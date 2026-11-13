"""Tests du résultat d'un document : le statut se déduit des anomalies."""

import pytest

from saisie_commandes.resultat import Anomaly, DocumentResult, Status, Summary

WARNING = Anomaly("numéro de commande absent", blocking=False)
BLOCKING = Anomaly("EAN inconnu du référentiel", blocking=True, line=5, ean="3760368799912")


@pytest.mark.parametrize(
    ("anomalies", "status"),
    [
        pytest.param((), Status.ACCEPTED, id="aucune-anomalie"),
        pytest.param((WARNING,), Status.WARNING, id="avertissement"),
        pytest.param((WARNING, BLOCKING), Status.BLOCKED, id="une-bloquante-suffit"),
    ],
)
def test_le_statut_se_deduit_des_anomalies(anomalies, status):
    assert DocumentResult(anomalies).status is status


def test_un_document_bloque_s_exprime_sans_rien_d_etabli():
    mail = DocumentResult((Anomaly("mail sans pièce jointe PDF", blocking=True),))
    assert (mail.status, mail.order, mail.summary) == (Status.BLOCKED, None, Summary())
