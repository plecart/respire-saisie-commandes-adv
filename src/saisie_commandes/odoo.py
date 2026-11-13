"""Envoi d'une commande à Odoo, par l'API externe XML-RPC.

Écrite, jamais exécutée : aucun chemin du programme ne l'appelle (ADR 0001 § 8), et elle n'est
exercée qu'à blanc, contre un faux serveur. Le MVP s'arrête au JSON au format cible (énoncé,
« Règles du jeu »).
"""

import xmlrpc.client
from collections.abc import Mapping
from typing import Any


def send_order(
    order: Mapping[str, Any], url: str, database: str, username: str, password: str
) -> int:
    """Crée dans Odoo la commande de vente `order`, au format de l'énoncé, et rend son id.

    S'authentifie sur `<url>/xmlrpc/2/common`, puis, sur `<url>/xmlrpc/2/object`, retrouve chaque
    article par sa référence interne (`default_code` de `product.product`) et crée la
    `sale.order` avec ses lignes. Un article introuvable lève `LookupError`, avant toute création.
    """
    uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(
        database, username, password, {}
    )
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    references = [line["product_ref"] for line in order["order_line"]]
    products = models.execute_kw(
        database,
        uid,
        password,
        "product.product",
        "search_read",
        [[("default_code", "in", references)]],
        {"fields": ["default_code"]},
    )
    product_ids = {product["default_code"]: product["id"] for product in products}
    missing = [reference for reference in references if reference not in product_ids]
    if missing:
        raise LookupError(
            "articles introuvables dans Odoo par leur référence interne : "
            + ", ".join(f"« {reference} »" for reference in missing)
        )

    lines = [
        (
            0,
            0,
            {
                "product_id": product_ids[line["product_ref"]],
                "product_uom_qty": line["product_uom_qty"],
                "price_unit": line["price_unit"],
                "discount": line["discount"],
            },
        )
        for line in order["order_line"]
    ]
    values = {
        "partner_id": order["partner_id"],
        "client_order_ref": order["client_order_ref"],
        "commitment_date": order["commitment_date"],
        "order_line": lines,
    }
    return models.execute_kw(database, uid, password, "sale.order", "create", [values])
