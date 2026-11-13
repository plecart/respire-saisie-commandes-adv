"""Lecture d'un document par Claude : du PDF reçu aux champs bruts (`RawFields`).

Une seule voie de lecture (ADR 0001 § 2) : chaque page est rendue en image PNG, et le document
entier part en un seul appel à l'API Claude, sortie contrainte par le JSON Schema de `RawFields`,
réponse validée par `RawFields`. Le modèle extrait, le code décide (§ 3) : les instructions lui
demandent de ne rendre que ce qui est imprimé, une valeur illisible comme telle, jamais devinée,
ni texte libre ni annotation manuscrite. Le modèle se choisit par variable d'environnement (§ 4) ;
la clé d'API est indispensable (§ 9).

Une lecture qui échoue lève `ExtractionError`, dont le texte est le motif en clair ; l'issue #5
(« Décisions ») en fait un document bloqué, sans arrêter le lot. Les erreurs temporaires sont
réessayées par le SDK lui-même, jamais ici ; toute autre erreur lève dès le premier appel.

Ce module appelle un service payant : il n'est couvert que par des tests à client simulé, et il
reste hors de la mesure de couverture.
"""

import base64
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import anthropic
import pydantic
import pymupdf

from saisie_commandes.champs import RawFields

API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
"""Variable d'environnement de la clé d'API Anthropic."""

MODEL_VARIABLE = "CLAUDE_MODEL"
"""Variable d'environnement du modèle Claude qui lit les documents."""

DEFAULT_MODEL = "claude-haiku-5-5"
"""Modèle utilisé quand `CLAUDE_MODEL` n'est pas renseigné.

Le moins cher qui lit correctement les documents fournis (ADR 0001 § 4) : comparé le 2026-11-13
sur les cinq PDF de `exemples/`, Haiku 5.5 reproduit la table des résultats attendus du PRD #1 à
trois exécutions sur trois (comparaison des modèles : description de la PR #11).
"""

_MAX_RETRIES = 5
"""Réessais du SDK sur une erreur temporaire (connexion, délai dépassé, 408, 409, 429, ≥ 500)."""

_TIMEOUT_SECONDS = 120
"""Attente maximale d'une tentative ; celle du SDK, 10 minutes, ferait une heure sur six."""

_DPI = 220
"""Résolution du rendu des pages.

À 150 dpi, Haiku 5.5 décalait d'une ligne deux totaux de Commande_1 (13 lignes, beaucoup à
« 0,00 € ») à deux lectures sur six ; à 220 dpi, huit sur huit justes, réponse plus courte
(mesuré le 2026-11-13, description de la PR #11).
"""

_MAX_TOKENS = 16_000
"""Plafond de la réponse ; les champs bruts attendus de Commande_3, 18 lignes, font 3 Ko de JSON."""


