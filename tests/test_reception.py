"""Tests de la réception : les documents d'un dossier d'entrée, le PDF joint à un mail."""

from email.message import EmailMessage
from pathlib import Path

import pytest
from mails import PDF, PDF_TYPE, mail

from saisie_commandes.reception import RejectedMail, receive, save_pdf_attachment, shared_names

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ORDER_BODY = (
    "Commande n° 208532 - GRANDE PHARMACIE DU LAC\n3760368741584 : 18 x 6,40, remise 35 %\n"
)
"""Corps qui recopie une commande en texte : il n'est jamais lu."""

UNNAMED = "piece_jointe.pdf"

LONGEST_NAME = chr(0x1D400) * 62 + ".pdf"
"""Le plus long nom gardé : 62 caractères de 4 octets en UTF-8, puis `.pdf` ; 252 octets."""

PDF_DIRECTORY = Path("temporaire", "mail")
"""Dossier du PDF écrit, deux niveaux sous le mail : un nom en `../../` en sortirait vers lui."""


def save(message: EmailMessage, root: Path) -> Path:
    """Écrit le mail dans `root`, puis son PDF joint sous `root / PDF_DIRECTORY` ; rend le PDF."""
    directory = root / PDF_DIRECTORY
    directory.mkdir(parents=True)
    path = root / "mail.eml"
    path.write_bytes(bytes(message))
    return save_pdf_attachment(path, directory)


def decision(message: EmailMessage, root: Path) -> str | tuple[str, bytes]:
    """Ce que la réception décide d'un mail : son motif de rejet, ou le nom et les octets du PDF."""
    try:
        written = save(message, root)
    except RejectedMail as rejection:
        return str(rejection)
    return written.name, written.read_bytes()


def forwarded() -> EmailMessage:
    """Mail qui porte en seule pièce jointe un message transféré, sans nom de fichier."""
    message = mail()
    message.add_attachment(mail(body="Commande transférée.\n"))
    return message


def test_la_reception_rend_les_pdf_et_les_mails_du_dossier_dans_l_ordre_de_leurs_noms(tmp_path):
    (tmp_path / "c.pdf").mkdir()
    for name in ("a.pdf", "B.PDF", "b.eml", "A.EML", "notes.txt", "c.pdf/d.pdf"):
        (tmp_path / name).write_bytes(b"")
    assert [path.name for path in receive(tmp_path)] == ["A.EML", "B.PDF", "a.pdf", "b.eml"]


def test_deux_documents_qui_ne_different_que_par_l_extension_partagent_leur_nom():
    documents = [Path("lot/A.pdf"), Path("lot/B.pdf"), Path("lot/A.PDF"), Path("lot/C.Pdf")]
    assert shared_names([*documents, Path("lot/C.pdf")]) == ["A", "C"]


def test_le_pdf_seul_joint_a_un_mail_s_ecrit_dans_le_dossier_sous_son_nom(tmp_path):
    written = save(mail(("Commande.pdf", PDF_TYPE)), tmp_path)
    assert (written, written.read_bytes()) == (tmp_path / PDF_DIRECTORY / "Commande.pdf", PDF)


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        pytest.param(mail(body=ORDER_BODY), "mail sans pièce jointe", id="sans-piece-jointe"),
        pytest.param(
            mail(("a.pdf", PDF_TYPE), ("b.pdf", PDF_TYPE), ("logo.png", "image/png")),
            "mail avec 3 pièces jointes (a.pdf, b.pdf, logo.png), un seul PDF attendu",
            id="plusieurs-pieces-jointes",
        ),
        pytest.param(
            mail(("Commande.pdf", PDF_TYPE), (None, "image/png")),
            "mail avec 2 pièces jointes (Commande.pdf, image/png), un seul PDF attendu",
            id="une-sans-nom-parmi-plusieurs",
        ),
        pytest.param(
            mail(("devis.docx", DOCX_TYPE)),
            "pièce jointe « devis.docx » qui n'est pas un PDF",
            id="seule-piece-jointe-docx",
        ),
        pytest.param(
            forwarded(),
            "pièce jointe « message/rfc822 » qui n'est pas un PDF",
            id="seul-message-transfere",
        ),
    ],
)
def test_un_mail_qui_ne_porte_pas_un_seul_pdf_est_rejete_avec_son_motif(tmp_path, message, reason):
    with pytest.raises(RejectedMail) as rejection:
        save(message, tmp_path)
    assert (str(rejection.value), list((tmp_path / PDF_DIRECTORY).iterdir())) == (reason, [])


def test_un_mail_dont_le_corps_inclut_une_image_se_traite_comme_son_seul_pdf_joint(tmp_path):
    message = EmailMessage()
    message.set_content('<p>Commande ci-jointe.</p><img src="cid:logo">', subtype="html")
    message.add_related(b"logo", maintype="image", subtype="png", cid="<logo>")
    message.add_attachment(PDF, maintype="application", subtype="pdf", filename="Commande.pdf")
    assert decision(message, tmp_path) == ("Commande.pdf", PDF)


