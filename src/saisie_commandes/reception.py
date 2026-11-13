"""Réception d'un lot : les documents à traiter d'un dossier d'entrée.

Le dossier est parcouru fichier par fichier, sans descendre dans ses sous-dossiers. Un fichier
est reçu comme document par son extension, quelle que soit sa casse ; les autres sont ignorés.
Les documents se rendent dans l'ordre de leurs noms, quel que soit le système de fichiers.
"""

from pathlib import Path

_DOCUMENT_SUFFIXES = frozenset({".pdf"})
"""Extensions, en minuscules, des fichiers reçus comme documents."""


def receive(directory: Path) -> list[Path]:
    """Documents à traiter dans `directory`, triés par nom."""
    documents = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _DOCUMENT_SUFFIXES
    ]
    return sorted(documents, key=lambda path: path.name)
