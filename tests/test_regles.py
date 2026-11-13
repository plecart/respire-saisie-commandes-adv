"""Tests des règles métier, par leur seule interface : champs bruts et référentiels en entrée,
résultat du document en sortie. La table des statuts est celle du PRD #1, ligne « mail » exclue.
"""

from datetime import date
from decimal import Decimal

import pytest
from fiches import article, client

from saisie_commandes.champs import ILLEGIBLE, DocumentType, RawFields, RawLine
from saisie_commandes.referentiels import ReferenceData
from saisie_commandes.regles import apply_rules
from saisie_commandes.resultat import Anomaly, DocumentResult, Order, OrderLine, Status, Summary

EAN = "3760368740730"

REFERENCES = ReferenceData(
    clients=[
        client("10106", "PHARMACIE DU VIEUX LILLE", "59800"),
        client("10102", "PHARMACIE DU MARCHE", "14000"),
        client("10108", "PHARMACIE DU MARCHE", "14400"),
        client("10103", "GRANDE PHARMACIE DU LAC", "74600"),
        client("10111", "GRANDE PHARMACIE DU LAC", "74600", active="non"),
        client("10120", "PHARMACIE DES REMPARTS", "35400", active="non"),
        client("10121", "PHARMACIE DU PORT", "13002"),
        client("10122", "PHARMACIE DU PORT", "13002"),
    ],
    articles=[
        article("DSTPFC50", EAN),
        article("DSTPEC50", "3760368742338"),
        article("FHINT30-50", "3760368742383"),
        article("SLSPF20", "3000000001271"),
    ],
)


def line(**printed) -> RawLine:
    """Ligne juste de 12 sticks Fleur de coton à 10,75 remisés à 35 % ; `printed` la modifie."""
    fields = {
        "ean": EAN,
        "quantity": "12",
        "unit": None,
        "free_units": None,
        "catalog_price": "10,75",
        "discounts": ["35%"],
        "line_total": "83,85",
    }
    return RawLine(**(fields | printed))


def document(*lines: RawLine, **printed) -> RawFields:
    """Bon de commande juste de la Pharmacie du Vieux Lille, d'une ligne par défaut.

    `printed` modifie l'en-tête ; il remplace aussi les lignes (`lines=[]`).
    """
    fields = {
        "document_type": DocumentType.ORDER,
        "pharmacy_name": "PHARMACIE DU VIEUX LILLE",
        "postal_code": "59800",
        "order_number": "2026-11-0457",
        "delivery_date": "10/11/2026",
        "total_excl_tax": "83,85",
        "lines": list(lines or [line()]),
    }
    return RawFields(**(fields | printed))


def blocking(message: str, line_number: int | None = None, ean: str | None = None) -> Anomaly:
    """Anomalie bloquante, située sur une ligne quand `line_number` est donné."""
    return Anomaly(message, blocking=True, line=line_number, ean=ean)


def on_line(message: str, ean: str | None = EAN) -> Anomaly:
    """Anomalie bloquante de la première ligne."""
    return blocking(message, line_number=1, ean=ean)


def warning(message: str) -> Anomaly:
    """Anomalie d'avertissement, qui porte sur le document."""
    return Anomaly(message, blocking=False)


