# Saisie des commandes ADV

Lit les bons de commande reçus (PDF, ou mails `.eml` portant un PDF) et en produit les commandes
de vente Odoo, une par fichier JSON, avec le rapport d'anomalies du lot.

## Lancement

1. Copier `.env.example` en `.env` et y renseigner `ANTHROPIC_API_KEY`. Le fichier `.env` n'est
   jamais versionné.
2. Lancer `docker compose up` (Docker Compose 2.24 ou plus) : le dossier `exemples/` est
   traité, et `sorties/` reçoit un JSON par commande produite et le rapport `rapport.md` ; le
   terminal affiche le tableau récapitulatif. Après une modification du code :
   `docker compose up --build`.

Sans Docker, avec [uv](https://docs.astral.sh/uv/), depuis la racine du dépôt :

```sh
uv run --env-file .env saisie-commandes exemples sorties
```

## Relève de la boîte Gmail (bonus)

Renseigner dans `.env` l'adresse de la boîte Gmail dédiée, `GMAIL_ADDRESS`, et son mot de passe
d'application Google, `GMAIL_APP_PASSWORD`, puis lancer, depuis la racine du dépôt :

```sh
uv run --locked --env-file .env saisie-commandes-releve sorties
```

Toutes les 10 secondes, la commande relève les mails non lus de la boîte de réception. Chacun
est marqué lu et traité comme un `.eml` du dossier d'entrée : son tableau récapitulatif s'affiche
dans le terminal, ses sorties vont dans `sorties/mail-<UID>/`. Aucun mail n'est envoyé. Ctrl+C
arrête la relève.
