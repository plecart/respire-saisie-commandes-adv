#!/bin/sh
# Lance le traitement des bons de commande sur macOS, sans rien installer au préalable :
#
#   sh lancer.sh [dossier d'entrée] [dossier de sortie]      (défauts : exemples sorties)
#
# Sans `.env`, la clé d'API est demandée par une saisie masquée, puis écrite dans `.env`. Sans
# uv, l'installeur officiel le pose dans ~/.local/bin, sans droits administrateur ni
# modification des fichiers de configuration du shell. Relancé, le script ne redemande ni ne
# réinstalle rien.
set -eu

# À la racine du dépôt, d'où que le script soit lancé.
CDPATH= cd "$(dirname "$0")"
input=${1:-exemples}
output=${2:-sorties}

if [ ! -f .env ]; then
  # Sans terminal, rien ne peut être saisi : arrêt avant tout téléchargement.
  if [ ! -t 0 ]; then
    echo "lancer.sh : le fichier .env manque, et la clé d'API (ANTHROPIC_API_KEY) ne se" >&2
    echo "demande qu'à un terminal. Copier .env.example en .env et y renseigner la clé," >&2
    echo "ou relancer depuis un terminal." >&2
    exit 1
  fi
  # L'écho du terminal est rétabli à toute sortie pendant la saisie, interruption comprise.
  trap 'stty echo' EXIT
  trap 'exit 130' HUP INT TERM
  printf "Clé d'API Anthropic (ANTHROPIC_API_KEY), saisie masquée : " >&2
  stty -echo
  read -r api_key || true
  stty echo
  trap - EXIT HUP INT TERM
  echo >&2
  if [ -z "$api_key" ]; then
    echo "lancer.sh : aucune clé saisie, .env n'est pas écrit." >&2
    exit 1
  fi
  # Lisible par l'utilisateur seul.
  (umask 077 && printf 'ANTHROPIC_API_KEY=%s\n' "$api_key" > .env)
fi

if command -v uv > /dev/null 2>&1; then
  uv=uv
else
  uv_dir=$HOME/.local/bin
  uv=$uv_dir/uv
  if [ ! -x "$uv" ]; then
    # Le PATH du shell courant ignore le nouveau dossier : uv s'appelle par son chemin.
    curl -LsSf https://astral.sh/uv/install.sh |
      env UV_INSTALL_DIR="$uv_dir" UV_NO_MODIFY_PATH=1 sh
  fi
fi

exec "$uv" run --locked --env-file .env saisie-commandes "$input" "$output"