@pytest.mark.parametrize(
    ("fields", "status", "anomalies"),
    [
        pytest.param(
            document(document_type=DocumentType.INVOICE),
            Status.BLOCKED,
            [blocking("n'est pas un bon de commande")],
            id="pas-un-bon-de-commande-facture",
        ),
        pytest.param(
            document(document_type=DocumentType.OTHER),
            Status.BLOCKED,
            [blocking("n'est pas un bon de commande")],
            id="pas-un-bon-de-commande-autre",
        ),
        pytest.param(
            document(pharmacy_name="PHARMACIE DE LA GARE"),
            Status.BLOCKED,
            [blocking("client introuvable : « PHARMACIE DE LA GARE »")],
            id="client-introuvable",
        ),
        pytest.param(
            document(pharmacy_name=None),
            Status.BLOCKED,
            [blocking("nom de la pharmacie absent")],
            id="client-introuvable-nom-absent",
        ),
        pytest.param(
            document(pharmacy_name=ILLEGIBLE),
            Status.BLOCKED,
            [blocking("nom de la pharmacie illisible")],
            id="client-introuvable-nom-illisible",
        ),
        pytest.param(
            document(pharmacy_name="PHARMACIE DU PORT", postal_code="13002"),
            Status.BLOCKED,
            [
                blocking(
                    "client ambigu : plusieurs fiches « PHARMACIE DU PORT » "
                    "que le code postal ne départage pas"
                )
            ],
            id="client-ambigu",
        ),
        pytest.param(
            document(line(ean=None)),
            Status.BLOCKED,
            [on_line("EAN absent", ean=None)],
            id="ean-absent",
        ),
        pytest.param(
            document(line(ean=ILLEGIBLE)),
            Status.BLOCKED,
            [on_line("EAN illisible", ean=None)],
            id="ean-illisible",
        ),
        pytest.param(
            document(line(ean="3760368740731")),
            Status.BLOCKED,
            [on_line("EAN-13 invalide", ean="3760368740731")],
            id="ean-cle-invalide",
        ),
        pytest.param(
            document(line(ean="3760368799912")),
            Status.BLOCKED,
            [on_line("EAN inconnu du référentiel", ean="3760368799912")],
            id="ean-inconnu",
        ),
        pytest.param(
            document(line(quantity=None)),
            Status.BLOCKED,
            [on_line("quantité absente")],
            id="quantite-absente",
        ),
        pytest.param(
            document(line(quantity=ILLEGIBLE)),
            Status.BLOCKED,
            [on_line("quantité illisible")],
            id="quantite-illisible",
        ),
        pytest.param(
            document(line(quantity="1O")),
            Status.BLOCKED,
            [on_line("quantité illisible : « 1O »")],
            id="quantite-illisible-mal-lue",
        ),
        pytest.param(
            document(line(quantity="2,5")),
            Status.BLOCKED,
            [on_line("quantité illisible : « 2,5 »")],
            id="quantite-illisible-non-entiere",
        ),
        pytest.param(
            document(line(catalog_price=None)),
            Status.BLOCKED,
            [on_line("prix catalogue absent")],
            id="prix-absent",
        ),
        pytest.param(
            document(line(catalog_price=ILLEGIBLE)),
            Status.BLOCKED,
            [on_line("prix catalogue illisible")],
            id="prix-illisible",
        ),
        pytest.param(
            document(line(line_total=None)),
            Status.BLOCKED,
            [on_line("total de ligne absent")],
            id="total-de-ligne-absent",
        ),
        pytest.param(
            document(line(line_total=ILLEGIBLE)),
            Status.BLOCKED,
            [on_line("total de ligne illisible")],
            id="total-de-ligne-illisible",
        ),
        pytest.param(
            document(total_excl_tax=None),
            Status.BLOCKED,
            [blocking("total HT absent")],
            id="total-du-document-absent",
        ),
        pytest.param(
            document(total_excl_tax=ILLEGIBLE),
            Status.BLOCKED,
            [blocking("total HT illisible")],
            id="total-du-document-illisible",
        ),
        pytest.param(
            document(line(unit="COL6")),
            Status.BLOCKED,
            [on_line("quantité en colis : « COL6 »")],
            id="quantite-en-colis",
        ),
        pytest.param(
            document(line(unit="colis de 6")),
            Status.BLOCKED,
            [on_line("quantité en colis : « colis de 6 »")],
            id="quantite-en-colis-en-minuscules",
        ),
        pytest.param(
            document(line(free_units="2")),
            Status.BLOCKED,
            [on_line("unités gratuites : « 2 »")],
            id="unites-gratuites",
        ),
        pytest.param(
            # 12 × 10,75 × 0,65 × 0,95 = 79,66 : aucune des deux remises seule ne le redonne.
            document(line(discounts=["35%", "5%"], line_total="79,66"), total_excl_tax="79,66"),
            Status.BLOCKED,
            [on_line("plusieurs remises : « 35% », « 5% »")],
            id="deux-remises",
        ),
        pytest.param(
            document(line(line_total="83,87"), total_excl_tax="83,87"),
            Status.BLOCKED,
            [on_line("total de ligne incohérent : « 83,87 » imprimé, 83,85 calculé")],
            id="total-de-ligne-incoherent",
        ),
        pytest.param(
            document(total_excl_tax="83,87"),
            Status.BLOCKED,
            [blocking("total HT incohérent : « 83,87 » imprimé, 83,85 pour la somme des lignes")],
            id="total-du-document-incoherent",
        ),
        pytest.param(
            document(lines=[], total_excl_tax="0,00"),
            Status.BLOCKED,
            [blocking("aucune ligne de commande")],
            id="aucune-ligne",
        ),
        pytest.param(
            document(order_number=None),
            Status.WARNING,
            [warning("numéro de commande absent")],
            id="numero-de-commande-absent",
        ),
        pytest.param(
            document(order_number=ILLEGIBLE),
            Status.WARNING,
            [warning("numéro de commande absent")],
            id="numero-de-commande-illisible",
        ),
        pytest.param(
            document(order_number="0"),
            Status.WARNING,
            [warning("numéro de commande à « 0 »")],
            id="numero-de-commande-a-zero",
        ),
        pytest.param(
            document(delivery_date=None),
            Status.WARNING,
            [warning("date de livraison absente")],
            id="date-absente",
        ),
        pytest.param(
            document(delivery_date=ILLEGIBLE),
            Status.WARNING,
            [warning("date de livraison absente")],
            id="date-illisible",
        ),
        pytest.param(
            document(delivery_date="31/02/2026"),
            Status.WARNING,
            [warning("date de livraison mal formée ou sans année : « 31/02/2026 »")],
            id="date-mal-formee",
        ),
        pytest.param(
            document(delivery_date="10/11"),
            Status.WARNING,
            [warning("date de livraison mal formée ou sans année : « 10/11 »")],
            id="date-sans-annee",
        ),
        pytest.param(
            document(postal_code="59000"),
            Status.WARNING,
            [warning("code postal du document (59000) différent de la fiche (59800)")],
            id="code-postal-different",
        ),
        pytest.param(
            document(pharmacy_name="PHARMACIE DES REMPARTS", postal_code="35400"),
            Status.WARNING,
            [warning("client retenu parmi les inactifs (10120)")],
            id="client-inactif",
        ),
        pytest.param(
            document(
                line(catalog_price="0,00 €", discounts=["--"], line_total="0,00 €"),
                total_excl_tax="0,00 €",
            ),
            Status.ACCEPTED,
            [],
            id="prix-catalogue-a-zero",
        ),
        pytest.param(
            document(delivery_date="13/01/2020"),
            Status.ACCEPTED,
            [],
            id="date-passee",
        ),
        pytest.param(
            # Les champs bruts ne portent aucune désignation (test_champs refuse le champ) :
            # celle qu'imprime le document, différente ou non, ne change rien.
            document(),
            Status.ACCEPTED,
            [],
            id="designation-differente",
        ),
    ],
)
def test_table_des_statuts(fields, status, anomalies):
    result = apply_rules(fields, REFERENCES)
    assert (result.status, list(result.anomalies), result.order is None) == (
        status,
        anomalies,
        status is Status.BLOCKED,
    )


