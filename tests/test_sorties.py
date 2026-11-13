"""Tests des sorties d'un lot, par les fichiers écrits et le résumé rendu."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from saisie_commandes.resultat import Anomaly, DocumentResult, Order, OrderLine, Summary
from saisie_commandes.sorties import summary_table, write_outputs

ENONCE = {
    "partner_id": 10103,
    "client_order_ref": "208532",
    "commitment_date": "2026-01-13",
    "order_line": [
        {"product_ref": "DSTPFC50", "product_uom_qty": 12, "price_unit": 10.75, "discount": 35.0}
    ],
}
"""L'exemple de commande de l'énoncé."""

COMMANDE_3 = DocumentResult(
    anomalies=(),
    summary=Summary(10103, "208532", date(2026, 1, 13), 18, Decimal("1592.99")),
    order=Order(
        10103,
        "208532",
        date(2026, 1, 13),
        (OrderLine("DSTPFC50", 12, Decimal("10.75"), Decimal(35)),),
    ),
)
"""Commande_3 : son résumé, et sa commande réduite à la ligne de l'exemple de l'énoncé."""

DOCUMENT_4 = DocumentResult((Anomaly("n'est pas un bon de commande", blocking=True),))

COMMANDE_5 = DocumentResult(
    anomalies=(
        Anomaly("EAN absent", blocking=True, line=3),
        Anomaly("quantité en colis : « COL6 »", blocking=True, line=4, ean="3760368742383"),
    ),
    summary=Summary(10106, "2026-11-0457", date(2026, 11, 10), 6, Decimal("601.53")),
)

TABLE = """\
| Document | Statut | Client | Référence | Livraison | Lignes | Total HT |
| --- | --- | --- | --- | --- | --- | --- |
| Commande_3 | accepté | 10103 | 208532 | 2026-01-13 | 18 | 1 592,99 |
| Document_4 | bloqué | — | — | — | — | — |
| Commande_5 | bloqué | 10106 | 2026-11-0457 | 2026-11-10 | 6 | 601,53 |"""

RESULTS = {"Commande_3": COMMANDE_3, "Document_4": DOCUMENT_4, "Commande_5": COMMANDE_5}


def written_order(tmp_path, order: Order) -> str:
    """JSON écrit pour une commande produite, relu puis réécrit tel quel : types compris."""
    write_outputs({"Commande": DocumentResult((), order=order)}, tmp_path)
    text = (tmp_path / "Commande.json").read_text(encoding="utf-8")
    return json.dumps(json.loads(text))


def test_une_commande_s_ecrit_au_format_de_l_enonce(tmp_path):
    assert written_order(tmp_path, COMMANDE_3.order) == json.dumps(ENONCE)


def test_une_reference_ou_une_date_absente_reste_vide_et_sans_remise_la_remise_vaut_zero(
    tmp_path,
):
    order = Order(10102, None, None, (OrderLine("DSTPRECHDM", 6, Decimal("0.00"), Decimal(0)),))
    expected = {
        "partner_id": 10102,
        "client_order_ref": "",
        "commitment_date": "",
        "order_line": [
            {"product_ref": "DSTPRECHDM", "product_uom_qty": 6, "price_unit": 0.0, "discount": 0.0}
        ],
    }
    assert written_order(tmp_path, order) == json.dumps(expected)


def test_le_json_garde_ses_accents_sans_echappement(tmp_path):
    order = Order(10106, "Réf. n° 0457", None, COMMANDE_3.order.order_line)
    write_outputs({"Commande": DocumentResult((), order=order)}, tmp_path)
    assert '"Réf. n° 0457"' in (tmp_path / "Commande.json").read_text(encoding="utf-8")


def test_les_sorties_ont_des_fins_de_ligne_unix_quel_que_soit_le_systeme(tmp_path):
    write_outputs(RESULTS, tmp_path)
    written = [path.read_bytes() for path in sorted(tmp_path.iterdir())]
    assert [b"\r" in content for content in written] == [False, False]


def test_seule_une_commande_produite_a_son_json_dans_un_dossier_cree_s_il_manque(tmp_path):
    directory = tmp_path / "sorties" / "lot"
    write_outputs(RESULTS, directory)
    assert sorted(path.name for path in directory.iterdir()) == ["Commande_3.json", "rapport.md"]


def test_le_tableau_recapitulatif_marque_d_un_tiret_ce_qui_n_a_pas_ete_etabli():
    assert summary_table(RESULTS) == TABLE


def test_le_rapport_s_ouvre_sur_le_tableau_puis_liste_les_anomalies_situees(tmp_path):
    write_outputs(RESULTS, tmp_path)
    assert (tmp_path / "rapport.md").read_text(encoding="utf-8") == (
        f"{TABLE}\n"
        "\n"
        "## Document_4\n"
        "\n"
        "- n'est pas un bon de commande\n"
        "\n"
        "## Commande_5\n"
        "\n"
        "- EAN absent (ligne 3)\n"
        "- quantité en colis : « COL6 » (ligne 4, EAN 3760368742383)\n"
    )


def written_files(directory) -> dict[str, bytes]:
    """Contenu de chaque fichier d'un dossier de sortie, par nom."""
    return {path.name: path.read_bytes() for path in directory.iterdir()}


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(
            COMMANDE_3,
            replace(COMMANDE_3, order=replace(COMMANDE_3.order, client_order_ref="208533")),
            id="commande-reecrite",
        ),
        pytest.param(COMMANDE_3, DOCUMENT_4, id="commande-bloquee-a-la-relance"),
        pytest.param(DOCUMENT_4, COMMANDE_5, id="rapport-reecrit"),
    ],
)
def test_une_relance_dans_le_meme_dossier_ecrit_ce_qu_ecrirait_un_dossier_neuf(
    tmp_path, first, second
):
    """Relancé sur un dossier de sortie déjà servi, le lot y laisse ce qu'un dossier neuf aurait.

    Trois formes : JSON réécrit, JSON d'un document bloqué à la relance retiré, rapport réécrit.
    """
    write_outputs({"Commande": first}, tmp_path / "relance")
    write_outputs({"Commande": second}, tmp_path / "relance")
    write_outputs({"Commande": second}, tmp_path / "neuf")
    assert written_files(tmp_path / "relance") == written_files(tmp_path / "neuf")
