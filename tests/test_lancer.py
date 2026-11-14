"""Tests de `lancer.sh`, lancé par `sh` comme l'évaluateur le lance, uv et curl simulés.

Le script se copie dans un dépôt temporaire, `HOME` pointe dans `tmp_path`, et le PATH ne garde
que les dossiers des utilitaires dont le script a besoin, derrière de faux `uv` et `curl` qui
consignent ce qu'ils reçoivent dans `HOME`. L'entrée standard est vide, sauf pour la saisie
masquée de la clé d'API, tapée dans un pseudo-terminal : ces tests-là ne tournent que sous POSIX.
"""

import os
import select
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

try:
    import pty
    import termios
except ImportError:  # Windows : ni pseudo-terminal ni termios.
    pty = None

SH = shutil.which("sh")
pytestmark = pytest.mark.skipif(SH is None, reason="sh introuvable : lancer.sh ne peut pas tourner")

needs_pty = pytest.mark.skipif(
    pty is None, reason="pty indisponible hors POSIX : la saisie de la clé exige un terminal"
)

ROOT = Path(__file__).parents[1]

INSTALLER_URL = "https://astral.sh/uv/install.sh"

INSTALLED_UV = Path("home", ".local", "bin", "uv")
"""uv installé dans le dossier de l'utilisateur, relatif à `tmp_path`."""

TOOLS = ("sh", "env", "dirname", "stty", "cat", "mkdir", "chmod")
"""Utilitaires externes qu'appellent le script, le faux installeur et `sh` lui-même."""

UV_EXIT_CODE = 3
"""Code de sortie du faux `uv`, distinct de 0 et de 1."""

FAKE_UV = rf"""#!/bin/sh
printf '%s\n' "$@" > "$HOME/uv.log"
exit {UV_EXIT_CODE}
"""
"""Faux `uv` : consigne ses arguments, un par ligne."""

FAKE_CURL = rf"""#!/bin/sh
printf '%s\n' "$@" > "$HOME/curl.log"
cat <<'INSTALLER'
mkdir -p "$UV_INSTALL_DIR"
printf '%s\n' "$UV_NO_MODIFY_PATH" > "$HOME/installer.log"
cat > "$UV_INSTALL_DIR/uv" <<'UV'
{FAKE_UV}UV
chmod +x "$UV_INSTALL_DIR/uv"
INSTALLER
"""
"""Faux `curl` : consigne ses arguments et rend un installeur qui pose le faux `uv`.

L'installeur rendu se comporte comme l'officiel sur ce que le script en attend : il installe
dans `UV_INSTALL_DIR`, et consigne `UV_NO_MODIFY_PATH`, qui laisse les profils du shell intacts.
"""

RUN = ["run", "--locked", "--env-file", ".env", "saisie-commandes"]
"""Arguments que reçoit uv, avant les dossiers d'entrée et de sortie."""

DEFAULT_RUN = [*RUN, "exemples", "sorties"]
"""Arguments que reçoit uv d'un lancement sans argument."""

PROMPT = "saisie masquée : ".encode()
"""Fin de l'invite de la clé d'API, après laquelle le script attend la saisie."""

READ_TIMEOUT = 10
"""Secondes d'attente au plus de chaque lecture du terminal."""

TYPED_KEY = "sk-ant-saisie"

KEY_LINE = f"{TYPED_KEY}\n".encode()
"""La clé tapée, puis Entrée."""

NO_KEY = [
    pytest.param(b"\n", id="entree-seule"),
    pytest.param(b"\x04", id="fin-de-saisie"),  # Ctrl-D
    pytest.param(b"\x03", id="interruption"),  # Ctrl-C
]
"""Saisies qui ne donnent aucune clé."""


@pytest.fixture
def system_path():
    """PATH des seuls dossiers de `TOOLS` ; saute le test si un uv réel s'y trouve."""
    found = {tool: shutil.which(tool) for tool in TOOLS}
    if missing := [tool for tool, path in found.items() if path is None]:
        pytest.skip(f"utilitaires introuvables : {', '.join(missing)}")
    path = os.pathsep.join(dict.fromkeys(str(Path(path).parent) for path in found.values()))
    if real_uv := shutil.which("uv", path=path):
        pytest.skip(f"uv réel dans {real_uv}, que le PATH réduit ne peut pas masquer")
    return path