def test_un_document_qui_n_est_pas_une_commande_s_arrete_a_cette_anomalie():
    invoice = document(
        line(ean=None, quantity=ILLEGIBLE),
        document_type=DocumentType.INVOICE,
        pharmacy_name="RESPIRE SAS",
        order_number=None,
        total_excl_tax="543,89",
    )
    assert apply_rules(invoice, REFERENCES) == DocumentResult(
        (blocking("n'est pas un bon de commande"),)
    )


def test_un_bon_accepte_produit_sa_commande():
    fields = document(
        line(),
        line(ean="3760368742338", quantity="24", discounts=["0"], line_total="258,00"),
        total_excl_tax="341,85",
    )
    assert apply_rules(fields, REFERENCES) == DocumentResult(
        anomalies=(),
        summary=Summary(10106, "2026-11-0457", date(2026, 11, 10), 2, Decimal("341.85")),
        order=Order(
            partner_id=10106,
            client_order_ref="2026-11-0457",
            commitment_date=date(2026, 11, 10),
            order_line=(
                OrderLine("DSTPFC50", 12, Decimal("10.75"), Decimal(35)),
                OrderLine("DSTPEC50", 24, Decimal("10.75"), Decimal(0)),
            ),
        ),
    )


def test_un_document_bloque_garde_toutes_ses_anomalies_et_ce_qui_a_ete_etabli():
    """Commande_5 : un EAN absent, une quantité en colis, un EAN inconnu.

    La ligne en colis n'est pas recalculée : son total imprimé compte 2 colis de 6 unités.
    """
    fields = document(
        line(quantity="24", line_total="167,70"),
        line(ean="3760368742338"),
        line(ean=None, quantity="6", catalog_price="17,45", line_total="68,06"),
        line(
            ean="3760368742383",
            quantity="2",
            unit="COL6",
            catalog_price="18,25",
            line_total="142,35",
        ),
        line(ean="3760368799912", quantity="6", catalog_price="16,90", line_total="65,91"),
        line(
            ean="3000000001271",
            catalog_price="9,90",
            discounts=["38%"],
            line_total="73,66",
        ),
        total_excl_tax="601,53",
    )
    assert apply_rules(fields, REFERENCES) == DocumentResult(
        anomalies=(
            blocking("EAN absent", line_number=3),
            blocking("quantité en colis : « COL6 »", line_number=4, ean="3760368742383"),
            blocking("EAN inconnu du référentiel", line_number=5, ean="3760368799912"),
        ),
        summary=Summary(10106, "2026-11-0457", date(2026, 11, 10), 6, Decimal("601.53")),
    )


