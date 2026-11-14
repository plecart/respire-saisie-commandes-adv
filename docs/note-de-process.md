# Note de process — saisie des commandes ADV, du mail à Odoo

## Le cadre

L'outil prépare les commandes, il ne les confirme jamais. **Quand un doute existe, la machine ne
décide pas seule** : elle le signale avec son motif, et l'ADV tranche. L'IA lit le document, des
règles écrites décident. La base fait foi, pas le document : la pharmacie se retrouve par son nom,
l'article par son EAN, et les prix ne se comparent à aucun tarif, seule la cohérence des calculs
du document est contrôlée. Le texte libre et les annotations manuscrites ne sont pas lus. Le
détail des règles et des statuts est en tête du [README](../README.md).

## Le flux

![Flux du mail à Odoo](flux.png)

| Étape | Ce qui se passe | Qui |
| --- | --- | --- |
| 1. Mail | La pharmacie envoie son bon de commande à la boîte de l'ADV. | la pharmacie |
| 2. Réception | La boîte est relevée à intervalle régulier. Seules les pièces jointes en PDF comptent, les autres sont ignorées : il en faut exactement une, sinon le mail part à l'ADV avec son motif. | automatique |
| 3. Lecture | Chaque page est rendue en image et lue par Claude en un appel : il recopie les champs imprimés, et signale ce qu'il ne peut pas lire. | automatique (IA) |
| 4. Rapprochement | La pharmacie est retrouvée par son nom (et son code postal entre homonymes), chaque article par son EAN, dans les clients et articles d'Odoo. | automatique (règles) |
| 5. Statut | Chaque ligne et le total sont recalculés ; le document est accepté, signalé par un avertissement, ou bloqué. | automatique (règles) |
| 6. JSON | Tout document non bloqué donne sa commande au format `sale.order` ; le lot donne son rapport d'anomalies. | automatique |
| 7. Odoo | Une commande acceptée devient un devis à valider, une commande avec avertissement un devis signalé ; un document bloqué rejoint la file de l'ADV avec son motif. | automatique |
| 8. Revue humaine | L'ADV valide les devis, vérifie le point signalé, saisit ou fait corriger les documents bloqués. | l'ADV |

Le MVP couvre les étapes 2 à 6 : un dossier de PDF ou de mails `.eml` simule la boîte, les deux
CSV fournis tiennent lieu des référentiels d'Odoo, et la fonction de l'étape 7 est écrite, testée
à blanc, jamais exécutée.

## Les cas incertains et la revue humaine

Chaque doute devient un statut et un motif en clair, jamais une correction silencieuse.

