# Saisie des commandes ADV

Lit les bons de commande reçus par l'ADV (PDF, ou mails `.eml` portant un PDF) et en prépare les
commandes de vente Odoo : un fichier JSON par commande, et le rapport des anomalies du lot. Le
process cible, du mail jusqu'à Odoo, est décrit dans la
[note de process](docs/note-de-process.md).

## Le cadre : les règles assumées

Ce sont des choix, pas des oublis, et ils suivent un principe : **quand un doute existe, la
machine ne décide pas seule**. Elle signale le doute avec son motif, et un humain tranche.

**L'IA lit, le code décide.** Claude recopie ce qui est imprimé : la nature du document
(commande, facture ou autre), le nom et le code postal de la pharmacie, le numéro de commande, la
date de livraison, puis pour chaque ligne l'EAN, la quantité, l'unité, les unités gratuites, le
prix catalogue, la ou les remises et le total, et enfin le total du document. Une valeur illisible
est signalée comme telle, jamais devinée. Le rapprochement avec les bases, les calculs et la
décision sont des règles écrites et testées, qui rendent toujours le même résultat.

**La base fait foi, pas le document.**

- **Pharmacie** : retrouvée par son nom, sans tenir compte de la casse, des accents, de la
  ponctuation ni des espaces, parmi les clients actifs. Si deux pharmacies actives portent ce nom,
  le code postal du document les départage. Si aucune n'est active, la recherche se fait parmi les
  inactives, et la commande porte un avertissement. L'adresse imprimée n'est pas une clé de
  recherche : elle peut être mal écrite ou mal lue.
- **Article** : retrouvé par son EAN. La désignation imprimée est ignorée, car chaque pharmacie
  nomme les produits à sa façon.
- **Prix** : comparés à aucun tarif. Seule la cohérence du document est contrôlée : quantité ×
  prix catalogue × (1 − remise) = total de la ligne, et somme des lignes = total du document, au
  centime près.

**Trois statuts.**

