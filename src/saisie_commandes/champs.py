"""Schéma des champs bruts : ce que l'extraction lit sur un document et rend aux règles métier.

Contrat entre l'extraction et les règles (ADR 0001 § 3) : le modèle extrait, le code décide. Chaque
valeur est rendue en texte, telle qu'imprimée (« 10,75 », « 35 % », « 23.01.2026 »), et ce sont
les règles qui l'analysent. Une valeur imprimée prend l'une de trois formes (`Printed`) :

- le texte imprimé ;
- `None` (`null` en JSON) : la valeur n'est pas imprimée — colonne vide, champ absent ;
- `ILLEGIBLE` (`{"illegible": true}` en JSON) : la valeur est imprimée mais illisible.

Le schéma est strict : tout champ est requis, et un champ inconnu est refusé. Il s'exporte en
JSON Schema (`RawFields.model_json_schema()`) pour contraindre la sortie de l'extraction ; les
docstrings des attributs y deviennent les descriptions des champs.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Schema(BaseModel):
    """Base des modèles du contrat : stricts, immuables, décrits par leurs docstrings."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class Illegible(_Schema):
    """Valeur imprimée mais illisible : elle n'est jamais devinée."""

    illegible: Literal[True]
    """Toujours vrai : marque la valeur comme illisible."""


ILLEGIBLE = Illegible(illegible=True)
"""Le marqueur d'une valeur illisible."""

type Printed = Annotated[
    str | Illegible | None,
    Field(
        description="Valeur telle qu'imprimée : le texte lu ; null si elle n'est pas imprimée ; "
        '{"illegible": true} si elle est imprimée mais illisible.'
    ),
]


class DocumentType(StrEnum):
    """Nature d'un document reçu."""

    ORDER = "commande"
    INVOICE = "facture"
    OTHER = "autre"


class RawLine(_Schema):
    """Une ligne de commande, telle qu'imprimée. La désignation n'est pas extraite."""

    ean: Printed
    """EAN de l'article."""
    quantity: Printed
    """Quantité commandée."""
    unit: Printed
    """Unité de la quantité (« UN », « COL6 »)."""
    free_units: Printed
    """Unités gratuites."""
    catalog_price: Printed
    """Prix catalogue unitaire, avant remise."""
    discounts: list[str | Illegible]
    """Remises renseignées sur la ligne, une par colonne de remise ; vide si aucune."""
    line_total: Printed
    """Total de la ligne, hors taxes."""


class RawFields(_Schema):
    """Les champs bruts d'un document. Texte libre et annotations manuscrites ne sont pas lus."""

    document_type: DocumentType
    """Nature du document : bon de commande, facture ou autre."""
    pharmacy_name: Printed
    """Nom de la pharmacie qui passe la commande."""
    postal_code: Printed
    """Code postal de la pharmacie."""
    order_number: Printed
    """Numéro de commande de la pharmacie."""
    delivery_date: Printed
    """Date de livraison souhaitée."""
    total_excl_tax: Printed
    """Total hors taxes du document."""
    lines: list[RawLine]
    """Lignes de commande, dans l'ordre du document."""
