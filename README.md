# Saisie des commandes ADV

Lit les bons de commande (PDF, ou mails `.eml` portant un PDF) et en prépare les commandes de
vente Odoo : un JSON par commande et un rapport d'anomalies. Le process est décrit dans la
[note de process](docs/note-de-process.md). Les sorties du lot fourni sont dans
[`sorties/`](sorties/).

## Lancement

Il faut une clé d'API Anthropic, créée dans la Claude Console **rattachée à un workspace** (sans
quoi l'API répond 400). Elle ne s'écrit que dans `.env`, jamais versionné.

Sur Mac, sans rien installer, depuis la racine du dépôt :

```sh
sh lancer.sh
```

Le script demande la clé, installe uv au besoin (sans droits administrateur), traite `exemples/`
vers `sorties/` et affiche erreurs, avertissements et JSON de chaque document. Autres dossiers :
`sh lancer.sh <entrée> <sortie>`.

Avec uv, sur tout système : copier `.env.example` en `.env`, y mettre `ANTHROPIC_API_KEY`, puis :

```sh
uv run --locked --env-file .env saisie-commandes exemples sorties
```

**Relève Gmail (bonus)** : renseigner `GMAIL_ADDRESS` et `GMAIL_APP_PASSWORD` dans `.env`, puis
`uv run --locked --env-file .env saisie-commandes-releve sorties`. Toutes les 10 s, les mails non
lus sont marqués lus et traités vers `sorties/mail-<UID>/` ; Ctrl+C arrête.

## Choix techniques

Détaillés dans l'[ADR 0001](docs/adr/0001-architecture-du-mvp.md).

- **L'IA lit, le code décide** : Claude recopie le document ; rapprochement, calculs et statut
  sont des règles écrites et testées.
- **Une seule voie de lecture, la page en image**, un appel par document, réponse contrainte par
  un schéma : trois des cinq PDF sont des scans sans texte exploitable.
- **Claude Haiku 5.5**, le moins cher qui lit juste : comparé le 2026-11-13 aux lectures faites à
  la main, il reproduit les cinq documents à 220 dpi (10 sur 10 sur Commande_1 ; à 150 dpi, une
  ligne décalée deux fois sur six). Sonnet lisait juste dès 150 dpi, pour environ dix fois le
  prix. Variable `CLAUDE_MODEL`.
- **Une erreur ne fait pas tomber le lot** : seul son document est bloqué, motif en clair. Erreur
  temporaire de l'API : trois essais, deux minutes au plus chacun.
- **Calculs en décimal**, arrondi au demi supérieur, tolérance d'un centime.
- **Référentiels** : les deux CSV, en mémoire. En production, Odoo fait foi.
- **Odoo** : [`odoo.py`](src/saisie_commandes/odoo.py) crée la commande par XML-RPC ; testée
  contre un faux serveur, jamais exécutée.
- **Python 3.12 et uv**, sans conteneur ; `anthropic`, `pymupdf`, `pydantic`.
- **Tests sans IA** (`uv run pytest`) : Claude est remplacé par les lectures attendues ;
  couverture de 80 % exigée. La CI lance lint, format et tests sous Linux, `lancer.sh` sous macOS.

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

Reconstitué depuis l'historique Git (UTC+1) et le journal de bord ; à corriger par l'auteur.

- **13 novembre, 12 h 49 → 0 h 12** (≈ 11 h 20, pauses comprises) : énoncé, analyse des PDF et
  CSV, ADR, issues, puis cœur sans IA, lecture par Claude et mails.
- **14 novembre, matinée** : lancement sur macOS, README et note de process.

La lecture de l'énoncé avant le premier commit n'est pas datée.
