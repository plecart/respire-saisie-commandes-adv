"""Réception d'un lot : les documents à traiter d'un dossier d'entrée.

Le dossier est parcouru fichier par fichier, sans descendre dans ses sous-dossiers. Un fichier
est reçu comme document par son extension, quelle que soit sa casse : un PDF, ou un mail `.eml` ;
les autres sont ignorés. Les documents se rendent dans l'ordre de leurs noms, quel que soit le
système de fichiers. Deux documents au même nom sans extension se repèrent (`shared_names`).

Un mail ne se lit que par ses pièces jointes, au sens de `EmailMessage.iter_attachments` : une
image incluse dans un `multipart/related` n'en est pas une, un message transféré en est une.
Son corps n'est jamais lu. Le mail dont la seule pièce jointe est un PDF se traite comme ce PDF, que
`save_pdf_attachment` écrit dans un dossier ; tout autre mail est rejeté (`RejectedMail`).

Tout ce que porte un mail est non fiable : une pièce jointe faite de parties (message transféré,
`multipart/*`) n'est jamais un PDF, le nom d'une pièce jointe ne devient un nom de fichier que
s'il a une forme sûre, et un motif de rejet n'en cite aucun caractère non imprimable.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path, PureWindowsPath

_PDF_SUFFIX = ".pdf"
_MAIL_SUFFIX = ".eml"
_DOCUMENT_SUFFIXES = frozenset({_PDF_SUFFIX, _MAIL_SUFFIX})
"""Extensions, en minuscules, des fichiers reçus comme documents."""

_PDF_TYPE = "application/pdf"

_SAFE_FILE_NAME = re.compile(r"[\w-][\w .-]{0,61}\.pdf", re.IGNORECASE)
"""Forme d'un nom de pièce jointe gardé comme nom de fichier, par liste blanche.

Lettres et chiffres de toute écriture, `_`, `-`, espace et point, ni point ni espace en tête,
terminé par `.pdf`. Au plus 62 caractères avant `.pdf`, de 4 octets UTF-8 au pire : 252 octets,
sous la limite de 255 octets d'un nom de fichier sous Linux.
"""

_WINDOWS_DEVICE = re.compile(r"(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³]) *(\.|$)", re.IGNORECASE)
"""Nom que Windows lit comme un périphérique, quelle que soit l'extension (`CON.pdf`, `nul.a.pdf`).

Noms réservés de la documentation Windows « Naming Files, Paths, and Namespaces » (lue le
2026-11-13), « suivis immédiatement d'une extension » compris. S'y ajoutent, par prudence, `COM0`,
`LPT0` et des espaces avant le point, qu'elle ne nomme pas : un tel nom ne fait que se replier.
"""

_UNNAMED_PDF = "piece_jointe.pdf"
"""Nom du PDF écrit quand le nom de sa pièce jointe n'est pas sûr (`_file_name`)."""

_UNPRINTABLE = chr(0xFFFD)
"""Caractère de remplacement Unicode, mis dans un motif à la place d'un caractère non imprimable."""


class RejectedMail(Exception):
    """Mail qui ne se traite pas comme un PDF ; son texte est le motif du blocage, en clair."""


def receive(directory: Path) -> list[Path]:
    """Documents à traiter dans `directory`, triés par nom."""
    documents = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _DOCUMENT_SUFFIXES
    ]
    return sorted(documents, key=lambda path: path.name)


def shared_names(documents: Iterable[Path]) -> list[str]:
    """Noms sans extension que portent plusieurs documents, triés : leurs sorties se confondraient.

    Sur un système de fichiers sensible à la casse, `A.pdf` et `A.PDF` sont deux documents.
    """
    counts = Counter(document.stem for document in documents)
    return sorted(name for name, count in counts.items() if count > 1)


def is_mail(document: Path) -> bool:
    """Vrai si le document est un mail, à traiter par son PDF joint (`save_pdf_attachment`)."""
    return document.suffix.lower() == _MAIL_SUFFIX


