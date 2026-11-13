"""Résultat d'un document : son statut, sa commande éventuelle, ses anomalies.

Contrat entre les règles métier, les sorties et la réception des mails. Le statut se déduit des
anomalies, jamais l'inverse : une seule anomalie bloquante suffit à bloquer le document, qui n'a
alors pas de commande. Le résultat porte aussi ce qui a été établi du document, bloqué ou non,
pour le rapport du lot ; un mail rejeté s'exprime par une anomalie seule, sans rien d'établi.

La commande reprend les champs d'une commande de vente Odoo (`sale.order`) au format de
l'énoncé, en types justes : montants en `Decimal`, date en `date`. Sa mise en JSON revient aux
sorties.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Status(StrEnum):
    """Statut d'un document : ce que la machine peut faire seule."""

    ACCEPTED = "accepté"
    """Aucun doute : la commande est produite."""
    WARNING = "avertissement"
    """Commande exploitable, avec un point à vérifier : elle est produite."""
    BLOCKED = "bloqué"
    """La machine ne décide pas seule : aucune commande produite."""


@dataclass(frozen=True)
class Anomaly:
    """Un point relevé sur un document, en français, situé quand il porte sur une ligne."""

    message: str
    blocking: bool
    """Vrai si l'anomalie bloque le document, faux si elle n'appelle qu'un avertissement."""
    line: int | None = None
    """Numéro de la ligne concernée, à partir de 1."""
    ean: str | None = None
    """EAN imprimé sur la ligne concernée, s'il a été lu."""


@dataclass(frozen=True)
class OrderLine:
    """Une ligne de commande de vente."""

    product_ref: str
    """SKU de l'article, sa référence interne Odoo."""
    product_uom_qty: int
    """Quantité commandée, en unités."""
    price_unit: Decimal
    """Prix catalogue avant remise."""
    discount: Decimal
    """Remise en pourcentage (`35` pour 35 %), `0` sans remise."""


@dataclass(frozen=True)
class Order:
    """Une commande de vente prête à créer dans Odoo."""

    partner_id: int
    """Identifiant du client au référentiel."""
    client_order_ref: str | None
    """Numéro de commande de la pharmacie, tel qu'imprimé ; `None` s'il n'a pas pu être lu."""
    commitment_date: date | None
    """Date de livraison souhaitée ; `None` si elle n'a pas pu être lue."""
    order_line: tuple[OrderLine, ...]


@dataclass(frozen=True)
class Summary:
    """Ce qui a été établi d'un document ; `None` pour ce qui ne l'a pas été."""

    partner_id: int | None = None
    client_order_ref: str | None = None
    commitment_date: date | None = None
    line_count: int | None = None
    """Nombre de lignes imprimées sur le document."""
    total_excl_tax: Decimal | None = None
    """Total hors taxes imprimé sur le document."""


@dataclass(frozen=True)
class DocumentResult:
    """Résultat du traitement d'un document."""

    anomalies: tuple[Anomaly, ...]
    """Toutes les anomalies relevées, dans l'ordre des contrôles."""
    summary: Summary = Summary()
    order: Order | None = None
    """La commande produite ; `None` si le document est bloqué."""

    @property
    def status(self) -> Status:
        """Bloqué si une anomalie bloque, sinon avertissement s'il y en a une, sinon accepté."""
        if any(anomaly.blocking for anomaly in self.anomalies):
            return Status.BLOCKED
        return Status.WARNING if self.anomalies else Status.ACCEPTED
