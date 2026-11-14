# Saisie des commandes ADV

Lit les bons de commande (PDF, ou mails `.eml` portant un PDF) et en prépare les commandes de
vente Odoo : un JSON par commande et un rapport d'anomalies. Le process est décrit dans la
[note de process](docs/note-de-process.md). Les sorties du lot fourni sont dans
[`sorties/`](sorties/).

## Lancement

1. Placer à la racine du dépôt un fichier `.env` contenant la clé d'API et la boîte Gmail :

   ```sh
   ANTHROPIC_API_KEY=<clé d'API Anthropic>
   GMAIL_ADDRESS=<adresse Gmail>
   GMAIL_APP_PASSWORD=<mot de passe d'application>
   ```

2. Sur Mac, depuis la racine du dépôt :

   ```sh
   sh lancer.sh
   ```

   Le script télécharge seulement ce qui manque (uv, Python, dépendances), puis lance la relève
   de la boîte Gmail. Relancé, il ne télécharge plus rien.

3. Envoyer à l'adresse Gmail un mail portant un PDF. Toutes les 10 secondes, les mails non lus
   sont traités : le résultat s'affiche dans le terminal et va dans `sorties/mail-<UID>/`.
   Ctrl+C arrête.

## Traiter un dossier

Avec uv installé, sur tout système (sur Mac après `lancer.sh`, `~/.local/bin/uv` s'il n'est pas
sur le PATH) :

```sh
uv run --locked --env-file .env saisie-commandes exemples sorties
```

Un JSON par commande et `rapport.md` vont dans `sorties/`, et le terminal affiche le résultat de
chaque document. Les mails `.eml` portant un PDF se traitent de même : deux sont dans `exemples/`,
`Mail_valide.eml` et `Mail_sans_piece_jointe.eml`.

## Choix techniques

- **L'IA lit, le code décide** : Claude recopie le document ; rapprochement, calculs et statut
  sont des règles écrites et testées.
- **Une seule voie de lecture, la page en image**, un appel par document, réponse contrainte par
  un schéma : trois des cinq PDF sont des scans sans texte exploitable.
- **Claude Haiku 5.5**, le moins cher qui lit juste : il reproduit les cinq documents lus à la
  main, pages rendues à 220 dpi. Sonnet lit aussi juste, pour environ dix fois le prix.
- **Une erreur ne fait pas tomber le lot** : seul son document est bloqué, motif en clair. Erreur
  temporaire de l'API : trois essais, deux minutes au plus chacun.
- **Calculs en décimal**, arrondi au demi supérieur, tolérance d'un centime.
- **Référentiels** : les deux CSV, en mémoire. En production, Odoo fait foi.
- **Odoo** : [`odoo.py`](src/saisie_commandes/odoo.py) crée la commande par XML-RPC ; testée
  contre un faux serveur, jamais exécutée.
- **Python 3.12 et uv**, sans conteneur ; `anthropic`, `pymupdf`, `pydantic`.
- **Tests sans IA** (`uv run pytest`) : Claude est remplacé par les lectures attendues ;
  couverture de 80 % exigée. La CI lance lint, format et tests sous Linux, `lancer.sh` sous
  macOS.

## Limites connues

- Une pharmacie n'est trouvée que par égalité de nom (casse, accents, ponctuation et espaces
  près) ; deux homonymes actives au même code postal ne se départagent pas.
- Un nom imprimé avec ceux des titulaires dépend de la consigne de lecture du modèle.
- Colis, unités gratuites et doubles remises vont à un humain : colisage inconnu, cumul des
  remises incertain.
- Aucun prix n'est comparé à un tarif : la base n'en porte pas.
- Les consignes en texte libre (« annuler le reliquat ») sont perdues sans signalement.
- Chaque document coûte un appel à l'IA, même un PDF au texte lisible.
- Une lecture juste ne prouve pas la fiabilité : sur un tableau dense, seul le contrôle des
  totaux de ligne bloque une lecture fausse.
- Un PDF qui n'est pas au premier niveau du mail (scanner, mail signé, transfert, corps mis en
  forme) n'est pas trouvé : le mail est bloqué.
- Un PDF de plus d'une centaine de pages ou de 32 Mo est bloqué sur un motif technique qui ne dit
  pas « trop gros ».
- L'envoi à Odoo n'a jamais tourné contre une vraie instance.
- Sans clé d'API, rien ne fonctionne.

## Avec deux semaines de plus

- Étudier un grand volume de bons réels et les blocages de l'équipe ADV.
- Lire sans IA les PDF au vrai texte, en se gardant des scans au texte trompeur.
- Connaître le colisage, pour convertir les colis au lieu de bloquer.
- Départager les homonymes par l'adresse, rapprocher un nom mal écrit.
- Renvoyer à un humain tout document portant une consigne en texte libre.
- Une interface de brouillon : notification, correction, validation.
- Accusé de réception à la pharmacie et rangement des mails traités.
- Archiver les PDF, reliés à leur commande Odoo.

## Temps passé

De la compréhension du sujet à l'analyse du contenu et des PDF, aux planifications, au
développement et au test, environ 2 jours.
