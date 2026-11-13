"""Sorties d'un lot : un JSON par commande produite, le rapport d'anomalies, son résumé.

Le JSON d'une commande a exactement la forme de l'énoncé (PRD #1, « Commande produite ») :
quantité entière, prix et remise décimaux, remise en pourcentage (`35.0`, `0.0` sans remise) ;
une référence ou une date qui n'a pas pu être lue y est une chaîne vide. Le rapport `rapport.md`
s'ouvre sur le tableau récapitulatif du lot (`summary_table`), puis liste les anomalies de chaque
document qui en a, en français, situées par leur ligne et leur EAN.

Les fichiers s'écrivent en UTF-8, fins de ligne Unix (LF), quel que soit le système.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path

from saisie_commandes.resultat import Anomaly, DocumentResult, Order
from saisie_commandes.valeurs import format_amount

type Results = Mapping[str, DocumentResult]
"""Résultats d'un lot, par nom de document sans extension, dans l'ordre du lot."""

_REPORT = "rapport.md"
_COLUMNS = ("Document", "Statut", "Client", "Référence", "Livraison", "Lignes", "Total HT")
_NOT_ESTABLISHED = "—"
"""Cellule d'une valeur qui n'a pas été établie."""


def write_outputs(results: Results, directory: Path) -> None:
    """Écrit dans `directory`, créé s'il manque, le JSON de chaque commande produite et le rapport.

    Le JSON d'un document se nomme d'après lui : `<nom du document>.json`.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, result in results.items():
        if result.order is not None:
            order = json.dumps(_order_json(result.order), ensure_ascii=False, indent=2)
            _write(directory / f"{name}.json", order)
    _write(directory / _REPORT, _report(results))


def summary_table(results: Results) -> str:
    """Tableau récapitulatif du lot en Markdown, une ligne par document, sans fin de ligne finale.

    Une valeur qui n'a pas été établie s'écrit « — » ; un total, à la française.
    """
    rows = [_COLUMNS, ("---",) * len(_COLUMNS)]
    rows += [_summary_row(name, result) for name, result in results.items()]
    return "\n".join(f"| {' | '.join(row)} |" for row in rows)


def _order_json(order: Order) -> dict[str, object]:
    """Commande au format de l'énoncé, en types JSON : montants en nombres décimaux."""
    return {
        "partner_id": order.partner_id,
        "client_order_ref": order.client_order_ref or "",
        "commitment_date": order.commitment_date.isoformat() if order.commitment_date else "",
        "order_line": [
            {
                "product_ref": line.product_ref,
                "product_uom_qty": line.product_uom_qty,
                "price_unit": float(line.price_unit),
                "discount": float(line.discount),
            }
            for line in order.order_line
        ],
    }


def _summary_row(name: str, result: DocumentResult) -> tuple[str, ...]:
    """Ligne du tableau récapitulatif d'un document."""
    summary = result.summary
    values = (
        summary.partner_id,
        summary.client_order_ref,
        summary.commitment_date,
        summary.line_count,
        summary.total_excl_tax,
    )
    return (name, result.status, *map(_cell, values))


def _cell(value: int | str | date | Decimal | None) -> str:
    """Texte d'une cellule : « — » si la valeur n'est pas établie, un montant à la française."""
    if value is None:
        return _NOT_ESTABLISHED
    if isinstance(value, Decimal):
        return format_amount(value)
    return str(value)


def _report(results: Results) -> str:
    """Rapport du lot : le tableau récapitulatif, puis les anomalies de chaque document."""
    sections = [summary_table(results)]
    sections += [
        _anomalies_section(name, result.anomalies)
        for name, result in results.items()
        if result.anomalies
    ]
    return "\n\n".join(sections)


def _anomalies_section(name: str, anomalies: Iterable[Anomaly]) -> str:
    """Section du rapport d'un document : son nom en titre, puis ses anomalies en liste."""
    items = "\n".join(f"- {_describe(anomaly)}" for anomaly in anomalies)
    return f"## {name}\n\n{items}"


def _describe(anomaly: Anomaly) -> str:
    """Anomalie en clair, suivie de sa ligne et de son EAN quand elle en porte."""
    place = [f"ligne {anomaly.line}"] if anomaly.line is not None else []
    if anomaly.ean is not None:
        place.append(f"EAN {anomaly.ean}")
    return f"{anomaly.message} ({', '.join(place)})" if place else anomaly.message


def _write(path: Path, text: str) -> None:
    """Écrit un texte en UTF-8, fins de ligne Unix, terminé par une fin de ligne."""
    path.write_text(f"{text}\n", encoding="utf-8", newline="\n")