@pytest.fixture
def script_env(tmp_path, system_path):
    """Pose `depot/lancer.sh`, son `.env` et le faux `curl`, et rend l'environnement du script.

    Les variables d'uv du poste, `UV_NO_MODIFY_PATH` comprise, ne passent pas au script.
    """
    repo = tmp_path / "depot"
    repo.mkdir()
    shutil.copy(ROOT / "lancer.sh", repo)
    (repo / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-factice\n")
    (tmp_path / "home").mkdir()
    fakes = tmp_path / "bin"
    _write_executable(fakes / "curl", FAKE_CURL)
    env = {name: value for name, value in os.environ.items() if not name.startswith("UV_")}
    env |= {"HOME": str(tmp_path / "home"), "PATH": os.pathsep.join([str(fakes), system_path])}
    return env


@pytest.fixture
def launch(tmp_path, script_env):
    """Lance `sh depot/lancer.sh <arguments>` depuis `tmp_path`, entrée standard vide.

    La fonction rendue lance le script ; sous `uv_on_path`, le faux `uv` est sur le PATH.
    """

    def run(*args: str, uv_on_path: bool = True) -> subprocess.CompletedProcess[str]:
        if uv_on_path:
            _write_executable(tmp_path / "bin" / "uv", FAKE_UV)
        return subprocess.run(
            [SH, "depot/lancer.sh", *args],
            check=False,
            cwd=tmp_path,
            env=script_env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            timeout=60,
        )

    return run


class Terminal(NamedTuple):
    """Ce qu'un lancement laisse au terminal : code de sortie, affichage, écho à la fin."""

    returncode: int
    output: str
    echo: bool


@pytest.fixture
def type_key(tmp_path, script_env):
    """Lance `sh depot/lancer.sh` sans `.env` dans un pseudo-terminal, faux `uv` sur le PATH.

    La fonction rendue tape `keys` à l'invite de la clé, attend la fin du script et rend ce
    qu'en voit le terminal.
    """
    (tmp_path / "depot" / ".env").unlink()
    _write_executable(tmp_path / "bin" / "uv", FAKE_UV)

    def run(keys: bytes) -> Terminal:
        pid, master = pty.fork()
        if pid == 0:  # Le script, dont le pseudo-terminal est le terminal de contrôle.
            try:
                os.execve(SH, [SH, str(tmp_path / "depot" / "lancer.sh")], script_env)
            finally:
                os._exit(127)  # Jamais de retour dans pytest.
        try:
            output = _type_at_prompt(master, keys)
            _iflag, _oflag, _cflag, lflag, *_ = termios.tcgetattr(master)
        finally:
            os.close(master)  # Un script resté à l'invite voit son terminal fermé, et sort.
        returncode = os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])
        return Terminal(returncode, output.decode(), bool(lflag & termios.ECHO))

    return run


def _type_at_prompt(master: int, keys: bytes) -> bytes:
    """Tape `keys` au terminal à l'invite de la clé, et rend son affichage jusqu'à sa fermeture.

    Échoue si le terminal reste muet `READ_TIMEOUT` secondes.
    """
    output = b""
    while select.select([master], [], [], READ_TIMEOUT)[0]:
        try:
            chunk = os.read(master, 1024)
        except OSError:  # Terminal fermé : EIO sous Linux, b"" ailleurs (`pty._copy` de CPython).
            chunk = b""
        if not chunk:
            return output
        output += chunk
        if output.endswith(PROMPT):
            os.write(master, keys)
    pytest.fail(f"terminal muet depuis {READ_TIMEOUT} s, après : {output!r}")