def test_les_anomalies_suivent_l_ordre_du_document_avertissements_compris():
    fields = document(
        line(),
        line(ean="3760368799912"),
        postal_code="59000",
        order_number="0",
        delivery_date=None,
        total_excl_tax="83,85",
    )
    assert apply_rules(fields, REFERENCES).anomalies == (
        warning("code postal du document (59000) différent de la fiche (59800)"),
        warning("numéro de commande à « 0 »"),
        warning("date de livraison absente"),
        blocking("EAN inconnu du référentiel", line_number=2, ean="3760368799912"),
        blocking("total HT incohérent : « 83,85 » imprimé, 167,70 pour la somme des lignes"),
    )


@pytest.mark.parametrize(
    ("name", "postal_code", "partner_id", "status"),
    [
        pytest.param(
            "Pharmacie du  Vieux-Lille.", "59800", 10106, Status.ACCEPTED, id="nom-normalise"
        ),
        pytest.param(
            "PHARMACIE DU MARCHE", "14400", 10108, Status.ACCEPTED, id="homonymes-departages"
        ),
        pytest.param(
            "GRANDE PHARMACIE DU LAC", "74600", 10103, Status.ACCEPTED, id="actif-d-abord"
        ),
        pytest.param("PHARMACIE DES REMPARTS", "35400", 10120, Status.WARNING, id="inactif-retenu"),
        pytest.param("PHARMACIE DU MARCHE", "75001", None, Status.BLOCKED, id="ambigu-sans-code"),
        pytest.param("PHARMACIE DU PORT", "13002", None, Status.BLOCKED, id="ambigu-meme-code"),
    ],
)
def test_rapprochement_du_client(name, postal_code, partner_id, status):
    result = apply_rules(document(pharmacy_name=name, postal_code=postal_code), REFERENCES)
    assert (result.summary.partner_id, result.status) == (partner_id, status)


def test_un_code_postal_illisible_ne_confirme_pas_la_fiche():
    result = apply_rules(document(postal_code=ILLEGIBLE), REFERENCES)
    assert result.anomalies == (
        warning("code postal du document (absent ou illisible) différent de la fiche (59800)"),
    )


