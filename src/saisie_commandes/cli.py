"""Ligne de commande : traite un dossier de documents reçus et écrit les sorties du lot.

`saisie-commandes <dossier d'entrée> <dossier de sortie>` enchaîne réception, extraction, règles
métier et sorties (PRD #1, « Modules ») : le dossier de sortie reçoit un JSON par commande
produite et le rapport `rapport.md` ; le terminal affiche, pour chaque document, ses erreurs et
avertissements, puis le JSON de sa commande (`sorties.terminal_view`). Les référentiels se
lisent dans `referentiels/`, sous le dossier courant.

Un mail se traite comme le seul PDF parmi ses pièces jointes, les autres ignorées, écrit le temps
de son extraction dans un dossier temporaire ; un mail sans PDF joint, ou à plusieurs PDF joints,
est bloqué sans être extrait (`reception`). Un document dont la lecture échoue est bloqué, motif
« lecture impossible : … » ; le lot continue.

L'extraction est injectée (`main`, `process_documents`) ; à défaut, la commande lit les documents
par Claude, selon l'environnement (`extraction`). Sans clé d'API, elle s'arrête sur un message,
sans rien écrire. Elle s'arrête de même sur deux documents du même nom sans extension, dont les
sorties se confondraient.
"""

import argparse
import os
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from saisie_commandes.champs import RawFields
from saisie_commandes.extraction import MissingApiKey, extractor_from_environment
from saisie_commandes.reception import (
    RejectedMail,
    is_mail,
    receive,
    save_pdf_attachment,
    shared_names,
)
from saisie_commandes.referentiels import ReferenceData
from saisie_commandes.regles import apply_rules
from saisie_commandes.resultat import Anomaly, DocumentResult
from saisie_commandes.sorties import Results, terminal_view, write_outputs
from saisie_commandes.valeurs import on_one_line

type Extractor = Callable[[Path], RawFields]
"""Lit les champs bruts d'un document, désigné par son chemin."""

REFERENCES = Path("referentiels")
"""Dossier des référentiels, relatif au dossier courant."""


def process_documents(
    documents: Iterable[Path], output_dir: Path, extract: Extractor, references: ReferenceData
) -> Results:
    """Traite chaque document du lot et en écrit les sorties dans `output_dir`.

    Rend les résultats du lot, par nom de document sans extension, dans l'ordre des documents.
    """
    results = {document.stem: _process(document, extract, references) for document in documents}
    write_outputs(results, output_dir)
    return results


def _process(document: Path, extract: Extractor, references: ReferenceData) -> DocumentResult:
    """Résultat d'un document : ses champs bruts passés aux règles, ou le motif de son blocage.

    Frontière par document (issue #5, « Décisions ») : une lecture en échec bloque le document
    seul, le lot continue. Toute erreur levée en lisant les champs bruts, pas seulement
    `ExtractionError`, a pour motif « lecture impossible : » suivi de son texte, à défaut du nom
    de sa classe.
    """
    try:
        fields = _raw_fields(document, extract)
    except RejectedMail as rejection:
        return _blocked(str(rejection))
    except Exception as error:  # noqa: BLE001 (frontière par document, voir la docstring)
        return _blocked(f"lecture impossible : {describe_error(error)}")
    return apply_rules(fields, references)


def _raw_fields(document: Path, extract: Extractor) -> RawFields:
    """Champs bruts d'un document ; ceux d'un mail sont ceux de son seul PDF joint.

    Le PDF d'un mail s'écrit dans un dossier temporaire, supprimé après l'extraction ; un échec
    de cette suppression (fichier encore ouvert sous Windows) n'interrompt pas le lot.

    Raises:
        RejectedMail: le document est un mail qui ne porte aucun PDF joint, ou en porte plusieurs.
    """
    if not is_mail(document):
        return extract(document)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        return extract(save_pdf_attachment(document, Path(directory)))


def describe_error(error: BaseException) -> str:
    """Texte d'une erreur dans un motif : son message, à défaut le nom de sa classe."""
    return str(error) or type(error).__name__


def _blocked(reason: str) -> DocumentResult:
    """Résultat d'un document bloqué avant les règles : son motif, rien d'établi."""
    return DocumentResult((Anomaly(reason, blocking=True),))


def main(argv: Sequence[str] | None = None, extract: Extractor | None = None) -> int:
    """Point d'entrée de `saisie-commandes` ; rend le code de sortie, non nul si le lot est refusé.

    `argv` remplace les arguments de la ligne de commande ; `extract` est l'extracteur injecté,
    à défaut celui de `extractor_from_environment` sur `os.environ`.
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
        try:
            extract = extractor_from_environment(os.environ)
        except MissingApiKey as error:
            return _refuse(str(error))
    documents = receive(args.entree)
    if shared := shared_names(documents):
        names = ", ".join(f"« {on_one_line(name)} »" for name in shared)
        return _refuse(f"plusieurs documents portent le nom {names}")
    references = ReferenceData.load(REFERENCES)
    results = process_documents(documents, args.sortie, extract, references)
    print(terminal_view(results))
    return 0


def _refuse(reason: str) -> int:
    """Écrit pourquoi le lot n'est pas traité, sur la sortie d'erreur ; rend le code de sortie."""
    print(f"saisie-commandes : {reason}, aucun document n'a été traité.", file=sys.stderr)
    return 1
