"""Tests de la ligne de commande, hors traitement d'un lot (voir `test_bout_en_bout`)."""

from importlib.metadata import entry_points

import pytest

from saisie_commandes.cli import main


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
