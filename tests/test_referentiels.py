"""Tests des référentiels : normalisation des noms et rapprochement client."""

import pytest

from saisie_commandes.referentiels import ClientMatch, ClientStatus, ReferenceData, normalize_name


def client(client_id: str, name: str, postal_code: str, active: str = "oui") -> dict[str, str]:
    """Fiche client réduite aux colonnes du référentiel que lit la recherche."""
    return {"id_client": client_id, "nom": name, "code_postal": postal_code, "actif": active}


def with_clients(*clients: dict[str, str]) -> ReferenceData:
    """Référentiels réduits à ces fiches clients."""
    return ReferenceData(clients=clients)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("Pharmacie du Lac", "PHARMACIE DU LAC", id="casse"),
        pytest.param("PHARMACIE DES ÉCOLES À NÎMES", "PHARMACIE DES ECOLES A NIMES", id="accents"),
        pytest.param("  PHARMACIE \t DU   LAC  ", "PHARMACIE DU LAC", id="espaces"),
        pytest.param(
            "PHARMACIE D'ARMES - ST-PIERRE.", "PHARMACIE D ARMES ST PIERRE", id="ponctuation"
        ),
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
