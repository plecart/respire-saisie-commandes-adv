# Saisie des commandes ADV

Lit les bons de commande reçus (PDF, ou mails `.eml` portant un PDF) et en produit les commandes
de vente Odoo, une par fichier JSON, avec le rapport d'anomalies du lot.

## Lancement

1. Copier `.env.example` en `.env` et y renseigner `ANTHROPIC_API_KEY`. Le fichier `.env` n'est
   jamais versionné.
2. Lancer `docker compose up` (Docker Compose 2.24 ou plus) : le dossier `exemples/` est traité, et `sorties/` reçoit un JSON
   par commande produite et le rapport `rapport.md` ; le terminal affiche le tableau
   récapitulatif. Après une modification du code : `docker compose up --build`.

Sans Docker, avec [uv](https://docs.astral.sh/uv/), depuis la racine du dépôt :

```sh
uv run --env-file .env saisie-commandes exemples sorties
```
