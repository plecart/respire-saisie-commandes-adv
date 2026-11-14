"""Relève de la boîte Gmail dédiée : chaque mail non lu se traite comme un `.eml` du dossier.

`saisie-commandes-releve <dossier de sortie>` se connecte en IMAP sur SSL à `imap.gmail.com`,
avec l'adresse et le mot de passe d'application de l'environnement (`GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`), puis relève la boîte de réception toutes les 10 secondes. Chaque mail non
lu y est téléchargé en entier, ce qui le marque lu dans Gmail (RFC 3501, § 6.4.5) : le drapeau
« lu » tient lieu de mémoire des mails traités, redémarrage compris. Le mail se traite comme un
lot d'un document par la chaîne du dossier (`cli.process_documents`) : ses sorties s'écrivent
dans `<dossier de sortie>/mail-<UID>/`, son tableau récapitulatif s'affiche dans le terminal.

Sans variable de la boîte ou sans clé d'API, la commande s'arrête sur un message, sans se
connecter ; une connexion refusée au démarrage l'arrête de même. Une erreur réseau ou IMAP
pendant un cycle s'affiche, la connexion est abandonnée et rouverte au cycle suivant. Ctrl+C
arrête la relève, en code 0. Aucun mail n'est envoyé, déplacé ni supprimé.

Non testé automatiquement, et exclu de la mesure de couverture (issue #7, « Décisions ») :
aucun test n'appelle Gmail.
"""

import argparse
import contextlib
import imaplib
import os
import ssl
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import NoReturn

from saisie_commandes.cli import REFERENCES, Extractor, process_documents
from saisie_commandes.extraction import MissingApiKey, extractor_from_environment
from saisie_commandes.referentiels import ReferenceData
from saisie_commandes.sorties import summary_table

_PROG = "saisie-commandes-releve"

_HOST = "imap.gmail.com"
_PORT = 993

_POLL_SECONDS = 10
"""Intervalle entre deux relèves, fixe (issue #7, « Décisions »)."""

_TIMEOUT_SECONDS = 30
"""Attente maximale d'une lecture ou d'une écriture réseau ; au-delà, le cycle échoue."""

_ADDRESS_VARIABLE = "GMAIL_ADDRESS"
_PASSWORD_VARIABLE = "GMAIL_APP_PASSWORD"

_IMAP_ERRORS = (imaplib.IMAP4.error, OSError)
"""Échecs d'un échange IMAP : refus ou réponse inattendue du serveur, réseau, SSL, délai."""


