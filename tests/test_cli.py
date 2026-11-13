"""Tests de la ligne de commande, hors traitement d'un lot fourni (voir `test_bout_en_bout`)."""

from importlib.metadata import entry_points
from pathlib import Path

import pytest
from mails import PDF, PDF_TYPE, mail

from saisie_commandes.champs import DocumentType, RawFields
from saisie_commandes.cli import main, process_documents
from saisie_commandes.referentiels import ReferenceData

ROOT = Path(__file__).parents[1]

NOT_AN_ORDER = RawFields(
    document_type=DocumentType.OTHER,
    pharmacy_name=None,
    postal_code=None,
    order_number=None,
    delivery_date=None,
    total_excl_tax=None,
    lines=[],
)
"""Champs bruts d'un document qui n'est pas un bon de commande."""


def test_sans_extracteur_la_commande_s_arrete_sur_un_message_sans_rien_ecrire(tmp_path, capsys):
    output = tmp_path / "sorties"
    code = main([str(tmp_path), str(output)])
    assert (code, capsys.readouterr().err, output.exists()) == (
        1,
        (
            "saisie-commandes : aucun extracteur de documents n'est branché, "
            "aucun document n'a été traité.\n"
        ),
        False,
    )


def test_la_commande_installee_se_nomme_saisie_commandes():
    (script,) = entry_points(group="console_scripts", name="saisie-commandes")
    assert script.load() is main


def test_deux_documents_du_meme_nom_refusent_le_lot_sans_rien_ecrire(tmp_path, capsys, monkeypatch):
    """`A.pdf` et `A.PDF` ne coexistent que sur un système de fichiers sensible à la casse.

    La réception est donc simulée, pour que le test tourne aussi sous Windows et macOS.
    """
    received = tmp_path / "entree"
    monkeypatch.setattr(
        "saisie_commandes.cli.receive",
        lambda directory: [received / "A.pdf", received / "A.PDF"],
    )
    output = tmp_path / "sorties"
    code = main([str(received), str(output)], extract=lambda document: pytest.fail("extrait"))
    assert (code, capsys.readouterr().err, output.exists()) == (
        1,
        (
            "saisie-commandes : plusieurs documents portent le nom « A », "
            "aucun document n'a été traité.\n"
        ),
        False,
    )


def test_un_mail_bloque_figure_au_rapport_et_au_terminal_sans_appeler_l_extracteur(
    tmp_path, capsys, monkeypatch
):
    """Son extension est en capitales : un mail se reconnaît quelle que soit la casse."""
    received = tmp_path / "entree"
    received.mkdir()
    (received / "Mail.EML").write_bytes(bytes(mail(body="Commande n° 208532, 18 lignes.\n")))
    output = tmp_path / "sorties"
    monkeypatch.chdir(ROOT)
    code = main([str(received), str(output)], extract=lambda document: pytest.fail("extrait"))
    table = (
        "| Document | Statut | Client | Référence | Livraison | Lignes | Total HT |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| Mail | bloqué | — | — | — | — | — |"
    )
    report = (output / "rapport.md").read_text(encoding="utf-8")
    assert (code, capsys.readouterr().out, report, [path.name for path in output.iterdir()]) == (
        0,
        f"{table}\n",
        f"{table}\n\n## Mail\n\n- mail sans pièce jointe\n",
        ["rapport.md"],
    )


def test_l_extracteur_recoit_le_pdf_joint_a_un_mail_qui_ne_lui_survit_pas(tmp_path):
    document = tmp_path / "Mail.eml"
    document.write_bytes(bytes(mail(("Commande.pdf", PDF_TYPE))))
    extracted = {}

    def extract(pdf: Path) -> RawFields:
        extracted[pdf] = pdf.read_bytes()
        return NOT_AN_ORDER

    results = process_documents([document], tmp_path / "sorties", extract, ReferenceData([], []))
    ((pdf, content),) = extracted.items()
    assert (list(results), pdf.name, content, pdf.parent.exists()) == (
        ["Mail"],
        "Commande.pdf",
        PDF,
        False,
    )
