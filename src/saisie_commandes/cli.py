"""Ligne de commande : traite un dossier de documents reçus et écrit les sorties du lot.

`saisie-commandes <dossier d'entrée> <dossier de sortie>` enchaîne réception, extraction, règles
métier et sorties (PRD #1, « Modules ») : le dossier de sortie reçoit un JSON par commande
produite et le rapport `rapport.md`, le terminal le tableau récapitulatif du lot. Les
référentiels se lisent dans `referentiels/`, sous le dossier courant.

L'extraction est injectée (`main`, `process_documents`). Aucun extracteur n'est encore branché :
lancée seule, la commande s'arrête sur un message, sans rien écrire. Elle s'arrête de même sur
deux documents du même nom sans extension, dont les sorties se confondraient.
"""

import argparse
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from saisie_commandes.champs import RawFields
from saisie_commandes.reception import receive, shared_names
from saisie_commandes.referentiels import ReferenceData
from saisie_commandes.regles import apply_rules
from saisie_commandes.sorties import Results, summary_table, write_outputs

type Extractor = Callable[[Path], RawFields]
"""Lit les champs bruts d'un document, désigné par son chemin."""

_REFERENCES = Path("referentiels")


def process_documents(
    documents: Iterable[Path], output_dir: Path, extract: Extractor, references: ReferenceData
) -> Results:
    """Traite chaque document du lot et en écrit les sorties dans `output_dir`.

    Rend les résultats du lot, par nom de document sans extension, dans l'ordre des documents.
    """
    results = {document.stem: apply_rules(extract(document), references) for document in documents}
    write_outputs(results, output_dir)
    return results


def main(argv: Sequence[str] | None = None, extract: Extractor | None = None) -> int:
    """Point d'entrée de `saisie-commandes` ; rend le code de sortie, non nul sans extracteur.

    `argv` remplace les arguments de la ligne de commande ; `extract` est l'extracteur injecté.
    """
    parser = argparse.ArgumentParser(
        prog="saisie-commandes",
        description="Saisit les bons de commande d'un dossier en commandes de vente Odoo.",
    )
    parser.add_argument("entree", type=Path, help="dossier des documents reçus")
    parser.add_argument(
        "sortie", type=Path, help="dossier des commandes et du rapport, créé s'il manque"
    )
    args = parser.parse_args(argv)
    if extract is None:
        return _refuse("aucun extracteur de documents n'est branché")
    documents = receive(args.entree)
    if shared := shared_names(documents):
        return _refuse(
            "plusieurs documents portent le nom " + ", ".join(f"« {n} »" for n in shared)
        )
    references = ReferenceData.load(_REFERENCES)
    results = process_documents(documents, args.sortie, extract, references)
    print(summary_table(results))
    return 0


def _refuse(reason: str) -> int:
    """Écrit pourquoi le lot n'est pas traité, sur la sortie d'erreur ; rend le code de sortie."""
    print(f"saisie-commandes : {reason}, aucun document n'a été traité.", file=sys.stderr)
    return 1
