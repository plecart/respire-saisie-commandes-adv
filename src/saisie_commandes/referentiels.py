"""Référentiels clients et articles, interrogés en mémoire par les règles métier.

Chargés une fois depuis leurs deux CSV (`ReferenceData.load`), ils ne touchent plus le disque.
Une fiche est une ligne d'un CSV du référentiel : un dictionnaire de l'en-tête vers la valeur,
en texte. Le rapprochement d'un client suit l'ADR 0001 § 6 : nom normalisé, égalité stricte,
actifs d'abord, code postal pour départager. L'adresse imprimée n'entre pas dans la recherche :
la fiche fait foi. Un article se retrouve par son seul EAN.
"""

import csv
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Self

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


def is_valid_ean13(code: str) -> bool:
    """Vrai si `code` est un EAN-13 : treize chiffres dont le dernier est la clé de contrôle.

    La clé rend divisible par 10 la somme des treize chiffres pondérés, de gauche à droite,
    par 1 et 3 en alternance.
    """
    if not re.fullmatch(r"[0-9]{13}", code):
        return False
    return sum(int(digit) * (3 if i % 2 else 1) for i, digit in enumerate(code)) % 10 == 0


class ReferenceData:
    """Fiches clients et articles, indexées pour les recherches des règles métier."""

    def __init__(self, clients: Iterable[Row], articles: Iterable[Row]) -> None:
        """Indexe les fiches : un client porte `nom`, `code_postal` et `actif`, un article `EAN`."""
        self._clients_by_name: dict[str, list[Row]] = defaultdict(list)
        for client in clients:
            self._clients_by_name[normalize_name(client["nom"])].append(client)
        self._articles_by_ean = {article["EAN"]: article for article in articles if article["EAN"]}

    @classmethod
    def load(cls, directory: Path) -> Self:
        """Charge `base_clients.csv` et `Respire_base_articles.csv` depuis `directory`, en texte."""
        return cls(
            clients=_read_csv(directory / "base_clients.csv"),
            articles=_read_csv(directory / "Respire_base_articles.csv"),
        )

    def find_client(self, name: str, postal_code: str | None) -> ClientMatch:
        """Cherche le client d'un document par son nom et son code postal imprimés.

        Les noms sont comparés après normalisation (`normalize_name`), parmi les fiches actives
        (`actif` vaut `oui`) ; faute de fiche active de ce nom, parmi les inactives. La fiche
        seule de son nom est retenue même si son code postal diffère de celui du document :
        l'écart revient aux règles métier. Entre plusieurs fiches, seul le code postal
        départage ; s'il en laisse zéro ou plusieurs, la recherche est ambiguë.
        """
        homonyms = self._clients_by_name.get(normalize_name(name), [])
        actives = [client for client in homonyms if client["actif"] == "oui"]
        if actives:
            return _pick(ClientStatus.ACTIVE, actives, postal_code)
        if homonyms:
            return _pick(ClientStatus.INACTIVE, homonyms, postal_code)
        return ClientMatch(ClientStatus.NOT_FOUND)

    def find_article(self, ean: str) -> Row | None:
        """Fiche de l'article portant cet EAN, ou `None`.

        La désignation imprimée n'entre pas dans la recherche, et un article sans EAN au
        référentiel n'est jamais retrouvé. La clé de contrôle se vérifie à part
        (`is_valid_ean13`).
        """
        return self._articles_by_ean.get(ean)


def _read_csv(path: Path) -> list[Row]:
    """Lignes d'un CSV en UTF-8, sans aucune conversion de valeur.

    Un code postal ou un CIP garde son zéro de tête ; la marque d'ordre d'octets qui ouvre le
    fichier articles est retirée, et n'entre pas dans son premier en-tête.
    """
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _pick(status: ClientStatus, candidates: list[Row], postal_code: str | None) -> ClientMatch:
    """Retient l'unique candidat, ou celui que le code postal désigne parmi plusieurs."""
    if len(candidates) > 1:
        candidates = [client for client in candidates if client["code_postal"] == postal_code]
    if len(candidates) == 1:
        return ClientMatch(status, candidates[0])
    return ClientMatch(ClientStatus.AMBIGUOUS)
