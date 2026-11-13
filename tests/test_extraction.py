"""Tests de la lecture d'un document par Claude, sans aucun appel à l'API.

Le client de l'API est simulé (`FakeClient`) ; ses réponses sont des messages du SDK et ses
erreurs les exceptions du SDK, construites ici.
"""

import base64
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pymupdf
import pytest
from extractions import extraction

from saisie_commandes.champs import RawFields
from saisie_commandes.extraction import (
    _INSTRUCTIONS,
    ExtractionError,
    MissingApiKey,
    claude_extractor,
    extractor_from_environment,
)

EXEMPLES = Path(__file__).parents[1] / "exemples"
COMMANDE_3 = EXEMPLES / "Commande_3.pdf"
ANSWER = extraction("Commande_3")
"""Champs bruts attendus de Commande_3, en JSON : la réponse d'une lecture réussie."""
MODEL = "claude-test"
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def reply(text: str, stop_reason: str = "end_turn") -> anthropic.types.Message:
    """Réponse de l'API, telle que le SDK la rend : un seul bloc de texte."""
    return anthropic.types.Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": MODEL,
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    )


class FakeClient:
    """Faux client de l'API : enregistre chaque requête, puis rend sa réponse ou lève son erreur."""

    def __init__(self, outcome: anthropic.types.Message | Exception) -> None:
        self.outcome = outcome
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request) -> anthropic.types.Message:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def status_error(
    error_class: type[anthropic.APIStatusError], status: int
) -> anthropic.APIStatusError:
    """Erreur de statut du SDK, avec le corps d'erreur que renvoie l'API."""
    body = {"type": "error", "error": {"type": "error", "message": "message de l'API"}}
    response = httpx2.Response(status, request=REQUEST, json=body)
    return error_class(f"Error code: {status}", response=response, body=body)


def read_with(
    outcome: anthropic.types.Message | Exception, document: Path = COMMANDE_3
) -> tuple[ExtractionError, FakeClient]:
    """Lit `document` avec un faux client ; rend l'erreur d'extraction levée et le client."""
    client = FakeClient(outcome)
    with pytest.raises(ExtractionError) as raised:
        claude_extractor(client, MODEL)(document)
    return raised.value, client


def request_for(document: Path = COMMANDE_3) -> dict:
    """La requête, unique, qu'envoie la lecture réussie de `document`."""
    client = FakeClient(reply(ANSWER))
    claude_extractor(client, MODEL)(document)
    (request,) = client.requests
    return request


def portrait(image: bytes) -> bool:
    """Vrai si l'image est plus haute que large."""
    pixmap = pymupdf.Pixmap(image)
    return pixmap.width < pixmap.height


def descriptions(schema: object) -> Counter[str]:
    """Les descriptions d'un JSON Schema, à toute profondeur, comptées à chaque occurrence."""
    if isinstance(schema, list):
        return sum(map(descriptions, schema), Counter())
    if not isinstance(schema, dict):
        return Counter()
    found = Counter([schema["description"]] if isinstance(schema.get("description"), str) else [])
    return sum(map(descriptions, schema.values()), found)


def unwrapped(schema: object) -> object:
    """`schema`, chaque `anyOf` à une seule branche remplacé par cette branche."""
    if isinstance(schema, list):
        return [unwrapped(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if len(schema.get("anyOf", ())) == 1:
        return unwrapped(schema["anyOf"][0])
    return {key: unwrapped(value) for key, value in schema.items()}


def test_un_document_est_lu_en_un_seul_appel_qui_rend_ses_champs_bruts():
    client = FakeClient(reply(ANSWER))
    fields = claude_extractor(client, MODEL)(COMMANDE_3)
    assert (fields, len(client.requests)) == (RawFields.model_validate_json(ANSWER), 1)


def test_la_requete_nomme_le_modele_et_contraint_la_sortie_au_schema_des_champs_bruts():
    """Le schéma envoyé est celui du SDK, chaque référence décrite enveloppée dans un `anyOf`."""
    request = request_for()
    assert (request["model"], unwrapped(request["output_config"])) == (
        MODEL,
        {"format": {"type": "json_schema", "schema": anthropic.transform_schema(RawFields)}},
    )


def test_le_schema_envoye_porte_chaque_description_des_champs_bruts():
    """Chaque occurrence compte : deux champs de même description ne se confondent pas."""
    sent = descriptions(request_for()["output_config"])
    assert descriptions(RawFields.model_json_schema()) - sent == Counter()


def test_la_requete_porte_les_instructions_et_plafonne_la_reponse():
    request = request_for()
    assert (request["system"], request["max_tokens"]) == (_INSTRUCTIONS, 16_000)


def test_les_pages_partent_en_png_dans_l_ordre_du_document_puis_la_consigne(tmp_path):
    document = tmp_path / "deux_pages.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page(width=200, height=300)
        pdf.new_page(width=300, height=200)
        pdf.save(document)
    (message,) = request_for(document)["messages"]
    *images, prompt = message["content"]
    pages = [
        (image["source"]["media_type"], portrait(base64.b64decode(image["source"]["data"])))
        for image in images
    ]
    assert (message["role"], pages, prompt["type"]) == (
        "user",
        [("image/png", True), ("image/png", False)],
        "text",
    )


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=REQUEST),
        anthropic.APITimeoutError(request=REQUEST),
        status_error(anthropic.RequestTimeoutError, 408),
        status_error(anthropic.ConflictError, 409),
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.InternalServerError, 500),
        status_error(anthropic.OverloadedError, 529),
    ],
    ids=["connexion", "delai depasse", "408", "409", "429", "500", "529"],
)
def test_une_erreur_temporaire_de_claude_bloque_le_document_sans_reessai_propre(error):
    """Erreurs temporaires : celles que le SDK réessaie de lui-même avant de les lever."""
    extraction_error, client = read_with(error)
    assert (str(extraction_error), extraction_error.__cause__, len(client.requests)) == (
        "Claude indisponible, relancer le document",
        error,
        1,
    )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            status_error(anthropic.BadRequestError, 400),
            "requête refusée par Claude : message de l'API",
        ),
        (status_error(anthropic.AuthenticationError, 401), "clé d'API refusée par Claude"),
        (
            status_error(anthropic.PermissionDeniedError, 403),
            "droits insuffisants pour la clé d'API",
        ),
        (status_error(anthropic.NotFoundError, 404), "modèle inconnu de Claude : claude-test"),
        (
            status_error(anthropic.ContentTooLargeError, 413),
            "erreur de Claude (413) : message de l'API",
        ),
        (anthropic.AnthropicError("erreur sans statut"), "erreur de Claude : erreur sans statut"),
    ],
    ids=["400", "401", "403", "404", "autre statut", "sans statut"],
)
def test_une_autre_erreur_de_claude_bloque_le_document_sur_son_motif(error, reason):
    """Autres erreurs du SDK : les statuts nommés, tout autre statut, une erreur sans statut."""
    extraction_error, client = read_with(error)
    assert (str(extraction_error), extraction_error.__cause__, len(client.requests)) == (
        reason,
        error,
        1,
    )


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (reply("Je ne peux pas lire ce document.", "refusal"), "lecture refusée par le modèle"),
        (reply('{"document_type": "commande", "pharm', "max_tokens"), "réponse tronquée"),
        (
            reply('{"document_type": "commande", "pharm', "model_context_window_exceeded"),
            "réponse tronquée",
        ),
        (reply('{"document_type": "commande"}'), "réponse hors du schéma des champs bruts"),
    ],
    ids=["refusee", "tronquee", "contexte depasse", "hors schema"],
)
def test_une_reponse_inexploitable_bloque_le_document_sur_son_motif(answer, reason):
    extraction_error, _ = read_with(answer)
    assert str(extraction_error) == reason