def save_pdf_attachment(mail: Path, directory: Path) -> Path:
    """Écrit dans `directory` le PDF qu'un mail porte en seule pièce jointe ; rend son chemin.

    Le nom de la pièce jointe vient d'un fichier non fiable : le PDF n'en garde que le dernier
    composant, coupé sur la barre oblique comme sur l'antislash, et seulement s'il a une forme
    sûre ; sinon il se nomme `piece_jointe.pdf`. Rien ne s'écrit hors de `directory`. Un motif de
    rejet cite le nom entier de la pièce jointe, ses seuls caractères non imprimables remplacés.

    Raises:
        RejectedMail: le mail n'a aucune pièce jointe, en a plusieurs, PDF ou non, ou sa seule
            pièce jointe n'est pas un PDF.
    """
    message = BytesParser(policy=policy.default).parsebytes(mail.read_bytes())
    attachment = _pdf_attachment(message)
    path = directory / _file_name(attachment)
    path.write_bytes(attachment.get_payload(decode=True))
    return path


def _pdf_attachment(message: EmailMessage) -> EmailMessage:
    """La seule pièce jointe d'un mail, qui est un PDF ; sinon `RejectedMail`, avec son motif."""
    attachments = list(message.iter_attachments())
    if not attachments:
        raise RejectedMail("mail sans pièce jointe")
    if len(attachments) > 1:
        names = ", ".join(map(_display_name, attachments))
        raise RejectedMail(
            f"mail avec {len(attachments)} pièces jointes ({names}), un seul PDF attendu"
        )
    (attachment,) = attachments
    if not _is_pdf(attachment):
        raise RejectedMail(f"pièce jointe « {_display_name(attachment)} » qui n'est pas un PDF")
    return attachment


def _display_name(attachment: EmailMessage) -> str:
    """Nom d'une pièce jointe dans un motif : son nom, à défaut son type MIME.

    L'un et l'autre peuvent porter une fin de ligne, même encodée : chaque caractère non
    imprimable y devient `_UNPRINTABLE`, pour qu'un motif tienne sur sa ligne du rapport ; un
    espace autre que l'espace ASCII (insécable, fine insécable) y devient un espace.
    """
    name = attachment.get_filename() or attachment.get_content_type()
    return "".join(map(_printable, name))


def _printable(char: str) -> str:
    """Le caractère s'il est imprimable ; sinon un espace pour un espace, `_UNPRINTABLE` sinon."""
    if char.isprintable():
        return char
    return " " if unicodedata.category(char) == "Zs" else _UNPRINTABLE


def _is_pdf(attachment: EmailMessage) -> bool:
    """Vrai si la pièce jointe est un PDF : faite d'octets, et de type MIME PDF ou nommée en `.pdf`.

    Le parseur lit une pièce jointe `message/*` ou `multipart/*` comme des parties, sans octets
    (`get_payload(decode=True)` rend `None`) : elle n'est jamais un PDF, quel que soit son nom.
    """
    if attachment.is_multipart():
        return False
    name = attachment.get_filename() or ""
    return attachment.get_content_type() == _PDF_TYPE or name.lower().endswith(_PDF_SUFFIX)


def _file_name(attachment: EmailMessage) -> str:
    """Nom de fichier du PDF d'une pièce jointe : le dernier composant de son nom, s'il est sûr.

    `PureWindowsPath` coupe sur `/` comme sur l'antislash et retire un lecteur ; le composant qui
    reste n'est gardé que s'il a la forme `_SAFE_FILE_NAME` et ne désigne pas un périphérique
    Windows (`_WINDOWS_DEVICE`), sinon le PDF se nomme `piece_jointe.pdf`.
    """
    name = PureWindowsPath(attachment.get_filename() or "").name
    safe = _SAFE_FILE_NAME.fullmatch(name) and not _WINDOWS_DEVICE.match(name)
    return name if safe else _UNNAMED_PDF
