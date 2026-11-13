"""Fiches de référentiel réduites aux colonnes que lisent les recherches, pour les tests."""


def client(client_id: str, name: str, postal_code: str, active: str = "oui") -> dict[str, str]:
    """Fiche client réduite à son identifiant et aux colonnes que lit la recherche."""
    return {"id_client": client_id, "nom": name, "code_postal": postal_code, "actif": active}


def article(sku: str, ean: str) -> dict[str, str]:
    """Fiche article réduite à son SKU et à son EAN."""
    return {"SKU": sku, "EAN": ean}