@pytest.mark.parametrize(
    ("printed", "status"),
    [
        # 6 × 9,75 × 0,65 = 38,025 : 38,03 au demi supérieur, 38,02 au demi pair.
        pytest.param("38,04", Status.ACCEPTED, id="un-centime-au-dessus-du-demi-superieur"),
        pytest.param("38,01", Status.BLOCKED, id="deux-centimes-sous-le-demi-superieur"),
    ],
)
def test_arrondi_au_demi_superieur(printed, status):
    fields = document(
        line(quantity="6", catalog_price="9,75", line_total=printed), total_excl_tax=printed
    )
    assert apply_rules(fields, REFERENCES).status is status


@pytest.mark.parametrize(
    ("printed", "status"),
    [
        pytest.param("83,86", Status.ACCEPTED, id="plus-un-centime"),
        pytest.param("83,84", Status.ACCEPTED, id="moins-un-centime"),
        pytest.param("83,87", Status.BLOCKED, id="plus-deux-centimes"),
        pytest.param("83,83", Status.BLOCKED, id="moins-deux-centimes"),
    ],
)
def test_tolerance_d_un_centime_sur_la_ligne(printed, status):
    fields = document(line(line_total=printed), total_excl_tax=printed)
    assert apply_rules(fields, REFERENCES).status is status


@pytest.mark.parametrize(
    ("printed", "status"),
    [
        pytest.param("83,86", Status.ACCEPTED, id="plus-un-centime"),
        pytest.param("83,84", Status.ACCEPTED, id="moins-un-centime"),
        pytest.param("83,87", Status.BLOCKED, id="plus-deux-centimes"),
        pytest.param("83,83", Status.BLOCKED, id="moins-deux-centimes"),
    ],
)
def test_tolerance_d_un_centime_sur_le_document(printed, status):
    assert apply_rules(document(total_excl_tax=printed), REFERENCES).status is status


@pytest.mark.parametrize(
    ("quantity", "price", "discounts", "total", "order_line"),
    [
        pytest.param(
            "9",
            "9,25 €",
            ["35,00 %"],
            "54,11 €",
            OrderLine("DSTPFC50", 9, Decimal("9.25"), Decimal(35)),
            id="commande-1-euros-et-pourcentage",
        ),
        pytest.param(
            "6",
            "0,00 €",
            ["--"],
            "0,00 €",
            OrderLine("DSTPFC50", 6, Decimal(0), Decimal(0)),
            id="commande-1-remise-en-tirets",
        ),
        pytest.param(
            "9",
            "9,750",
            [],
            "87,750",
            OrderLine("DSTPFC50", 9, Decimal("9.75"), Decimal(0)),
            id="commande-2-trois-decimales-sans-remise",
        ),
        pytest.param(
            "24",
            "10,75",
            ["0"],
            "258,00",
            OrderLine("DSTPFC50", 24, Decimal("10.75"), Decimal(0)),
            id="commande-3-remise-nulle",
        ),
        pytest.param(
            "12",
            "9,90",
            ["38%"],
            "73,66",
            OrderLine("DSTPFC50", 12, Decimal("9.90"), Decimal(38)),
            id="commande-5-pourcentage-colle",
        ),
        pytest.param(
            "12,00",
            "1 592,99",
            [],
            "19 115,88",
            OrderLine("DSTPFC50", 12, Decimal("1592.99"), Decimal(0)),
            id="separateur-de-milliers-et-quantite-decimale-entiere",
        ),
        pytest.param(
            "12",
            "10.75",
            ["35.0%"],
            "83.85",
            OrderLine("DSTPFC50", 12, Decimal("10.75"), Decimal(35)),
            id="point-decimal",
        ),
    ],
)
def test_les_valeurs_imprimees_des_documents_fournis_se_lisent(
    quantity, price, discounts, total, order_line
):
    printed = line(quantity=quantity, catalog_price=price, discounts=discounts, line_total=total)
    result = apply_rules(document(printed, total_excl_tax=total), REFERENCES)
    assert result.order.order_line == (order_line,)


@pytest.mark.parametrize(
    ("printed", "commitment_date"),
    [
        pytest.param("23.01.2026", date(2026, 1, 23), id="points"),
        pytest.param("20/01/2026", date(2026, 1, 20), id="barres"),
        pytest.param("20-01-2026", date(2026, 1, 20), id="tirets"),
        pytest.param("20/01/26", date(2026, 1, 20), id="annee-sur-deux-chiffres"),
        pytest.param("10/11", None, id="sans-annee-laissee-vide"),
    ],
)
def test_date_de_livraison_lue_au_format_d_odoo(printed, commitment_date):
    order = apply_rules(document(delivery_date=printed), REFERENCES).order
    assert order.commitment_date == commitment_date