def encrypt(path: Path) -> None:
    """Écrit à `path` Commande_3 protégé par un mot de passe à l'ouverture."""
    with pymupdf.open(COMMANDE_3) as pdf:
        pdf.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="ouvrir", owner_pw="gérer")


@pytest.mark.parametrize(
    ("write", "reason"),
    [
        (lambda path: path.write_text("pas un PDF", encoding="utf-8"), "PDF illisible : "),
        (lambda path: path.write_bytes(b""), "PDF illisible : "),
        (encrypt, "PDF illisible : protégé par un mot de passe"),
        (lambda path: None, "PDF illisible : "),
    ],
    ids=["texte", "vide", "protege par mot de passe", "absent"],
)
def test_un_pdf_illisible_bloque_le_document_sans_appeler_claude(tmp_path, write, reason):
    document = tmp_path / "bon.pdf"
    write(document)
    extraction_error, client = read_with(reply(ANSWER), document)
    assert (str(extraction_error).startswith(reason), client.requests) == (True, [])


def test_une_erreur_du_systeme_de_fichiers_a_l_ouverture_bloque_le_document(monkeypatch):
    """Ouverture refusée par le système de fichiers, simulée : pymupdf ne la lève qu'en course."""
    error = PermissionError(13, "Permission denied")

    def refuse(document: Path) -> None:
        raise error

    monkeypatch.setattr(pymupdf, "open", refuse)
    extraction_error, client = read_with(reply(ANSWER))
    assert (str(extraction_error), extraction_error.__cause__, client.requests) == (
        "PDF illisible : [Errno 13] Permission denied",
        error,
        [],
    )


@pytest.mark.parametrize("environ", [{}, {"ANTHROPIC_API_KEY": ""}], ids=["absente", "vide"])
def test_sans_cle_d_api_l_extracteur_refuse_de_se_construire(environ):
    with pytest.raises(MissingApiKey) as raised:
        extractor_from_environment(environ)
    assert str(raised.value) == (
        "aucune clé d'API Anthropic : renseigner ANTHROPIC_API_KEY dans le fichier .env"
    )


def test_le_client_de_l_environnement_reessaie_trois_fois_et_attend_deux_minutes(monkeypatch):
    built = []

    class SpyClient(anthropic.Anthropic):
        def __init__(self, **settings) -> None:
            super().__init__(**settings)
            built.append(self)

    monkeypatch.setattr(anthropic, "Anthropic", SpyClient)
    extractor_from_environment({"ANTHROPIC_API_KEY": "clé-de-test"})
    (client,) = built
    assert (client.api_key, client.max_retries, client.timeout) == ("clé-de-test", 3, 120)


@pytest.mark.parametrize(
    ("environ", "model"),
    [
        ({"CLAUDE_MODEL": "claude-choisi"}, "claude-choisi"),
        ({}, "claude-haiku-5-5"),
        ({"CLAUDE_MODEL": ""}, "claude-haiku-5-5"),
    ],
    ids=["renseigne", "absent", "vide"],
)
def test_le_modele_est_celui_de_l_environnement_sinon_celui_par_defaut(monkeypatch, environ, model):
    client = FakeClient(reply(ANSWER))
    monkeypatch.setattr(anthropic, "Anthropic", lambda **settings: client)
    extractor_from_environment({"ANTHROPIC_API_KEY": "clé-de-test", **environ})(COMMANDE_3)
    assert [request["model"] for request in client.requests] == [model]