def test_une_piece_jointe_octet_stream_nommee_en_pdf_est_un_pdf(tmp_path):
    message = mail(("Commande.PDF", "application/octet-stream"))
    assert decision(message, tmp_path) == ("Commande.PDF", PDF)


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda part: part.set_content(mail()), id="message-rfc822"),
        pytest.param(EmailMessage.make_mixed, id="multipart-mixed"),
        pytest.param(EmailMessage.make_alternative, id="multipart-alternative"),
        pytest.param(EmailMessage.make_related, id="multipart-related"),
    ],
)
def test_une_piece_jointe_faite_de_parties_n_est_pas_un_pdf_meme_nommee_en_pdf(tmp_path, make):
    """Message transféré ou multipart : le parseur en lit des parties, jamais des octets."""
    part = mail()
    make(part)
    part["Content-Disposition"] = 'attachment; filename="x.pdf"'
    message = mail()
    message.make_mixed()
    message.attach(part)
    assert decision(message, tmp_path) == "pièce jointe « x.pdf » qui n'est pas un PDF"


def test_deux_mails_au_meme_corps_mais_aux_pieces_jointes_differentes_sont_decides_autrement(
    tmp_path,
):
    pdf = decision(mail(("Commande.pdf", PDF_TYPE), body=ORDER_BODY), tmp_path / "pdf")
    docx = decision(mail(("devis.docx", DOCX_TYPE), body=ORDER_BODY), tmp_path / "docx")
    assert (pdf, docx) == (
        ("Commande.pdf", PDF),
        "pièce jointe « devis.docx » qui n'est pas un PDF",
    )


@pytest.mark.parametrize(
    "attachments",
    [
        pytest.param([("Commande.pdf", PDF_TYPE)], id="un-pdf"),
        pytest.param([], id="aucune"),
        pytest.param([("devis.docx", DOCX_TYPE)], id="un-docx"),
    ],
)
def test_deux_mails_aux_memes_pieces_jointes_sont_decides_de_meme_quel_que_soit_leur_corps(
    tmp_path, attachments
):
    bodies = {"texte": "Bonjour.\n", "commande": ORDER_BODY, "vide": "", "absent": None}
    decisions = {
        decision(mail(*attachments, body=body), tmp_path / name) for name, body in bodies.items()
    }
    assert len(decisions) == 1


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("../../x.pdf", id="barres-obliques"),
        pytest.param(r"..\..\x.pdf", id="antislashs"),
        pytest.param("{tmp_path}/x.pdf", id="chemin-absolu"),
    ],
)
def test_une_piece_jointe_nommee_par_un_chemin_s_ecrit_dans_le_dossier_sous_son_dernier_composant(
    tmp_path, name
):
    written = save(mail((name.format(tmp_path=tmp_path), PDF_TYPE)), tmp_path)
    files = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    assert (written, files) == (
        tmp_path / PDF_DIRECTORY / "x.pdf",
        [tmp_path / "mail.eml", tmp_path / PDF_DIRECTORY / "x.pdf"],
    )


@pytest.mark.parametrize(
    ("name", "file_name"),
    [
        pytest.param("Commande_3.pdf", "Commande_3.pdf", id="garde-souligne"),
        pytest.param("Commande 3.PDF", "Commande 3.PDF", id="garde-espace-et-capitales"),
        pytest.param("bon-de-commande.pdf", "bon-de-commande.pdf", id="garde-tirets"),
        pytest.param("Commande_reçue.pdf", "Commande_reçue.pdf", id="garde-accent"),
        pytest.param(LONGEST_NAME, LONGEST_NAME, id="garde-252-octets"),
        pytest.param(None, UNNAMED, id="absent"),
        pytest.param("", UNNAMED, id="vide"),
        pytest.param(".", UNNAMED, id="point"),
        pytest.param("..", UNNAMED, id="dossier-parent"),
        pytest.param("...", UNNAMED, id="trois-points"),
        pytest.param("a" * 63 + ".pdf", UNNAMED, id="un-caractere-de-trop"),
        pytest.param("a" * 300 + ".pdf", UNNAMED, id="304-caracteres"),
        pytest.param("a" + chr(0) + "b.pdf", UNNAMED, id="caractere-nul"),
        pytest.param("a.pdf:x", UNNAMED, id="flux-ntfs"),
        pytest.param("a*.pdf", UNNAMED, id="etoile"),
        pytest.param("a?.pdf", UNNAMED, id="point-d-interrogation"),
        pytest.param("a<.pdf", UNNAMED, id="chevron-ouvrant"),
        pytest.param("a>.pdf", UNNAMED, id="chevron-fermant"),
        pytest.param("a|.pdf", UNNAMED, id="barre-verticale"),
        pytest.param('a".pdf', UNNAMED, id="guillemet"),
        pytest.param("devis", UNNAMED, id="sans-extension-pdf"),
        pytest.param(".cache.pdf", UNNAMED, id="point-initial"),
        pytest.param("a.pdf.", UNNAMED, id="point-final"),
    ],
)
def test_un_pdf_joint_garde_son_nom_s_il_a_une_forme_sure_sinon_se_nomme_piece_jointe(
    tmp_path, name, file_name
):
    assert decision(mail((name, PDF_TYPE)), tmp_path) == (file_name, PDF)