class MissingCredentials(Exception):
    """L'adresse ou le mot de passe d'application de la boîte n'est pas renseigné."""


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de `saisie-commandes-releve` ; rend le code de sortie.

    `argv` remplace les arguments de la ligne de commande. Rend 1, sans connexion, si une
    variable de la boîte ou la clé d'API manque, et 1 si la connexion de démarrage échoue ;
    sinon relève la boîte jusqu'à Ctrl+C, puis rend 0.
    """
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Relève la boîte Gmail dédiée et traite chaque bon de commande reçu en PDF.",
    )
    parser.add_argument(
        "sortie", type=Path, help="dossier des sorties, un sous-dossier par mail, créé s'il manque"
    )
    args = parser.parse_args(argv)
    try:
        address, password = _credentials(os.environ)
        extract = extractor_from_environment(os.environ)
    except (MissingCredentials, MissingApiKey) as error:
        return _refuse(str(error))
    references = ReferenceData.load(REFERENCES)
    connect = partial(_connect, address, password)
    try:
        imap = connect()
    except _IMAP_ERRORS as error:
        return _refuse(f"connexion à la boîte {address} impossible : {error}")
    print(
        f"Relève de la boîte {address} : un bon de commande envoyé en PDF joint à cette adresse "
        "voit son résultat s'afficher ici en moins d'une minute environ. Ctrl+C pour arrêter."
    )
    process = partial(_process_mail, output_dir=args.sortie, extract=extract, references=references)
    try:
        _watch(imap, connect, process)
    except KeyboardInterrupt:
        return 0


def _credentials(environ: Mapping[str, str]) -> tuple[str, str]:
    """Adresse de la boîte et mot de passe d'application, lus dans `environ`.

    Raises:
        MissingCredentials: l'une des deux variables est absente ou vide ; le texte nomme
            celles à renseigner.
    """
    missing = [name for name in (_ADDRESS_VARIABLE, _PASSWORD_VARIABLE) if not environ.get(name)]
    if missing:
        names = " et ".join(missing)
        raise MissingCredentials(f"boîte Gmail inconnue : renseigner {names} dans le fichier .env")
    return environ[_ADDRESS_VARIABLE], environ[_PASSWORD_VARIABLE]


def _connect(address: str, password: str) -> imaplib.IMAP4:
    """Ouvre une connexion IMAP sur SSL à Gmail, authentifiée par le mot de passe d'application.

    Le certificat du serveur est vérifié (`ssl.create_default_context`) : sans contexte,
    `imaplib.IMAP4_SSL` ne le vérifie pas, et le mot de passe partirait vers tout serveur qui se
    présente. Chaque lecture ou écriture réseau attend au plus `_TIMEOUT_SECONDS`. Une connexion
    dont l'authentification échoue est fermée.

    Raises:
        imaplib.IMAP4.error: authentification refusée, ou réponse inattendue du serveur.
        OSError: erreur réseau, certificat refusé ou délai dépassé.
    """
    imap = imaplib.IMAP4_SSL(
        _HOST, _PORT, ssl_context=ssl.create_default_context(), timeout=_TIMEOUT_SECONDS
    )
    try:
        imap.login(address, password)
    except _IMAP_ERRORS:
        _abandon(imap)
        raise
    return imap


def _watch(
    imap: imaplib.IMAP4 | None,
    connect: Callable[[], imaplib.IMAP4],
    process: Callable[[str, bytes], None],
) -> NoReturn:
    """Relève la boîte toutes les `_POLL_SECONDS` secondes, sans fin, à partir de `imap`.

    `process` reçoit l'UID et les octets de chaque mail non lu. Une erreur réseau ou IMAP d'un
    cycle (`_IMAP_ERRORS`, où tombe aussi une `OSError` levée par `process`) s'écrit sur la sortie
    d'erreur ; la connexion est abandonnée, et `connect` en ouvre une autre au cycle suivant. Toute
    autre exception, dont l'interruption par Ctrl+C (`KeyboardInterrupt`), déconnecte au mieux,
    puis remonte : c'est la seule sortie de la boucle.
    """
    try:
        while True:
            try:
                imap = imap or connect()
                _check_inbox(imap, process)
            except _IMAP_ERRORS as error:
                print(
                    f"{_PROG} : relève interrompue ({error}), reprise dans {_POLL_SECONDS} s.",
                    file=sys.stderr,
                )
                _abandon(imap)
                imap = None
            time.sleep(_POLL_SECONDS)
    finally:
        _logout(imap)


def _check_inbox(imap: imaplib.IMAP4, process: Callable[[str, bytes], None]) -> None:
    """Un cycle de relève : passe à `process` l'UID et les octets de chaque mail non lu.

    La réponse SEARCH porte les UID séparés par des espaces, sur une ou plusieurs lignes ;
    `imaplib` rend `[None]` quand le serveur n'en envoie aucune.

    Raises:
        imaplib.IMAP4.error: le serveur refuse une commande ou rend une réponse inattendue,
            dont un UID qui n'est pas un nombre : l'UID nomme un dossier de sortie.
        OSError: erreur réseau ou délai dépassé.
    """
    _ok(imap.select("INBOX"))
    uids = b" ".join(filter(None, _ok(imap.uid("SEARCH", None, "UNSEEN")))).split()
    if not all(uid.isdigit() for uid in uids):
        raise imaplib.IMAP4.error(f"UID inattendus : {uids}")
    for uid in map(bytes.decode, uids):
        process(uid, _fetch(imap, uid))


def _fetch(imap: imaplib.IMAP4, uid: str) -> bytes:
    """Octets du mail `uid`, téléchargé en entier : `BODY[]`, et non `BODY.PEEK[]`, le marque lu.

    Raises:
        imaplib.IMAP4.error: le serveur refuse la commande, ou sa réponse ne porte pas le mail.
        OSError: erreur réseau ou délai dépassé.
    """
    for part in _ok(imap.uid("FETCH", uid, "(BODY[])")):
        if isinstance(part, tuple):
            return part[1]
    raise imaplib.IMAP4.error(f"mail {uid} absent de la réponse")


def _ok(response: tuple[str, list]) -> list:
    """Données d'une réponse IMAP de statut OK.

    Raises:
        imaplib.IMAP4.error: le serveur a répondu NO, qu'`imaplib` rend sans lever.
    """
    status, data = response
    if status != "OK":
        raise imaplib.IMAP4.error(f"réponse {status} : {data}")
    return data


def _process_mail(
    uid: str, raw: bytes, *, output_dir: Path, extract: Extractor, references: ReferenceData
) -> None:
    """Traite un mail comme un lot d'un document, `mail-<uid>.eml`, et affiche son tableau.

    Le mail s'écrit le temps du traitement dans un dossier temporaire ; ses sorties, JSON de la
    commande s'il y en a une et `rapport.md`, dans `<output_dir>/mail-<uid>/`, propre à ce mail.
    """
    # ponytail: un UID n'est unique que sous une même UIDVALIDITY de la boîte (RFC 3501,
    # § 2.3.1.1) ; la préfixer au dossier de sortie si Gmail en change un jour.
    name = f"mail-{uid}"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        mail = Path(directory, f"{name}.eml")
        mail.write_bytes(raw)
        results = process_documents([mail], output_dir / name, extract, references)
    print(summary_table(results))


def _abandon(imap: imaplib.IMAP4 | None) -> None:
    """Ferme la socket d'une connexion en échec, sans rien demander au serveur."""
    if imap is not None:
        with contextlib.suppress(OSError):
            imap.shutdown()


def _logout(imap: imaplib.IMAP4 | None) -> None:
    """Déconnecte au mieux : une erreur de déconnexion reste sans suite, la relève s'arrête."""
    if imap is not None:
        with contextlib.suppress(*_IMAP_ERRORS):
            imap.logout()


def _refuse(reason: str) -> int:
    """Écrit pourquoi la relève ne démarre pas, sur la sortie d'erreur ; rend le code de sortie."""
    print(f"{_PROG} : {reason}, relève non démarrée.", file=sys.stderr)
    return 1
