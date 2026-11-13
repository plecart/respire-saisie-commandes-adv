"""Extractions attendues des documents fournis, versionnées dans `donnees/extractions/`."""

from pathlib import Path

EXTRACTIONS = Path(__file__).parent / "donnees" / "extractions"


def extraction(name: str) -> str:
    """JSON de l'extraction attendue d'un document, désigné par son nom sans extension."""
    return (EXTRACTIONS / f"{name}.json").read_text(encoding="utf-8")