def _wrap_refs(schema: Any) -> Any:
    """`schema`, chaque `$ref` accompagné d'autres clés enveloppé dans un `anyOf` à une branche.

    `transform_schema` ne garde d'un nœud `$ref` que la référence (SDK 2.8.0,
    `lib/_parse/_transform.py`) : la description d'un champ typé par un modèle ou un alias s'y
    perdrait. Dans l'enveloppe, elle reste au champ ; un `allOf` ne conviendrait pas, l'API
    refusant un `allOf` qui porte un `$ref` (documentation « Structured outputs », « JSON Schema
    limitations »).
    """
    if isinstance(schema, list):
        return [_wrap_refs(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    schema = {key: _wrap_refs(value) for key, value in schema.items()}
    if "$ref" in schema and len(schema) > 1:
        ref = schema.pop("$ref")
        return {"anyOf": [{"$ref": ref}], **schema}
    return schema


_OUTPUT_CONFIG = {
    "format": {
        "type": "json_schema",
        "schema": anthropic.transform_schema(_wrap_refs(RawFields.model_json_schema())),
    }
}
"""Sortie contrainte par le schéma des champs bruts, adapté par le SDK, descriptions comprises."""

_INSTRUCTIONS = """Tu lis un document reçu par l'administration des ventes d'un fournisseur, le plus
souvent le bon de commande d'une pharmacie, et tu en recopies les champs que demande le schéma.

- Ne renvoie que ce qui est imprimé. Une valeur qui n'est pas imprimée vaut null ; une valeur
  imprimée mais illisible vaut {"illegible": true}. Ne devine, ne complète et ne calcule jamais
  une valeur.
- Recopie chaque valeur telle qu'imprimée, sans la convertir : virgule décimale, symbole « % »,
  date au format du document.
- Ne lis ni le texte libre (commentaires, conditions, mentions) ni les annotations manuscrites.
- La pharmacie est celle qui passe la commande, jamais le fournisseur. Son nom est celui de
  l'officine seul, sans les noms de ses titulaires ou pharmaciens ni son adresse. Le prix
  catalogue est le prix unitaire avant remise ; les totaux sont hors taxes ; la date de
  livraison est celle qui est souhaitée, pas celle de la commande ni de l'édition.
- L'unité est celle de la quantité (« UN », « COL6 ») ; null si le document n'en imprime pas.
  Ne la confonds pas avec un prix.
- Une entrée par ligne de commande, dans l'ordre du document. Une remise par colonne de remise
  renseignée sur la ligne ; aucune si ces colonnes sont vides.
- Indique la nature du document : commande, facture ou autre."""
"""Instructions au modèle, génériques : aucune règle propre à un document."""

_PROMPT = "Voici les pages du document, dans l'ordre. Recopie ses champs selon le schéma."
"""Consigne qui suit les images des pages."""

_UNAVAILABLE = "Claude indisponible, relancer le document"
"""Motif d'une erreur temporaire que les réessais du SDK n'ont pas levée."""

_TEMPORARY_STATUSES = frozenset({408, 409, 429})
"""Statuts temporaires sous 500, que le SDK réessaie comme tout statut à partir de 500."""

_UNUSABLE_STOPS = {
    "refusal": "lecture refusée par le modèle",
    "max_tokens": "réponse tronquée",
    "model_context_window_exceeded": "réponse tronquée",
}
"""Motif de chaque fin de réponse qui la rend inexploitable, par `stop_reason`."""


class ExtractionError(Exception):
    """La lecture d'un document a échoué ; le texte de l'erreur est le motif, en clair."""


class MissingApiKey(Exception):
    """Aucune clé d'API Anthropic n'est renseignée : aucune lecture n'est possible."""


def extractor_from_environment(environ: Mapping[str, str]) -> Callable[[Path], RawFields]:
    """Extracteur Claude configuré par l'environnement.

    Args:
        environ: les variables d'environnement, `os.environ` par exemple. `ANTHROPIC_API_KEY`
            porte la clé d'API ; `CLAUDE_MODEL`, s'il est renseigné, le modèle, sinon
            `DEFAULT_MODEL`.

    Returns:
        L'extracteur de `claude_extractor`, sur un client qui réessaie 5 fois une erreur
        temporaire et attend 2 minutes au plus la réponse à une tentative.

    Raises:
        MissingApiKey: `ANTHROPIC_API_KEY` est absente ou vide.
    """
    api_key = environ.get(API_KEY_VARIABLE)
    if not api_key:
        raise MissingApiKey(
            f"aucune clé d'API Anthropic : renseigner {API_KEY_VARIABLE} dans le fichier .env"
        )
    client = anthropic.Anthropic(
        api_key=api_key, max_retries=_MAX_RETRIES, timeout=_TIMEOUT_SECONDS
    )
    return claude_extractor(client, environ.get(MODEL_VARIABLE) or DEFAULT_MODEL)


def claude_extractor(client: anthropic.Anthropic, model: str) -> Callable[[Path], RawFields]:
    """Extracteur qui fait lire un PDF par Claude, en un seul appel par document.

    Args:
        client: le client de l'API, injecté ; seule sa méthode `messages.create` est appelée,
            une fois par document.
        model: le nom du modèle Claude qui lit.

    Returns:
        Un extracteur (`cli.Extractor`) : il rend les champs bruts du PDF dont il reçoit le
        chemin, et lève `ExtractionError` avec le motif de l'échec — PDF illisible, erreur de
        l'API, réponse refusée, tronquée ou hors du schéma des champs bruts.
    """

    def extract(document: Path) -> RawFields:
        return _read_answer(_ask(client, model, _render_pages(document)))

    return extract


def _render_pages(document: Path) -> list[bytes]:
    """Chaque page du PDF, rendue en PNG, dans l'ordre ; `ExtractionError` s'il est illisible."""
    try:
        pdf = pymupdf.open(document)
    except (pymupdf.FileDataError, pymupdf.FileNotFoundError, OSError) as error:
        raise ExtractionError(f"PDF illisible : {error}") from error
    with pdf:
        if pdf.needs_pass:
            raise ExtractionError("PDF illisible : protégé par un mot de passe")
        return [page.get_pixmap(dpi=_DPI).tobytes("png") for page in pdf]


def _ask(client: anthropic.Anthropic, model: str, pages: list[bytes]) -> anthropic.types.Message:
    """Un appel à l'API : les pages puis la consigne ; toute erreur du SDK → `ExtractionError`."""
    images = [_png_block(page) for page in pages]
    try:
        return client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=_INSTRUCTIONS,
            messages=[{"role": "user", "content": [*images, {"type": "text", "text": _PROMPT}]}],
            output_config=_OUTPUT_CONFIG,
        )
    except anthropic.AnthropicError as error:
        raise ExtractionError(_reason(error, model)) from error


def _png_block(png: bytes) -> dict:
    """Bloc de contenu d'un message qui porte une image PNG."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode("ascii"),
        },
    }


def _reason(error: anthropic.AnthropicError, model: str) -> str:
    """Motif en clair d'une erreur du SDK, levée une fois ses propres réessais épuisés."""
    if isinstance(error, anthropic.APIConnectionError):
        return _UNAVAILABLE
    if not isinstance(error, anthropic.APIStatusError):
        return f"erreur de Claude : {error}"
    status = error.status_code
    if status in _TEMPORARY_STATUSES or status >= 500:
        return _UNAVAILABLE
    detail = error.api_message or error.message
    return {
        400: f"requête refusée par Claude : {detail}",
        401: "clé d'API refusée par Claude",
        403: "droits insuffisants pour la clé d'API",
        404: f"modèle inconnu de Claude : {model}",
    }.get(status, f"erreur de Claude ({status}) : {detail}")


def _read_answer(message: anthropic.types.Message) -> RawFields:
    """Les champs bruts de la réponse, validés par `RawFields` ; `ExtractionError` sinon.

    La fin de la réponse se lit avant sa validation : une réponse tronquée n'est pas du JSON
    complet, et l'échec de sa validation en masquerait le motif.
    """
    if reason := _UNUSABLE_STOPS.get(message.stop_reason):
        raise ExtractionError(reason)
    text = "".join(block.text for block in message.content if block.type == "text")
    try:
        return RawFields.model_validate_json(text)
    except pydantic.ValidationError as error:
        raise ExtractionError("réponse hors du schéma des champs bruts") from error