- **Bloqué**, l'ADV reprend la main :
  - **Document** : pas un bon de commande (une facture, par exemple) ; aucune ligne de commande ;
    total HT absent, illisible ou incohérent avec la somme des lignes
  - **Pharmacie** : nom absent ou illisible ; pharmacie introuvable, ou ambiguë (homonymes que le
    code postal ne départage pas)
  - **Ligne** : EAN absent, illisible, invalide ou inconnu ; quantité, prix catalogue ou total de
    ligne absent ou illisible ; unité illisible ; quantité en colis ; unités gratuites accordées, ou
    leur nombre illisible ; remise illisible ; plusieurs remises ; total de ligne incohérent avec
    quantité × prix × (1 − remise)
  - **Mail** : aucun PDF en pièce jointe, ou plusieurs
  - **Lecture impossible** : PDF illisible ou protégé par un mot de passe, Claude indisponible, clé
    refusée, réponse inexploitable… (voir « [Choix techniques](../README.md#choix-techniques) » du
    README)
- **Avertissement**, l'ADV vérifie un point précis : numéro de commande absent ou « 0 », date de
  livraison absente, mal formée ou sans année, code postal différent de la fiche, pharmacie
  inactive.
- **Accepté**, l'ADV valide le devis comme toute commande.

Sur les documents fournis : la facture Document_4 est bloquée (elle aurait créé un doublon),
Commande_5 aussi (un EAN absent, un inconnu, une quantité en colis) ; Commande_1 (numéro « 0 »)
et Commande_2 (code postal) passent avec un avertissement, Commande_3 est acceptée. Les erreurs de
lecture sont rattrapées par le code : la clé de contrôle de l'EAN et la cohérence des calculs.
Une ligne mal alignée par le modèle a ainsi été bloquée, au lieu de produire une commande fausse.

## Le passage en production

**Déclenchement.** La boîte de commandes de l'ADV est relevée en IMAP à intervalle régulier ; le
dossier d'entrée reste, pour rejouer un document. Les clients et les articles se lisent dans
Odoo, qui fait foi.

**Monitoring**, par lot : le rapport, le taux de blocage et ses motifs, les erreurs de l'IA, le
coût du lot. Une alerte part si le taux de blocage dépasse un seuil, ou si aucune commande
n'arrive.

**Coûts**, mesurés le 2026-11-14 : un appel réel par document sur les cinq PDF fournis, jetons
relevés dans la réponse de l'API, au tarif de Claude Haiku 5.5 lu le même jour sur la page
[Pricing](https://platform.claude.com/docs/en/about-claude/pricing) d'Anthropic — 0,10 $ par
million de jetons d'entrée et 0,50 $ par million de jetons de sortie, pour des requêtes
jusqu'à 100 000 jetons.

| Document | Lignes | Jetons d'entrée | Jetons de sortie | Coût |
| --- | --- | --- | --- | --- |
| Commande_1 | 13 | 7 286 | 2 002 | 0,0017 $ |
| Commande_2 | 5 | 7 286 | 823 | 0,0011 $ |
| Commande_3 | 18 | 7 286 | 2 289 | 0,0019 $ |
| Commande_5 | 6 | 7 286 | 1 090 | 0,0013 $ |
| Document_4 | 8 | 7 286 | 1 646 | 0,0016 $ |
| **Les cinq** | | **36 430** | **7 850** | **0,0076 $** |

Un document d'une page coûte donc environ 0,15 centime de dollar, soit 1,50 $ les mille. La
sortie varie d'une lecture à l'autre : 8 100 jetons environ pour les cinq lors de la mesure du
2026-11-13. Au regard de la revue humaine, le document le plus cher, à 0,0019 $, coûte moins
qu'une seule seconde de travail de l'ADV dès que son heure revient à plus de 6,84 $
(0,0019 $ × 3 600 secondes) : le coût récurrent qui compte est le temps de l'ADV sur les
documents signalés ou bloqués. Ce temps par document et le coût horaire de l'ADV sont à poser
par Respire.

**Sécurité.**

- La clé d'API vit dans un coffre à secrets.
- Le compte de service Odoo n'a que le droit de créer des devis.
- Des données clients partent chez un tiers : l'image de chaque bon de commande est envoyée à
  l'API d'Anthropic, avec le nom et l'adresse de la pharmacie, parfois le nom de ses titulaires,
  les articles, les prix et les remises. Les conditions commerciales d'Anthropic (Commercial
  Terms, § B « Customer Content », en vigueur au 17 juin 2025, lues le 2026-11-14) l'encadrent :
  « Anthropic may not train models on Customer Content from Services ». Selon sa Privacy Center
  (« How long do you store my organization's data? », 1er juillet 2026, lue le 2026-11-14), les
  entrées et sorties de l'API sont effacées sous 30 jours, et une rétention nulle est possible
  sur accord.
- `pymupdf`, qui rend les pages en images, est sous licence AGPL-3.0 ou commerciale : à prendre
  en compte avant la mise en production.

## Développer en interne ou acheter

**En interne, avec un seuil de bascule.** La valeur de l'outil est dans les règles propres à
Respire — le rapprochement sur ses référentiels, ses statuts, sa revue humaine — et ces règles
tiennent en peu de code. La lecture, elle, est assurée par un modèle généraliste, sans
développement spécifique à un format de document.

Les coûts récurrents des deux voies, comparés honnêtement : en interne, les appels à l'IA
(environ 1,50 $ les mille documents d'une page, ci-dessus), la maintenance des règles et la revue
humaine ; à l'achat, l'abonnement et la même revue humaine. Le prix d'un abonnement dépend de
l'éditeur et du volume : il n'a pas été relevé ici. L'achat se reconsidère si le volume ou la
variété des formats fait coûter la revue humaine plus cher qu'un abonnement : le taux de blocage,
suivi par le monitoring, est l'indicateur de cette bascule.
