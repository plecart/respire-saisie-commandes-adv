"""Tests du schéma des champs bruts : export JSON Schema, absent et illisible, aller-retour."""

import json

import pytest

from saisie_commandes.champs import ILLEGIBLE, RawFields, RawLine

LINE = {
    "ean": None,
    "quantity": "6",
    "unit": "UN",
    "free_units": None,
    "catalog_price": "17,45",
    "discounts": ["35%", {"illegible": True}],
    "line_total": {"illegible": True},
}

DOCUMENT = {
    "document_type": "commande",
    "pharmacy_name": "PHARMACIE DU VIEUX LILLE",
    "postal_code": "59800",
    "order_number": "2026-11-0457",
    "delivery_date": "10/11/2026",
    "total_excl_tax": "601,53",
    "lines": [LINE],
}


def test_le_schema_exporte_distingue_absent_d_illisible():
    printed = RawFields.model_json_schema()["$defs"]["Printed"]["anyOf"]
    assert printed == [{"type": "string"}, {"$ref": "#/$defs/Illegible"}, {"type": "null"}]


def test_le_marqueur_illisible_est_un_objet_explicite():
    illegible = RawFields.model_json_schema()["$defs"]["Illegible"]
    assert (illegible["properties"]["illegible"]["const"], illegible["required"]) == (
        True,
        ["illegible"],
    )


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        pytest.param('"3760368740730"', "3760368740730", id="texte"),
        pytest.param("null", None, id="absent"),
        pytest.param('{"illegible": true}', ILLEGIBLE, id="illisible"),
    ],
)
def test_une_valeur_imprimee_se_lit_texte_absente_ou_illisible(printed, expected):
    assert RawLine.model_validate({**LINE, "ean": json.loads(printed)}).ean == expected


def test_un_objet_vide_n_est_pas_une_valeur_illisible():
    with pytest.raises(ValueError, match="illegible"):
        RawLine.model_validate({**LINE, "ean": {}})


def test_un_champ_inconnu_est_refuse():
    with pytest.raises(ValueError, match="extra"):
        RawLine.model_validate({**LINE, "designation": "SERUM GLOW & PROTECT 30ML"})


def test_tout_champ_est_requis():
    without_free_units = {name: value for name, value in LINE.items() if name != "free_units"}
    with pytest.raises(ValueError, match="free_units"):
        RawLine.model_validate(without_free_units)


def test_aller_retour_json():
    fields = RawFields.model_validate_json(json.dumps(DOCUMENT))
    assert json.loads(fields.model_dump_json()) == DOCUMENT