def _write_executable(path: Path, text: str) -> None:
    """Écrit un script exécutable, en fins de ligne LF quel que soit le système."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _logged(tmp_path: Path, fake: str) -> list[str] | None:
    """Lignes consignées par le faux `fake` — `uv`, `curl` ou `installer` —, None sans journal."""
    log = tmp_path / "home" / f"{fake}.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else None


def test_sans_env_ni_terminal_le_script_s_arrete_sur_un_message_sans_rien_lancer(launch, tmp_path):
    """Le message nomme `.env` et la clé ; rien n'est écrit, rien n'est installé ni lancé.

    Sans uv sur le PATH : un téléchargement qui précéderait l'arrêt appellerait curl.
    """
    (tmp_path / "depot" / ".env").unlink()
    result = launch(uv_on_path=False)
    assert (
        result.returncode != 0,
        ".env" in result.stderr,
        "ANTHROPIC_API_KEY" in result.stderr,
        (tmp_path / "depot" / ".env").exists(),
        _logged(tmp_path, "uv"),
        _logged(tmp_path, "curl"),
    ) == (True, True, True, False, None, None), result.stderr


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), DEFAULT_RUN),
        (("bons reçus", "lot du jour"), [*RUN, "bons reçus", "lot du jour"]),
    ],
)
def test_le_script_lance_le_programme_par_l_uv_du_path_sur_les_dossiers_demandes(
    launch, tmp_path, args, expected
):
    """Sans argument, les dossiers par défaut ; un dossier dont le nom a une espace reste un."""
    launch(*args)
    assert _logged(tmp_path, "uv") == expected


def test_le_code_de_sortie_du_script_est_celui_du_programme(launch):
    assert launch().returncode == UV_EXIT_CODE


def test_sans_uv_le_script_l_installe_dans_le_dossier_de_l_utilisateur_puis_le_lance(
    launch, tmp_path
):
    """Installeur officiel, profils du shell intacts, puis uv lancé par son chemin."""
    launch(uv_on_path=False)
    assert (
        INSTALLER_URL in (_logged(tmp_path, "curl") or []),
        _logged(tmp_path, "installer"),
        (tmp_path / INSTALLED_UV).is_file(),
        _logged(tmp_path, "uv"),
    ) == (True, ["1"], True, DEFAULT_RUN)


def test_un_uv_deja_installe_dans_le_dossier_de_l_utilisateur_ne_se_reinstalle_pas(
    launch, tmp_path
):
    _write_executable(tmp_path / INSTALLED_UV, FAKE_UV)
    launch(uv_on_path=False)
    assert (_logged(tmp_path, "curl"), _logged(tmp_path, "uv")) == (None, DEFAULT_RUN)


@needs_pty
def test_la_cle_saisie_est_ecrite_dans_env_lisible_par_l_utilisateur_seul(type_key, tmp_path):
    """Le fichier est en mode 0600, puis le programme est lancé."""
    type_key(KEY_LINE)
    env_file = tmp_path / "depot" / ".env"
    assert (
        env_file.read_text(encoding="utf-8"),
        env_file.stat().st_mode & 0o777,
        _logged(tmp_path, "uv"),
    ) == (f"ANTHROPIC_API_KEY={TYPED_KEY}\n", 0o600, DEFAULT_RUN)


@needs_pty
def test_la_cle_saisie_ne_s_affiche_pas_dans_le_terminal(type_key):
    result = type_key(KEY_LINE)
    assert TYPED_KEY not in result.output, result.output


@needs_pty
@pytest.mark.parametrize("keys", [pytest.param(KEY_LINE, id="cle"), *NO_KEY])
def test_l_echo_du_terminal_est_retabli_a_la_fin_de_la_saisie(type_key, keys):
    assert type_key(keys).echo


@needs_pty
@pytest.mark.parametrize("keys", NO_KEY)
def test_sans_cle_saisie_le_script_s_arrete_sans_ecrire_env_ni_rien_lancer(
    type_key, tmp_path, keys
):
    result = type_key(keys)
    assert (
        result.returncode != 0,
        (tmp_path / "depot" / ".env").exists(),
        _logged(tmp_path, "uv"),
    ) == (True, False, None), result.output
