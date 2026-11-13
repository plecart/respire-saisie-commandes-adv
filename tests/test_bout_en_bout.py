"""Test de bout en bout sans IA : les cinq documents fournis, de la ligne de commande aux sorties.

Un faux extracteur rend l'extraction attendue de chaque document, versionnée dans
`donnees/extractions/` et tirée des transcriptions manuelles relues deux fois. Les attendus sont
ceux du PRD #1, § « Résultats attendus sur les documents fournis ».
"""

import json
from pathlib import Path

import pytest

from saisie_commandes.champs import RawFields
from saisie_commandes.cli import main

ROOT = Path(__file__).parents[1]
EXTRACTIONS = Path(__file__).parent / "donnees" / "extractions"

TABLE = [
    ["Document", "Statut", "Client", "Référence", "Livraison", "Lignes", "Total HT"],
    ["Commande_1", "avertissement", "10102", "0", "2026-01-23", "13", "424,11"],
    ["Commande_2", "avertissement", "10107", "156006", "2026-01-20", "5", "525,75"],
    ["Commande_3", "accepté", "10103", "208532", "2026-01-13", "18", "1 592,99"],
    ["Commande_5", "bloqué", "10106", "2026-11-0457", "2026-11-10", "6", "601,53"],
    ["Document_4", "bloqué", "—", "—", "—", "—", "—"],
]
"""Tableau récapitulatif attendu, documents dans l'ordre de leurs noms."""

COMMANDE_2 = {
    "partner_id": 10107,
    "client_order_ref": "156006",
    "commitment_date": "2026-01-20",
    "order_line": [
        {"product_ref": "DSTPRECHFC", "product_uom_qty": 9, "price_unit": 9.75, "discount": 0.0},
        {"product_ref": "DSTPRECHVT", "product_uom_qty": 6, "price_unit": 10.0, "discount": 0.0},
        {"product_ref": "DSTPFC50", "product_uom_qty": 24, "price_unit": 10.75, "discount": 0.0},
        {"product_ref": "DSTPRECHME", "product_uom_qty": 9, "price_unit": 0.0, "discount": 0.0},
        {"product_ref": "DSTPVT50", "product_uom_qty": 12, "price_unit": 10.0, "discount": 0.0},
    ],
}
"""Commande attendue de Commande_2 : sans remise imprimée, une ligne à 0,00 €."""


def extraction(name: str) -> str:
    """JSON de l'extraction attendue d'un document, désigné par son nom sans extension."""
    return (EXTRACTIONS / f"{name}.json").read_text(encoding="utf-8")


def extract(document: Path) -> RawFields:
    """Faux extracteur : l'extraction attendue du document, retrouvée par son nom."""
    return RawFields.model_validate_json(extraction(document.stem))


@pytest.fixture
def lot(tmp_path, monkeypatch, capsys):
    """Lance la commande sur `exemples/` depuis la racine du dépôt ; rend sortie et terminal."""
    monkeypatch.chdir(ROOT)
    output = tmp_path / "sorties"
    assert main(["exemples", str(output)], extract=extract) == 0
    return output, capsys.readouterr().out


def report(output: Path) -> str:
    """Texte du rapport écrit dans le dossier de sortie."""
    return (output / "rapport.md").read_text(encoding="utf-8")


def table(text: str) -> list[list[str]]:
    """Cellules d'un tableau Markdown, ligne de séparation exclue."""
    rows = [line.strip("|").split("|") for line in text.splitlines()]
    return [[cell.strip() for cell in row] for row in rows if row[0].strip() != "---"]


def anomalies(text: str) -> dict[str, list[str]]:
    """Anomalies listées par le rapport, par document."""
    sections = (section.partition("\n") for section in text.split("\n## ")[1:])
    return {
        name: [line.removeprefix("- ") for line in body.splitlines() if line]
        for name, _, body in sections
    }


def test_le_rapport_s_ouvre_sur_le_tableau_recapitulatif_attendu(lot):
    output, _ = lot
    assert table(report(output).split("\n\n")[0]) == TABLE


def test_le_terminal_affiche_le_tableau_recapitulatif_sans_le_detail(lot):
    output, terminal = lot
    assert (table(terminal), terminal) == (TABLE, report(output).split("\n\n")[0] + "\n")


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("Commande_1", ["numéro de commande à « 0 »"], id="commande-1"),
        pytest.param(
            "Commande_2",
            ["code postal du document (59800) différent de la fiche (62000)"],
            id="commande-2",
        ),
        pytest.param("Commande_3", [], id="commande-3"),
        pytest.param("Document_4", ["n'est pas un bon de commande"], id="document-4"),
        pytest.param(
            "Commande_5",
            [
                "EAN absent (ligne 3)",
                "quantité en colis : « COL6 » (ligne 4, EAN 3760368742383)",
                "EAN inconnu du référentiel (ligne 5, EAN 3760368799912)",
            ],
            id="commande-5",
        ),
    ],
)
def test_le_rapport_porte_les_anomalies_attendues(lot, document, expected):
    output, _ = lot
    assert anomalies(report(output)).get(document, []) == expected


def test_le_dossier_de_sortie_contient_exactement_quatre_fichiers(lot):
    output, _ = lot
    assert sorted(path.name for path in output.iterdir()) == [
        "Commande_1.json",
        "Commande_2.json",
        "Commande_3.json",
        "rapport.md",
    ]


def test_une_commande_produite_est_au_format_exact_de_l_enonce(lot):
    output, _ = lot
    written = json.loads((output / "Commande_2.json").read_text(encoding="utf-8"))
    assert json.dumps(written) == json.dumps(COMMANDE_2)


@pytest.mark.parametrize("document", [row[0] for row in TABLE[1:]])
def test_une_extraction_attendue_respecte_le_schema_des_champs_bruts(document):
    text = extraction(document)
    assert RawFields.model_validate_json(text).model_dump(mode="json") == json.loads(text)
