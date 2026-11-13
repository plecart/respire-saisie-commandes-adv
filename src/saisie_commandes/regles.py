"""Règles métier : des champs bruts d'un document et des référentiels, le résultat du document.

Le cœur du programme, pur : ni réseau ni disque (PRD #1, « Modules »). Les règles suivent
l'ADR 0001 § 6 et le PRD #1, §§ « Règles de rapprochement », « Contrôles de calcul » et
« Table des statuts » :

- un document qui n'est pas un bon de commande s'arrête à cette seule anomalie ;
- sinon tous les contrôles s'exécutent, et le résultat garde toutes les anomalies relevées ;
- chaque ligne est recalculée dès que sa quantité, son prix et sa remise sont établis, même
  bloquée par ailleurs ; la formule prend une seule remise et une quantité en unités, si bien
  qu'une ligne à plusieurs remises, ou dont la quantité est en colis ou d'unité illisible, ne
  l'est pas ;
- une valeur illisible, ou que la lecture ne reconnaît pas (`valeurs`), n'est jamais devinée.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal

from saisie_commandes.champs import DocumentType, Illegible, Printed, RawFields, RawLine
from saisie_commandes.referentiels import ClientStatus, ReferenceData, Row, is_valid_ean13
from saisie_commandes.resultat import Anomaly, DocumentResult, Order, OrderLine, Status, Summary
from saisie_commandes.valeurs import (
    format_amount,
    parse_date,
    parse_number,
    parse_percent,
    parse_quantity,
    read,
    readable,
    round_to_cent,
)

type _Report = Callable[[str], None]
"""Consigne une anomalie, décrite par son message."""

_TOLERANCE = Decimal("0.01")
"""Écart accepté entre un total imprimé et son recalcul (PRD #1, « Contrôles de calcul »)."""

# ponytail: seul le préfixe « COL » (COL6, colis) désigne un colis ; ajouter les autres
# conditionnements (carton, lot) le jour où un document en imprime.
_PACK_UNITS = ("COL",)
"""Débuts d'une unité de colis, en majuscules."""

_UNMATCHED_CLIENT = {
    ClientStatus.NOT_FOUND: "client introuvable : « {name} »",
    ClientStatus.AMBIGUOUS: (
        "client ambigu : plusieurs fiches « {name} » que le code postal ne départage pas"
    ),
}
"""Anomalie bloquante de chaque issue de recherche qui ne retient aucune fiche."""


def apply_rules(fields: RawFields, references: ReferenceData) -> DocumentResult:
    """Résultat d'un document : statut, anomalies, ce qui a été établi, commande éventuelle.

    La commande n'est produite que si aucune anomalie ne bloque le document.
    """
    if fields.document_type is not DocumentType.ORDER:
        return DocumentResult((Anomaly("n'est pas un bon de commande", blocking=True),))

    anomalies: list[Anomaly] = []

    def block(message: str) -> None:
        anomalies.append(Anomaly(message, blocking=True))

    def warn(message: str) -> None:
        anomalies.append(Anomaly(message, blocking=False))

    partner_id = _partner_id(fields.pharmacy_name, fields.postal_code, references, block, warn)
    reference = _order_reference(fields.order_number, warn)
    delivery = _delivery_date(fields.delivery_date, warn)
    if not fields.lines:
        block("aucune ligne de commande")
    lines = [
        _check_line(number, line, references, anomalies)
        for number, line in enumerate(fields.lines, start=1)
    ]
    total = _document_total(fields.total_excl_tax, [total for _, total in lines], block)

    summary = Summary(partner_id, reference, delivery, len(fields.lines), total)
    result = DocumentResult(tuple(anomalies), summary)
    if result.status is Status.BLOCKED:
        return result
    order_lines = tuple(order_line for order_line, _ in lines)
    return replace(result, order=Order(partner_id, reference, delivery, order_lines))


def _partner_id(
    name: Printed,
    postal_code: Printed,
    references: ReferenceData,
    block: _Report,
    warn: _Report,
) -> int | None:
    """Identifiant du client retenu, ou `None` s'il est introuvable ou ambigu (bloquant).

    Un client retenu parmi les inactifs, ou dont la fiche porte un autre code postal que le
    document, appelle un avertissement.
    """
    pharmacy = _require(name, str, "nom de la pharmacie", "absent", block)
    if pharmacy is None:
        return None
    document_postal_code = readable(postal_code)
    found = references.find_client(pharmacy, document_postal_code)
    if found.client is None:
        block(_UNMATCHED_CLIENT[found.status].format(name=pharmacy))
        return None
    partner_id = int(found.client["id_client"])
    if found.status is ClientStatus.INACTIVE:
        warn(f"client retenu parmi les inactifs ({partner_id})")
    if found.client["code_postal"] != document_postal_code:
        warn(
            f"code postal du document ({document_postal_code or 'absent ou illisible'}) "
            f"différent de la fiche ({found.client['code_postal']})"
        )
    return partner_id


def _order_reference(printed: Printed, warn: _Report) -> str | None:
    """Numéro de commande tel quel ; absent, illisible ou « 0 », il appelle un avertissement."""
    reference = readable(printed)
    if reference is None:
        warn("numéro de commande absent")
    elif reference == "0":
        warn("numéro de commande à « 0 »")
    return reference


def _delivery_date(printed: Printed, warn: _Report) -> date | None:
    """Date de livraison, ou `None` avec un avertissement si elle est absente ou non reconnue.

    Une date passée est acceptée : la préférence du client est gardée.
    """
    text = readable(printed)
    if text is None:
        warn("date de livraison absente")
        return None
    delivery = parse_date(text)
    if delivery is None:
        warn(f"date de livraison mal formée ou sans année : « {text} »")
    return delivery


def _check_line(
    number: int, line: RawLine, references: ReferenceData, anomalies: list[Anomaly]
) -> tuple[OrderLine | None, Decimal | None]:
    """Contrôle une ligne : rend sa ligne de commande et son total imprimé, s'ils sont établis.

    Les anomalies de la ligne s'ajoutent à `anomalies`, situées par son numéro et son EAN.
    """
    printed_ean = readable(line.ean)

    def block(message: str) -> None:
        anomalies.append(Anomaly(message, blocking=True, line=number, ean=printed_ean))

    article = _article(read(line.ean), references, block)
    quantity = _require(line.quantity, parse_quantity, "quantité", "absente", block)
    price = _require(line.catalog_price, parse_number, "prix catalogue", "absent", block)
    total = _require(line.line_total, parse_number, "total de ligne", "absent", block)
    in_units = _quantity_in_units(line.unit, block)
    _check_free_units(line.free_units, block)
    discount = _discount(line.discounts, block)

    if quantity is None or not in_units or price is None or discount is None:
        return None, total
    expected = round_to_cent(quantity * price * (1 - discount / 100))
    if total is not None and not _agrees(total, expected):
        block(
            f"total de ligne incohérent : « {line.line_total} » imprimé, "
            f"{format_amount(expected)} calculé"
        )
    if article is None:
        return None, total
    return OrderLine(article["SKU"], quantity, price, discount), total


def _article(ean: str | Illegible | None, references: ReferenceData, block: _Report) -> Row | None:
    """Fiche de l'article désigné par l'EAN ; absent, illisible, invalide ou inconnu, il bloque."""
    if ean is None:
        block("EAN absent")
    elif isinstance(ean, Illegible):
        block("EAN illisible")
    elif not is_valid_ean13(ean):
        block("EAN-13 invalide")
    elif (article := references.find_article(ean)) is None:
        block("EAN inconnu du référentiel")
    else:
        return article
    return None


def _quantity_in_units(printed: Printed, block: _Report) -> bool:
    """Vrai si la quantité est en unités ; bloque une quantité en colis, ou d'unité illisible."""
    unit = read(printed)
    if isinstance(unit, Illegible):
        block("unité illisible")
        return False
    if unit is not None and unit.upper().startswith(_PACK_UNITS):
        block(f"quantité en colis : « {unit} »")
        return False
    return True


def _check_free_units(printed: Printed, block: _Report) -> None:
    """Bloque une ligne qui compte des unités gratuites, ou dont le nombre est illisible."""
    text = read(printed)
    if text is None:
        return
    count = _parse(text, parse_number, "nombre d'unités gratuites", block)
    if count is not None and count > 0:
        block(f"unités gratuites : « {text} »")


def _discount(printed: list[str | Illegible], block: _Report) -> Decimal | None:
    """Remise de la ligne en pourcentage, `0` sans remise ; `None` si illisible ou multiple."""
    texts = [text for item in printed if (text := read(item)) is not None]
    rates = [_parse(text, parse_percent, "remise", block) for text in texts]
    if None in rates:
        return None
    if len(rates) > 1:
        block("plusieurs remises : " + ", ".join(f"« {text} »" for text in texts))
        return None
    return rates[0] if rates else Decimal(0)


def _document_total(
    printed: Printed, line_totals: list[Decimal | None], block: _Report
) -> Decimal | None:
    """Total HT imprimé, comparé à la somme des totaux de ligne quand tous sont établis."""
    total = _require(printed, parse_number, "total HT", "absent", block)
    if total is None or None in line_totals:
        return total
    lines_sum = sum(line_totals, Decimal(0))
    if not _agrees(total, lines_sum):
        block(
            f"total HT incohérent : « {printed} » imprimé, "
            f"{format_amount(lines_sum)} pour la somme des lignes"
        )
    return total


def _require[T](
    printed: Printed, parse: Callable[[str], T | None], noun: str, absent: str, block: _Report
) -> T | None:
    """Valeur analysée d'un champ indispensable ; absente ou illisible, elle bloque.

    `noun` nomme le champ dans l'anomalie, `absent` en est l'adjectif accordé.
    """
    text = read(printed)
    if text is None:
        block(f"{noun} {absent}")
        return None
    return _parse(text, parse, noun, block)


def _parse[T](
    text: str | Illegible, parse: Callable[[str], T | None], noun: str, block: _Report
) -> T | None:
    """Valeur analysée d'un texte imprimé ; illisible ou non reconnue, elle bloque."""
    if isinstance(text, Illegible):
        block(f"{noun} illisible")
        return None
    value = parse(text)
    if value is None:
        block(f"{noun} illisible : « {text} »")
    return value


def _agrees(printed: Decimal, computed: Decimal) -> bool:
    """Vrai si un total imprimé et son recalcul s'écartent d'un centime au plus."""
    return abs(printed - computed) <= _TOLERANCE
