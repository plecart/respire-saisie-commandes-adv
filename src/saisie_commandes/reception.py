"""Réception d'un lot : les documents à traiter d'un dossier d'entrée.

Le dossier est parcouru fichier par fichier, sans descendre dans ses sous-dossiers. Un fichier
est reçu comme document par son extension, quelle que soit sa casse : un PDF, ou un mail `.eml` ;
les autres sont ignorés. Les documents se rendent dans l'ordre de leurs noms, quel que soit le
système de fichiers. Deux documents au même nom sans extension se repèrent (`shared_names`).

Un mail ne se lit que par ses pièces jointes, au sens de `EmailMessage.iter_attachments` : une
image incluse dans un `multipart/related` n'en est pas une, un message transféré en est une.
Son corps n'est jamais lu. Parmi ses pièces jointes, seuls les PDF comptent, les autres sont
ignorées : le mail qui porte un seul PDF joint se traite comme ce PDF, que `save_pdf_attachment`
écrit dans un dossier ; le mail qui n'en porte aucun, ou plusieurs, est rejeté (`RejectedMail`).
Aucun PDF n'est cherché plus loin que le premier niveau : ni dans un message transféré, ni sous
l'enveloppe `multipart/signed` d'un mail signé S/MIME, ni dans un mail sans parties, dont tout le
contenu est un PDF (mail de scanner).

Tout ce que porte un mail est non fiable : une pièce jointe faite de parties (message transféré,
`multipart/*`) n'est jamais un PDF, le nom d'une pièce jointe ne devient un nom de fichier que
s'il a une forme sûre, et un motif de rejet n'en cite aucun caractère non imprimable.
"""

import re
from collections import Counter
from collections.abc import Iterable
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path, PureWindowsPath

from saisie_commandes.valeurs import on_one_line

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
    """Écrit dans `directory` le seul PDF joint à un mail ; rend son chemin.

    Les pièces jointes qui ne sont pas des PDF sont ignorées. Le nom du PDF joint vient d'un
    fichier non fiable : le PDF n'en garde que le dernier composant, coupé sur la barre
    oblique comme sur l'antislash, et seulement s'il a une forme sûre ; sinon il se nomme
    `piece_jointe.pdf`. Rien ne s'écrit hors de `directory`, ni rien du tout pour un mail rejeté.
    Le motif de rejet d'un mail à plusieurs PDF cite le nom entier de chacun, ses seuls
    caractères non imprimables remplacés.

    Raises:
        RejectedMail: le mail ne porte aucun PDF joint, ou en porte plusieurs.
    """
    message = BytesParser(policy=policy.default).parsebytes(mail.read_bytes())
    attachment = _pdf_attachment(message)
    path = directory / _file_name(attachment)
    path.write_bytes(attachment.get_payload(decode=True))
    return path


def _pdf_attachment(message: EmailMessage) -> EmailMessage:
    """Le seul PDF parmi les pièces jointes d'un mail ; sinon `RejectedMail`, avec son motif."""
    pdfs = [attachment for attachment in message.iter_attachments() if _is_pdf(attachment)]
    if not pdfs:
        raise RejectedMail("aucun PDF en pièce jointe")
    if len(pdfs) > 1:
        names = ", ".join(map(_display_name, pdfs))
        raise RejectedMail(f"plusieurs PDF en pièce jointe ({names}), un seul attendu")
    return pdfs[0]


def _display_name(pdf: EmailMessage) -> str:
    """Nom d'un PDF joint dans un motif : son nom, à défaut son type, `application/pdf`.

    Un PDF sans nom ne l'est que par ce type (`_is_pdf`) : seul le nom vient du mail. Ce nom peut
    porter une fin de ligne, même encodée : il s'écrit sur une ligne (`on_one_line`), pour qu'un
    motif tienne sur sa ligne du rapport.
    """
    return on_one_line(pdf.get_filename() or _PDF_TYPE)


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
