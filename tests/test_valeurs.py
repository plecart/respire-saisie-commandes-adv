"""Tests de l'écriture d'un montant : au centime, arrondi au demi supérieur, à la française."""

from decimal import Decimal

import pytest

from saisie_commandes.valeurs import format_amount


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        pytest.param("83.85", "83,85", id="centimes"),
        pytest.param("1592.99", "1 592,99", id="espace-de-milliers"),
        pytest.param("1234567", "1 234 567,00", id="millions-sans-centimes"),
        pytest.param("525.750", "525,75", id="trois-decimales"),
        pytest.param("0.005", "0,01", id="demi-superieur"),
    ],
)
def test_un_montant_s_ecrit_a_la_francaise(amount, text):
    assert format_amount(Decimal(amount)) == text
