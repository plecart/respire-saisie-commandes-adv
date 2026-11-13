"""Tests des référentiels : chargement en texte, rapprochement client, article par EAN."""

from pathlib import Path

import pytest
from fiches import article, client

from saisie_commandes.referentiels import (
    ClientMatch,
    ClientStatus,
    ReferenceData,
    is_valid_ean13,
    normalize_name,
)

REFERENTIELS = Path(__file__).parents[1] / "referentiels"


def with_clients(*clients: dict[str, str]) -> ReferenceData:
    """Référentiels réduits à ces fiches clients."""
    return ReferenceData(clients=clients, articles=())


def with_articles(*articles: dict[str, str]) -> ReferenceData:
    """Référentiels réduits à ces fiches articles."""
    return ReferenceData(clients=(), articles=articles)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Pharmacie du Lac", "PHARMACIE DU LAC", id="casse"),
        pytest.param("PHARMACIE DES ÉCOLES À NÎMES", "PHARMACIE DES ECOLES A NIMES", id="accents"),
        pytest.param("  PHARMACIE \t DU   LAC  ", "PHARMACIE DU LAC", id="espaces"),
        pytest.param(
            "PHARMACIE D'ARMES - ST-PIERRE.", "PHARMACIE D ARMES ST PIERRE", id="ponctuation"
        ),
        pytest.param("PHARMACIE_DU_LAC", "PHARMACIE DU LAC", id="souligne"),
    ],
)
def test_normalisation_du_nom(raw, expected):
    assert normalize_name(raw) == expected


def test_client_retrouve_par_son_nom_normalise():
    etoile = client("10120", "Pharmacie de l'Étoile", "75008")
    found = with_clients(etoile).find_client("PHARMACIE  DE L ETOILE.", "75008")
    assert found == ClientMatch(ClientStatus.ACTIVE, etoile)


def test_client_introuvable():
    lac = client("10110", "PHARMACIE DU LAC", "74000")
    found = with_clients(lac).find_client("PHARMACIE DE LA GARE", "74000")
    assert found == ClientMatch(ClientStatus.NOT_FOUND)


def test_actif_unique_retenu_meme_si_son_code_postal_differe():
    arcades = client("10107", "PHARMACIE DES ARCADES", "62000")
    found = with_clients(arcades).find_client("PHARMACIE DES ARCADES", "59800")
    assert found == ClientMatch(ClientStatus.ACTIVE, arcades)


@pytest.mark.parametrize(
    ("active", "status"),
    [
        pytest.param("oui", ClientStatus.ACTIVE, id="actifs"),
        pytest.param("non", ClientStatus.INACTIVE, id="inactifs"),
    ],
)
def test_homonymes_departages_par_code_postal(active, status):
    lille = client("10101", "PHARMACIE DU BEFFROI", "59800", active)
    douai = client("10109", "PHARMACIE DU BEFFROI", "59500", active)
    found = with_clients(lille, douai).find_client("PHARMACIE DU BEFFROI", "59500")
    assert found == ClientMatch(status, douai)


@pytest.mark.parametrize(
    "postal_code",
    [
        pytest.param("14400", id="aucun-restant"),
        pytest.param("14000", id="plusieurs-restants"),
    ],
)
def test_ambigu_si_le_code_postal_ne_departage_pas(postal_code):
    found = with_clients(
        client("10102", "PHARMACIE DU MARCHE", "14000"),
        client("10116", "PHARMACIE DU MARCHE", "14000"),
        client("10117", "PHARMACIE DU MARCHE", "14200"),
    ).find_client("PHARMACIE DU MARCHE", postal_code)
    assert found == ClientMatch(ClientStatus.AMBIGUOUS)


def test_inactif_retenu_a_defaut_d_actif():
    lac = client("10111", "GRANDE PHARMACIE DU LAC", "74600", active="non")
    found = with_clients(lac).find_client("GRANDE PHARMACIE DU LAC", "74600")
    assert found == ClientMatch(ClientStatus.INACTIVE, lac)


def test_un_actif_l_emporte_sur_un_inactif_du_meme_nom():
    active = client("10103", "GRANDE PHARMACIE DU LAC", "74600")
    inactive = client("10111", "GRANDE PHARMACIE DU LAC", "74000", active="non")
    found = with_clients(active, inactive).find_client("GRANDE PHARMACIE DU LAC", "74000")
    assert found == ClientMatch(ClientStatus.ACTIVE, active)


def test_article_retrouve_par_son_ean():
    shampoing = article("APSHS60", "3000000000014")
    assert with_articles(shampoing).find_article("3000000000014") == shampoing


@pytest.mark.parametrize(
    "ean",
    [
        pytest.param("3000000000021", id="absent-du-referentiel"),
        pytest.param("", id="vide"),
    ],
)
def test_article_inconnu(ean):
    data = with_articles(article("APSHS60", "3000000000014"), article("BELLBOX21", ""))
    assert data.find_article(ean) is None


@pytest.mark.parametrize(
    "ean",
    [
        pytest.param("3000000000014", id="cle-juste"),
        pytest.param("0012345678905", id="zero-de-tete"),
    ],
)
def test_cle_ean13_valide(ean):
    assert is_valid_ean13(ean)


@pytest.mark.parametrize(
    "ean",
    [
        pytest.param("3000000000015", id="cle-fausse"),
        # Somme pondérée divisible par 10 : seule la longueur écarte ces deux-là.
        pytest.param("300000000009", id="douze-chiffres"),
        pytest.param("30000000000140", id="quatorze-chiffres"),
        pytest.param("300000000001A", id="lettre"),
    ],
)
def test_cle_ean13_invalide(ean):
    assert not is_valid_ean13(ean)


def test_premier_en_tete_des_articles_lu_sans_marque_d_ordre_d_octets():
    shampoing = ReferenceData.load(REFERENTIELS).find_article("3000000000014")
    assert next(iter(shampoing)) == "RAYON"


def test_client_du_vrai_referentiel_retrouve_par_nom_et_code_postal():
    found = ReferenceData.load(REFERENTIELS).find_client("Pharmacie du Beffroi", "59500")
    assert (found.status, found.client["id_client"]) == (ClientStatus.ACTIVE, "10109")


def test_un_zero_de_tete_est_conserve(tmp_path):
    (tmp_path / "base_clients.csv").write_text(
        "id_client,cip,nom,code_postal,actif\n10201,0299201,PHARMACIE DE L AIN,01000,oui\n",
        encoding="utf-8",
    )
    (tmp_path / "Respire_base_articles.csv").write_text("SKU,EAN\n", encoding="utf-8")
    ain = ReferenceData.load(tmp_path).find_client("PHARMACIE DE L AIN", "01000").client
    assert (ain["cip"], ain["code_postal"]) == ("0299201", "01000")
