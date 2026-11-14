#!/bin/sh
# Lance la relève de la boîte Gmail sur macOS, sans rien installer au préalable :
#
#   sh lancer.sh
#
# Sans `.env`, la clé d'API est demandée par une saisie masquée, puis écrite dans `.env`. Sans
# uv, l'installeur officiel le pose dans ~/.local/bin, sans droits administrateur ni
# modification des fichiers de configuration du shell. Uv installe ensuite, s'ils manquent,
# Python et les dépendances figées par `uv.lock`, puis lance la relève, sorties dans `sorties/`.
# Relancé, le script ne redemande, ne télécharge ni ne réinstalle rien.
set -eu

# À la racine du dépôt, d'où que le script soit lancé : `.env` et `uv.lock` s'y trouvent.
CDPATH= cd "$(dirname "$0")"

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
  # Écho coupé avant l'invite, comme `getpass` de Python : rien de tapé dès l'invite ne s'affiche.
  stty -echo
  printf "Clé d'API Anthropic (ANTHROPIC_API_KEY), saisie masquée : " >&2
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
    # Le code d'un tube est celui de sa dernière commande : un curl en échec n'arrête rien.
    if [ ! -x "$uv" ]; then
      echo "lancer.sh : l'installation d'uv a échoué (vérifiez la connexion à Internet)." >&2
      exit 1
    fi
  fi
fi

exec "$uv" run --locked --env-file .env saisie-commandes-releve sorties
