"""Réception d'un lot : les documents à traiter d'un dossier d'entrée.

Le dossier est parcouru fichier par fichier, sans descendre dans ses sous-dossiers. Un fichier
est reçu comme document par son extension, quelle que soit sa casse : un PDF, ou un mail `.eml` ;
les autres sont ignorés. Les documents se rendent dans l'ordre de leurs noms, quel que soit le
système de fichiers. Deux documents au même nom sans extension se repèrent (`shared_names`).

Un mail ne se lit que par ses pièces jointes, au sens de `EmailMessage.iter_attachments` : une
image incluse dans le corps n'en est pas une, un message transféré en est une. Son corps n'est
jamais lu. Le mail dont la seule pièce jointe est un PDF se traite comme ce PDF, que
`save_pdf_attachment` écrit dans un dossier ; tout autre mail est rejeté (`RejectedMail`).
"""

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
_UNNAMED_PDF = "piece_jointe.pdf"
"""Nom du PDF écrit quand le nom de sa pièce jointe ne désigne aucun fichier."""


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
    composant, coupé sur la barre oblique comme sur l'antislash, et se nomme `piece_jointe.pdf`
    s'il n'en reste aucun nom de fichier. Rien ne s'écrit hors de `directory`.

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
    """Nom d'une pièce jointe dans un motif : son nom de fichier, à défaut son type MIME."""
    return attachment.get_filename() or attachment.get_content_type()


def _is_pdf(attachment: EmailMessage) -> bool:
    """Vrai si la pièce jointe est un PDF : par son type MIME, ou par l'extension de son nom."""
    name = attachment.get_filename() or ""
    return attachment.get_content_type() == _PDF_TYPE or name.lower().endswith(_PDF_SUFFIX)


def _file_name(attachment: EmailMessage) -> str:
    """Nom du fichier où écrire une pièce jointe PDF : le dernier composant de son nom.

    `PureWindowsPath` coupe sur `/` comme sur l'antislash et retire un lecteur ; `.` ne survit pas
    au découpage, `..` si.
    """
    name = PureWindowsPath(attachment.get_filename() or "").name
    return name if name not in {"", ".."} else _UNNAMED_PDF