| Statut | Ce qui en sort | Cas |
| --- | --- | --- |
| **Bloqué** | pas de commande : le document va à l'ADV avec son motif | **Document** : pas un bon de commande (une facture, par exemple) ; aucune ligne de commande ; total HT absent, illisible ou incohérent avec la somme des lignes<br>**Pharmacie** : nom absent ou illisible ; pharmacie introuvable, ou ambiguë (homonymes que le code postal ne départage pas)<br>**Ligne** : EAN absent, illisible, invalide ou inconnu ; quantité, prix catalogue ou total de ligne absent ou illisible ; unité illisible ; quantité en colis ; unités gratuites accordées, ou leur nombre illisible ; remise illisible ; plusieurs remises ; total de ligne incohérent avec quantité × prix × (1 − remise)<br>**Mail** : aucun PDF en pièce jointe, ou plusieurs<br>**Lecture impossible** : PDF illisible ou protégé par un mot de passe, Claude indisponible, clé refusée, réponse inexploitable… (voir « [Choix techniques](#choix-techniques) ») |
| **Avertissement** | la commande, avec le point à vérifier | numéro de commande absent ou égal à « 0 » ; date de livraison absente, mal formée ou sans année ; code postal du document différent de celui de la fiche ; pharmacie inactive |
| **Accepté** | la commande, sans alerte | y compris un prix à 0,00 € (geste commercial écrit sur le document), une date de livraison passée (c'est une date souhaitée) ou une désignation différente de celle de la base |

**Ce qui n'est pas lu** : le texte libre et les annotations manuscrites, comme « passé cette
date, annuler le reliquat ». D'un mail, seules les pièces jointes en PDF comptent, les autres sont
ignorées : il en faut exactement une, et le corps du message n'est jamais lu.

Les sorties du lot fourni sont versionnées dans [`sorties/`](sorties/) : `rapport.md` en donne
le tableau récapitulatif et les motifs, document par document.

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
Python 3.12, qu'il télécharge s'il manque, et les dépendances figées par `uv.lock`. Le dossier
`exemples/` est alors traité : `sorties/` reçoit un JSON par commande produite et le rapport
d'anomalies `rapport.md`, et le terminal affiche, pour chaque document, ses erreurs et
avertissements, puis le JSON de sa commande. Relancé, le script ne redemande ni ne réinstalle
rien. D'autres dossiers se donnent en arguments :
`sh lancer.sh <dossier d'entrée> <dossier de sortie>`.

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

## Choix techniques

Les choix sont consignés dans l'[ADR 0001](docs/adr/0001-architecture-du-mvp.md).

- **Une seule voie de lecture : la page en image.** Chaque page est rendue en image et lue par un
  modèle vision, en un appel par document, avec une réponse contrainte par un schéma. Trois des
  cinq PDF fournis sont des scans dont le texte extractible ne contient que des champs
  d'anonymisation : la commande n'existe que dans l'image.
- **Claude Haiku 5.5 par défaut, le moins cher qui lit juste.** Comparé le 2026-11-13 aux
  lectures établies à la main, il reproduit le résultat attendu des cinq documents. Sur
  Commande_1, le tableau le plus dense, il décalait une ligne deux fois sur six avec des pages
  rendues à 150 dpi, et le contrôle des totaux a bloqué le document ; à 220 dpi, dix lectures sur
  dix sont justes. Claude Sonnet lisait Commande_1 juste dès 150 dpi, pour environ dix fois le
  prix. Le modèle se change par la variable `CLAUDE_MODEL`.
- **Une erreur ne fait pas tomber le lot.** Une lecture qui échoue bloque son seul document, avec
  le motif en clair. Une erreur temporaire de l'API est réessayée trois fois, deux minutes au plus
  par tentative.
- **Calculs exacts** : montants en décimal, arrondi au demi supérieur, tolérance d'un centime.
- **Référentiels** : les deux CSV fournis, chargés en mémoire au lancement. En production, clients
  et articles se lisent dans Odoo, qui fait foi.
- **Odoo** : [`odoo.py`](src/saisie_commandes/odoo.py) contient la fonction qui créerait la
  commande par XML-RPC. Elle est testée contre un faux serveur, jamais exécutée.
- **Python 3.12 et uv**, sans conteneur ; bibliothèques `anthropic`, `pymupdf` (rendu des pages)
  et `pydantic` (schéma de lecture).
- **Tests sans IA** : `uv run pytest` remplace Claude par les lectures attendues des documents,
  établies à la main ; couverture exigée de 80 % sur les règles métier. La CI lance lint, format
  et tests sous Linux, et `lancer.sh` sous macOS.

## Limites connues

- **Une pharmacie dont le nom diffère de la base est bloquée**, sauf par la casse, les accents,
  la ponctuation ou les espaces. Le rapprochement exige l'égalité du nom : c'est voulu, un humain
  tranche. Deux pharmacies actives de même nom et de même code postal ne sont pas départageables.
- **Le nom imprimé peut porter celui des titulaires** (« GRANDE PHARMACIE DU LAC Mmes Petit &
  Roux ») : le rapprochement dépend alors de la consigne de lecture donnée au modèle.
- **Colis, unités gratuites et doubles remises vont à un humain** : la base ne connaît pas le
  colisage des articles, et l'on ne sait pas si deux remises se cumulent ou s'enchaînent.
- **Les prix ne sont comparés à aucun tarif**, la base articles n'en portant aucun.
- **Les consignes écrites en texte libre sont perdues** (« annuler le reliquat ») : rien ne les
  signale à l'ADV.
- **Chaque document coûte un appel à l'IA**, même un PDF dont le texte serait lisible sans elle.
- **Une lecture juste ne prouve pas la fiabilité** : sur un tableau dense, le filet est le
  contrôle des totaux de ligne, qui bloque la lecture fausse au lieu de la laisser passer.
- **Mails** : un PDF qui n'est pas joint au premier niveau du mail n'est pas trouvé (envoi direct
  d'un scanner, mail signé, PDF dans un message transféré ou dans le corps mis en forme d'un
  message) : le mail est bloqué, faute de PDF en pièce jointe.
- **Un PDF de plus d'une centaine de pages ou de 32 Mo** dépasse les limites d'un appel : il est
  bloqué sur un motif technique qui ne dit pas « trop gros ».
- **L'envoi à Odoo n'a jamais tourné** contre une vraie instance.
- **Sans clé d'API, rien ne fonctionne** : aucune lecture n'est possible sans Claude.

## Avec deux semaines de plus

- Étudier un grand volume de bons de commande réels, et passer du temps avec l'équipe ADV pour
  recueillir ses blocages.
- Lire sans IA le texte des PDF qui en ont un vrai, pour réduire les coûts — en se gardant des
  scans dont le texte extractible est trompeur.
- Connaître le colisage de chaque article, pour convertir les colis au lieu de bloquer.
- Départager les homonymes par l'adresse complète, et rapprocher un nom mal écrit.
- Renvoyer à un humain tout document qui porte une consigne en texte libre.
- Une interface de brouillon : notification, correction et validation humaine.
- Un accusé de réception automatique à la pharmacie, et le rangement des mails traités dans la
  boîte, pour que l'ADV voie ce que l'automatisme a pris en charge.
- L'archivage des bons de commande PDF, reliés à leur commande Odoo.

## Temps passé

Estimation reconstituée depuis l'historique Git (horodatage des commits et des merges, à l'heure
du poste, UTC+1) et le journal de bord du projet ; elle sera corrigée par l'auteur.

| Jour | Plage | Travail |
| --- | --- | --- |
| 13 novembre | 12 h 49 → 0 h 12 | lecture de l'énoncé, analyse des cinq PDF et des deux CSV, ADR, découpage en issues (avant 17 h) ; cœur sans IA, lecture par Claude, réception des mails (17 h → 0 h) |
| 14 novembre | à partir de 9 h 59 | lancement sur macOS, README et note de process |

Soit environ 11 h 20 d'amplitude le premier jour, pauses non déduites, et la matinée du second.
Le temps de lecture de l'énoncé avant le premier commit n'est pas daté.
