"""Tests de l'envoi à Odoo, à blanc, contre un faux serveur XML-RPC local.

Le faux serveur répond sur les deux points d'entrée de l'API externe d'Odoo, `/xmlrpc/2/common`
et `/xmlrpc/2/object`. Il est lié au port 0, que le système remplace par un port libre, et
s'arrête en fin de test.
"""

import ast
import threading
from pathlib import Path
from xmlrpc.client import Fault
from xmlrpc.server import (
    MultiPathXMLRPCServer,
    SimpleXMLRPCDispatcher,
    SimpleXMLRPCRequestHandler,
)

import pytest

import saisie_commandes
from saisie_commandes.odoo import send_order

PACKAGE = Path(saisie_commandes.__file__).parent

DATABASE, LOGIN, PASSWORD, UID = "respire", "adv@respire.example", "secret", 7

PRODUCTS = [
    {"id": 41, "default_code": "DSTPFC50", "name": "Déodorant stick Fleur de coton 50g"},
    {"id": 42, "default_code": "FHINT30-50", "name": "Fluide hydratant intense SPF30 50 mL"},
    {"id": 43, "default_code": "DSTPEC50", "name": "Déodorant stick Embruns Cèdre"},
]
"""Articles de la fausse base Odoo ; leur référence interne est `default_code`."""

ORDER = {
    "partner_id": 10106,
    "client_order_ref": "2026-11-0457",
    "commitment_date": "2026-11-10",
    "order_line": [
        {"product_ref": "FHINT30-50", "product_uom_qty": 12, "price_unit": 18.25, "discount": 35.0},
        {"product_ref": "DSTPFC50", "product_uom_qty": 24, "price_unit": 10.75, "discount": 35.0},
    ],
}
"""Commande au format de l'énoncé."""

CREATED = {
    "partner_id": 10106,
    "client_order_ref": "2026-11-0457",
    "commitment_date": "2026-11-10",
    "order_line": [
        [0, 0, {"product_id": 42, "product_uom_qty": 12, "price_unit": 18.25, "discount": 35.0}],
        [0, 0, {"product_id": 41, "product_uom_qty": 24, "price_unit": 10.75, "discount": 35.0}],
    ],
}
"""Commande de vente que crée l'envoi de `ORDER` : chaque ligne en commande de création
`(0, 0, valeurs)`, son article désigné par son id dans Odoo."""


class FakeOdoo:
    """Ce que fait l'API externe d'Odoo des appels de l'envoi : connexion, articles, commandes."""

    def __init__(self) -> None:
        self.orders: list[dict] = []
        """Valeurs de chaque commande de vente créée."""

    def authenticate(self, database, login, password, user_agent_env):
        """Identifiant de l'utilisateur, ou `False` si la connexion est refusée."""
        return UID if (database, login, password) == (DATABASE, LOGIN, PASSWORD) else False

    def execute_kw(self, database, uid, password, model, method, args, kwargs=None):
        """Appel d'une méthode d'un modèle, au nom d'un utilisateur connecté."""
        if (database, uid, password) != (DATABASE, UID, PASSWORD):
            raise Fault(3, "Access Denied")
        if (model, method) == ("product.product", "search_read"):
            (domain,) = args
            fields = {"id", *((kwargs or {}).get("fields") or PRODUCTS[0].keys())}
            found = [product for product in PRODUCTS if all(matches(product, t) for t in domain)]
            return [{name: product[name] for name in fields} for product in found]
        if (model, method) == ("sale.order", "create"):
            (values,) = args
            self.orders.append(values)
            return 100 + len(self.orders)
        raise Fault(2, f"méthode non simulée : {model}.{method}")


def matches(record: dict, term: list) -> bool:
    """Vrai si `record` satisfait une condition de domaine Odoo, `=` ou `in`."""
    field, operator, value = term
    if operator == "=":
        return record[field] == value
    if operator == "in":
        return record[field] in value
    raise Fault(2, f"opérateur non simulé : {operator}")


class OdooPaths(SimpleXMLRPCRequestHandler):
    """Requêtes HTTP du faux serveur, sur les seuls chemins de l'API externe d'Odoo."""

    rpc_paths = ("/xmlrpc/2/common", "/xmlrpc/2/object")
    timeout = 5
    """Délai d'une connexion, en secondes : un client muet ne bloque pas l'arrêt du serveur."""


@pytest.fixture
def odoo():
    """Faux serveur Odoo démarré dans un fil : rend son URL et son état."""
    fake = FakeOdoo()
    server = MultiPathXMLRPCServer(("127.0.0.1", 0), requestHandler=OdooPaths, logRequests=False)
    for path, function in (
        ("/xmlrpc/2/common", fake.authenticate),
        ("/xmlrpc/2/object", fake.execute_kw),
    ):
        dispatcher = SimpleXMLRPCDispatcher()
        dispatcher.register_function(function)
        server.add_dispatcher(path, dispatcher)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", fake
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_la_commande_est_creee_avec_ses_lignes_et_ses_articles_retrouves_par_reference(odoo):
    url, fake = odoo
    order_id = send_order(ORDER, url, DATABASE, LOGIN, PASSWORD)
    assert (order_id, fake.orders) == (101, [CREATED])


def test_un_article_introuvable_arrete_l_envoi_avant_toute_creation(odoo):
    url, fake = odoo
    unknown = {
        "product_ref": "MASSDECL50",
        "product_uom_qty": 6,
        "price_unit": 16.9,
        "discount": 35.0,
    }
    order = {**ORDER, "order_line": [*ORDER["order_line"], unknown]}
    with pytest.raises(LookupError, match="« MASSDECL50 »"):
        send_order(order, url, DATABASE, LOGIN, PASSWORD)
    assert fake.orders == []


def test_l_envoi_est_la_seule_fonction_de_son_fichier():
    tree = ast.parse((PACKAGE / "odoo.py").read_text(encoding="utf-8"))
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    names = [
        getattr(node, "name", "lambda") for node in ast.walk(tree) if isinstance(node, definitions)
    ]
    assert names == ["send_order"]


def imported(path: Path) -> set[str]:
    """Noms complets de ce qu'importe un fichier source, relatifs compris (« ..odoo »)."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def test_aucun_module_n_importe_l_envoi_a_odoo():
    modules = {path.name: imported(path) for path in PACKAGE.glob("*.py")}
    importers = [
        name for name, names in modules.items() if any("odoo" in n.split(".") for n in names)
    ]
    assert ({"cli.py", "odoo.py"} <= modules.keys(), importers) == (True, [])
