"""Mails construits par `EmailMessage` pour les tests : un corps, puis des pièces jointes."""

from email.message import EmailMessage

PDF = b"%PDF-1.7 " + bytes(range(256))
"""Octets de chaque pièce jointe : tous les octets possibles, pour qu'aucun ne se perde."""

PDF_TYPE = "application/pdf"


def mail(
    *attachments: tuple[str | None, str], body: str | None = "Bonjour, voici notre commande.\n"
) -> EmailMessage:
    """Mail de ce corps, sans corps si `None`, suivi de ces pièces jointes, qui portent `PDF`.

    Une pièce jointe se donne par son nom de fichier, `None` s'il n'en a pas, et son type MIME.
    """
    message = EmailMessage()
    if body is not None:
        message.set_content(body)
    for filename, content_type in attachments:
        maintype, subtype = content_type.split("/")
        message.add_attachment(PDF, maintype=maintype, subtype=subtype, filename=filename)
    return message
