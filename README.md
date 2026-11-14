# Saisie des commandes ADV

Lit les bons de commande reçus (PDF, ou mails `.eml` portant un PDF) et en produit les commandes
de vente Odoo, une par fichier JSON, avec le rapport d'anomalies du lot.

## Lancement

Le programme fait lire chaque document par Claude : il lui faut une clé d'API Anthropic. Elle se
crée dans la Claude Console, **rattachée à un workspace** : sans workspace, l'API refuse les
appels (erreur 400 qui réclame `anthropic-workspace-id`). Sans clé, en demander une de test au
mainteneur ; elle ne s'écrit que dans le fichier `.env` local, jamais versionné.

Sur un Mac, sans rien installer au préalable, depuis la racine du dépôt :

```sh
sh lancer.sh
```

Au premier lancement, le script demande la clé, saisie masquée, et l'écrit dans `.env` ; il
installe [uv](https://docs.astral.sh/uv/) dans `~/.local/bin` s'il manque, sans droits
administrateur ni modification des fichiers de configuration du shell ; uv fournit à son tour
Python 3.12, qu'il télécharge s'il manque, et les dépendances figées par `uv.lock`. Le dossier `exemples/` est alors traité :
`sorties/` reçoit un JSON par commande produite et le rapport d'anomalies `rapport.md`, et le
terminal affiche, pour chaque document, ses erreurs et avertissements, puis le JSON de sa
commande. Relancé, le script ne redemande ni ne réinstalle rien.
D'autres dossiers se donnent en arguments : `sh lancer.sh <dossier d'entrée> <dossier de sortie>`.

Qui a déjà uv, sur tout système : copier `.env.example` en `.env`, y renseigner
`ANTHROPIC_API_KEY`, puis, depuis la racine du dépôt :

```sh
uv run --locked --env-file .env saisie-commandes exemples sorties
```

## Relève de la boîte Gmail (bonus)

Renseigner dans `.env` l'adresse de la boîte Gmail dédiée, `GMAIL_ADDRESS`, et son mot de passe
d'application Google, `GMAIL_APP_PASSWORD`, puis lancer, depuis la racine du dépôt :

```sh
uv run --locked --env-file .env saisie-commandes-releve sorties
```

Toutes les 10 secondes, la commande relève les mails non lus de la boîte de réception. Chacun
est marqué lu et traité comme un `.eml` du dossier d'entrée : ses erreurs, ses avertissements et
le JSON de sa commande s'affichent dans le terminal, ses sorties vont dans `sorties/mail-<UID>/`.
Aucun mail n'est envoyé. Ctrl+C arrête la relève.

Une coupure réseau s'affiche, et la relève reprend au cycle suivant. Un mot de passe refusé, même
en cours de relève, l'arrête. Si le traitement d'un mail échoue (disque plein, dossier de sortie
inaccessible…), la relève s'arrête sur un message qui nomme le mail, `mail-<UID>` : déjà marqué
lu, il est à remettre non lu dans Gmail pour être retraité au prochain lancement.
