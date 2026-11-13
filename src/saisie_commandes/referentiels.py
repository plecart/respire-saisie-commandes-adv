"""Référentiels clients et articles, interrogés en mémoire par les règles métier.

Une fiche est une ligne d'un CSV du référentiel : un dictionnaire de l'en-tête vers la valeur,
en texte. Le rapprochement d'un client suit l'ADR 0001 § 6 : nom normalisé, égalité stricte,
actifs d'abord, code postal pour départager. L'adresse imprimée n'entre pas dans la recherche :
la fiche fait foi.
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto

type Row = dict[str, str]


class ClientStatus(Enum):
    """Issue de la recherche d'un client."""

    ACTIVE = auto()
    """Une fiche active retenue."""
    INACTIVE = auto()
    """Une fiche inactive retenue, faute de fiche active de ce nom."""
    AMBIGUOUS = auto()
    """Plusieurs fiches de ce nom, que le code postal du document ne départage pas."""
    NOT_FOUND = auto()
    """Aucune fiche de ce nom."""


@dataclass(frozen=True)
class ClientMatch:
    """Résultat de la recherche d'un client : son issue, et la fiche retenue s'il y en a une."""

    status: ClientStatus
    client: Row | None = None


def normalize_name(name: str) -> str:
    """Forme comparable d'un nom de client.

    Majuscules, accents retirés, toute suite de caractères autres que lettres et chiffres
    (ponctuation, symboles, espaces) remplacée par une espace, espaces de début et de fin
    rognées : « Pharmacie de l'Étoile » devient « PHARMACIE DE L ETOILE ».
    """
    # ponytail: NFKD ne décompose pas les ligatures (Œ, Æ) ; une table de translittération
    # le jour où un nom du référentiel en porte.
    decomposed = unicodedata.normalize("NFKD", name)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", " ", unaccented).strip().upper()


class ReferenceData:
    """Fiches clients et articles, indexées pour les recherches des règles métier."""

    def __init__(self, clients: Iterable[Row]) -> None:
        """Indexe les fiches ; un client doit porter `nom`, `code_postal` et `actif`."""
        self._clients_by_name: dict[str, list[Row]] = defaultdict(list)
        for client in clients:
            self._clients_by_name[normalize_name(client["nom"])].append(client)

    def find_client(self, name: str, postal_code: str | None) -> ClientMatch:
        """Cherche le client d'un document par son nom et son code postal imprimés.

        Les noms sont comparés après normalisation (`normalize_name`), parmi les fiches actives
        (`actif` vaut `oui`) ; faute de fiche active de ce nom, parmi les inactives. Une seule
        fiche seule de son nom est retenue même si son code postal diffère de celui du
        document : l'écart revient aux règles métier. Entre plusieurs fiches, seul le code postal départage ; s'il en
        laisse zéro ou plusieurs, la recherche est ambiguë.
        """
        homonyms = self._clients_by_name.get(normalize_name(name), [])
        actives = [client for client in homonyms if client["actif"] == "oui"]
        if actives:
            return _pick(ClientStatus.ACTIVE, actives, postal_code)
        if homonyms:
            return _pick(ClientStatus.INACTIVE, homonyms, postal_code)
        return ClientMatch(ClientStatus.NOT_FOUND)


def _pick(status: ClientStatus, candidates: list[Row], postal_code: str | None) -> ClientMatch:
    """Retient l'unique candidat, ou celui que le code postal désigne parmi plusieurs."""
    if len(candidates) > 1:
        candidates = [client for client in candidates if client["code_postal"] == postal_code]
    if len(candidates) == 1:
        return ClientMatch(status, candidates[0])
    return ClientMatch(ClientStatus.AMBIGUOUS)
