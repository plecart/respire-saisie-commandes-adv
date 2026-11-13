"""Réception d'un lot : les documents à traiter d'un dossier d'entrée.

Le dossier est parcouru fichier par fichier, sans descendre dans ses sous-dossiers. Un fichier
est reçu comme document par son extension, quelle que soit sa casse ; les autres sont ignorés.
Les documents se rendent dans l'ordre de leurs noms, quel que soit le système de fichiers.
Deux documents au même nom sans extension se repèrent (`shared_names`).
"""

from collections import Counter
from collections.abc import Iterable
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


def shared_names(documents: Iterable[Path]) -> list[str]:
    """Noms sans extension que portent plusieurs documents, triés : leurs sorties se confondraient.

    Sur un système de fichiers sensible à la casse, `A.pdf` et `A.PDF` sont deux documents.
    """
    counts = Counter(document.stem for document in documents)
    return sorted(name for name, count in counts.items() if count > 1)
