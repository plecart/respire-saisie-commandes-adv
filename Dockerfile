# Image de `saisie-commandes` : traite `exemples/` vers `sorties/`, montés par `compose.yaml`.
FROM ghcr.io/astral-sh/uv:0.12.5-python3.12-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH"

# Dépendances d'abord : cette couche ne se reconstruit qu'à un changement du projet ou du verrou.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Le code reste en source : pydantic lit les docstrings des champs bruts dans les fichiers.
COPY src ./src
COPY referentiels ./referentiels
RUN uv sync --locked --no-dev

CMD ["saisie-commandes", "exemples", "sorties"]
