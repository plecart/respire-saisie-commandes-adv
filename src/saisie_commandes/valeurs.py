"""Valeurs à la française : lecture d'un champ brut en valeur typée, écriture d'un montant.

Les formes reconnues couvrent celles des documents fournis : nombres à la française
(« 1592,99 », « 9,750 », « 0,00 € », espaces de milliers admis), pourcentages (« 35% »,
« 35,00 % »), dates jour, mois, année (« 23.01.2026 », « 20/01/26 »). Une cellule vide ou faite
de tirets vaut une valeur absente. Chaque analyse rend `None` pour un texte qu'elle ne reconnaît
pas ; à l'appelant d'en faire une valeur illisible.

Un montant s'arrondit au centime, au demi supérieur (PRD #1, « Contrôles de calcul »), et
s'écrit comme il s'imprime : « 1 592,99 ».
"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from saisie_commandes.champs import Illegible, Printed

_CENT = Decimal("0.01")
_NUMBER = re.compile("[0-9]+(?:,[0-9]+|[.](?:[0-9]{1,2}|[0-9]{4,}))?")
_DATE = re.compile("(?P<day>[0-9]{1,2})[./-](?P<month>[0-9]{1,2})[./-](?P<year>[0-9]{4}|[0-9]{2})")


def read(printed: Printed) -> str | Illegible | None:
    """Valeur imprimée sans ses espaces de bord ; `None` pour une cellule vide ou de tirets."""
    if not isinstance(printed, str):
        return printed
    text = printed.strip()
    return text if text.strip("-–—") else None


def readable(printed: Printed) -> str | None:
    """Texte imprimé et lisible, ou `None` s'il est absent ou illisible."""
    text = read(printed)
    return text if isinstance(text, str) else None


def parse_number(text: str) -> Decimal | None:
    """Nombre positif ou nul à la française : espaces et symbole euro ignorés, virgule décimale.

    Un point décimal est admis, sauf suivi d'exactement trois chiffres : « 1.000 » vaut 1 ou 1000
    selon que le point est décimal ou de milliers. Aucun document fourni n'imprime de point dans
    un nombre.
    """
    compact = "".join(text.split()).strip("€")
    if _NUMBER.fullmatch(compact) is None:
        return None
    return Decimal(compact.replace(",", "."))


def parse_quantity(text: str) -> int | None:
    """Quantité entière : « 12 », ou « 12,00 » ; « 2,5 » n'en est pas une."""
    number = parse_number(text)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def parse_percent(text: str) -> Decimal | None:
    """Pourcentage, signe « % » facultatif : « 35% », « 35,00 % », « 0 »."""
    return parse_number(text.replace("%", ""))


def parse_date(text: str) -> date | None:
    """Date jour, mois, année, séparés par « / », « . » ou « - ».

    Une année sur deux chiffres est lue dans le siècle courant. Une date sans année, ou qui
    n'existe pas au calendrier, n'est pas reconnue.
    """
    match = _DATE.fullmatch(text)
    if match is None:
        return None
    day, month, year = (int(group) for group in match.groups())
    if len(match["year"]) == 2:
        # ponytail: siècle courant fixé à 2000 sans lire l'horloge, pour rester pur ;
        # à revoir avant 2100.
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def round_to_cent(amount: Decimal) -> Decimal:
    """Montant arrondi au centime, au demi supérieur : 38,025 donne 38,03."""
    return amount.quantize(_CENT, ROUND_HALF_UP)


def format_amount(amount: Decimal) -> str:
    """Montant au centime, à la française : espace de milliers, virgule décimale (« 1 592,99 »)."""
    return f"{round_to_cent(amount):,}".replace(",", " ").replace(".", ",")