@pytest.mark.parametrize(
    ("printed", "client_order_ref"),
    [
        pytest.param("156006", "156006", id="repris-tel-quel"),
        pytest.param("0", "0", id="zero-repris-tel-quel"),
        pytest.param(None, None, id="absent-laisse-vide"),
        pytest.param(ILLEGIBLE, None, id="illisible-laisse-vide"),
    ],
)
def test_numero_de_commande_repris_tel_quel(printed, client_order_ref):
    order = apply_rules(document(order_number=printed), REFERENCES).order
    assert order.client_order_ref == client_order_ref


@pytest.mark.parametrize(
    ("printed", "anomaly"),
    [
        pytest.param({"discounts": [ILLEGIBLE]}, on_line("remise illisible"), id="remise"),
        pytest.param(
            {"discounts": ["3S%"]}, on_line("remise illisible : « 3S% »"), id="remise-mal-lue"
        ),
        pytest.param(
            {"catalog_price": "-10,75"},
            on_line("prix catalogue illisible : « -10,75 »"),
            id="prix-negatif",
        ),
        pytest.param({"unit": ILLEGIBLE}, on_line("unité illisible"), id="unite"),
        pytest.param(
            {"free_units": ILLEGIBLE},
            on_line("nombre d'unités gratuites illisible"),
            id="unites-gratuites",
        ),
    ],
)
def test_une_valeur_illisible_n_est_jamais_devinee(printed, anomaly):
    assert apply_rules(document(line(**printed)), REFERENCES).anomalies == (anomaly,)


@pytest.mark.parametrize(
    ("quantity", "amount", "anomalies"),
    [
        pytest.param("1.000", "0,00", [on_line("quantité illisible : « 1.000 »")], id="quantite"),
        pytest.param(
            "1",
            "1.000",
            [
                on_line("prix catalogue illisible : « 1.000 »"),
                on_line("total de ligne illisible : « 1.000 »"),
                blocking("total HT illisible : « 1.000 »"),
            ],
            id="montants",
        ),
    ],
)
def test_un_point_suivi_de_trois_chiffres_est_ambigu(quantity, amount, anomalies):
    """« 1.000 » vaut 1 ou 1000 selon que le point est décimal ou de milliers : rien n'est deviné.

    Lu 1, il passerait inaperçu : avec un prix nul, ou partout à la fois dans les montants.
    """
    printed = line(quantity=quantity, catalog_price=amount, discounts=[], line_total=amount)
    fields = document(printed, total_excl_tax=amount)
    assert list(apply_rules(fields, REFERENCES).anomalies) == anomalies


@pytest.mark.parametrize(
    ("unit", "anomaly"),
    [
        pytest.param("COL6", "quantité en colis : « COL6 »", id="colis"),
        pytest.param(ILLEGIBLE, "unité illisible", id="unite-illisible"),
    ],
)
def test_une_quantite_qui_n_est_pas_en_unites_n_est_pas_recalculee(unit, anomaly):
    """2 colis de 6 à 18,25 remisés à 35 % : 2 × 18,25 × 0,65 ne redonne pas les 142,35 imprimés."""
    printed = line(quantity="2", unit=unit, catalog_price="18,25", line_total="142,35")
    fields = document(printed, total_excl_tax="142,35")
    assert apply_rules(fields, REFERENCES).anomalies == (on_line(anomaly),)


def test_une_remise_imprimee_a_zero_compte_parmi_plusieurs_remises():
    fields = document(line(discounts=["35%", "0,00 %"]))
    assert apply_rules(fields, REFERENCES).anomalies == (
        on_line("plusieurs remises : « 35% », « 0,00 % »"),
    )


def test_des_unites_gratuites_a_zero_n_en_sont_pas():
    assert apply_rules(document(line(free_units="0")), REFERENCES).status is Status.ACCEPTED
