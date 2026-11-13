# ADR 0001 — Architecture du MVP de saisie de commandes ADV

- **Statut** : accepté
- **Date** : 2026-11-13

## Contexte

L'ADV de Respire reçoit par mail des bons de commande de pharmacies en PDF (exports texte, scans) et les ressaisit dans Odoo. Le MVP doit, à partir d'un dossier de documents, produire pour chacun une commande au format `sale.order` ou signaler pourquoi il ne peut pas la produire. Il doit se lancer en une commande.

Contraintes : aller vite, rester simple, ne pas laisser la machine décider seule quand un doute existe.

Constats tirés des documents fournis :

- trois documents sur cinq sont des scans dont la couche texte ne contient que des champs d'anonymisation : le contenu utile n'existe que dans l'image ;
- un document n'est pas une commande mais une facture ;
- aucun document ne porte de CIP ni de numéro client ;
- la base articles ne contient aucun prix.

## Décisions

### 1. Langage : Python 3.12

Bibliothèques : `pymupdf` (rendu des pages), SDK du fournisseur d'IA, `pydantic` (schéma d'extraction), `pytest`. La fonction Odoo utilise `xmlrpc.client` de la bibliothèque standard.

### 2. Une seule voie de lecture : la page en image, lue par un modèle vision

Chaque page du PDF est rendue en image puis envoyée à un modèle vision, en un seul appel par document, avec une sortie contrainte par un schéma JSON.

- On lit ce qu'un humain voit, y compris quand la couche texte du PDF est trompeuse.
- Une seule voie à écrire, tester et maintenir.
- Écarté pour le MVP : lire le texte natif sans IA quand c'est possible. C'est une optimisation de coût, prévue pour la suite.

### 3. Le modèle extrait, le code décide

Le modèle renvoie uniquement ce qui est imprimé : type de document, nom et code postal de la pharmacie, numéro de commande, date de livraison, et pour chaque ligne l'EAN, la quantité, l'unité, les unités gratuites, le prix catalogue, la ou les remises, le total de ligne, puis le total du document. Une valeur illisible est renvoyée comme telle, jamais devinée. Le texte libre et les annotations ne sont pas extraits.

Rapprochement client et article, calculs et décision de statut sont du Python déterministe, couvert par des tests.

### 4. Fournisseur d'IA : Claude (API Anthropic), modèle configurable

Modèle par défaut : le moins cher qui lit correctement les cinq documents fournis, comparé à la vérité terrain établie à la main. Le nom du modèle est une variable d'environnement.

- Sortie structurée garantie par schéma, SDK Python simple, image ou PDF acceptés.
- Coût de l'ordre du centime par document au plus (chiffrage détaillé dans la note de process).
- Les erreurs de lecture sont rattrapées par le code : clé de contrôle EAN-13, cohérence des calculs.
- Alternative étudiée : Mistral OCR (spécialisé documents, hébergement européen à confirmer).

### 5. Référentiels : les deux CSV chargés en mémoire

235 articles et 15 clients, lus en texte au démarrage. C'est une solution de MVP : en production, clients et articles sont lus dans Odoo, qui est la source de vérité.

### 6. Règles métier

Client :

1. recherche par nom normalisé (casse, accents, ponctuation, espaces), égalité stricte, parmi les clients actifs ;
2. plusieurs actifs du même nom : le code postal du document départage ;
3. aucun actif : recherche parmi les inactifs, la commande est produite avec un avertissement.

Article : par EAN uniquement. La désignation imprimée est ignorée.

Calcul : quantité × prix catalogue × (1 − remise) = total de ligne, et somme des lignes = total du document. Montants en `Decimal`, arrondi au demi supérieur, tolérance d'un centime.

| Statut | Cas |
| --- | --- |
| **Bloqué** (pas de JSON) | document qui n'est pas une commande ; client introuvable ou ambigu ; EAN absent ou inconnu ; quantité ou prix illisible ; quantité en colis ; unités gratuites renseignées ; deux remises sur une ligne ; calcul incohérent ; mail sans PDF unique |
| **Avertissement** (JSON produit) | numéro de commande absent ou égal à « 0 » ; date de livraison absente, mal formée ou sans année ; code postal du document différent de celui de la base ; client inactif |
| **Accepté sans alerte** | prix à 0,00 € ; date de livraison passée ; désignation différente de celle de la base |

### 7. Entrées et sorties

- Entrée : un dossier de documents (PDF, ou fichiers `.eml` pour simuler l'arrivée d'un mail).
- Sortie : un fichier JSON par commande produite, un rapport d'anomalies pour l'ensemble du lot, et un résumé dans le terminal.

### 8. Envoi à Odoo isolé

Un fichier dédié contient la fonction qui créerait la commande par XML-RPC. Elle est écrite et testée à blanc, jamais exécutée.

### 9. Lancement en une commande : uv, et un script d'amorçage pour macOS

Le programme se lance par `uv run --locked saisie-commandes <entrée> <sortie>` : uv installe la version de Python et les dépendances figées par `uv.lock`. Pour qui n'a pas uv, `sh lancer.sh` (macOS) l'installe dans le dossier de l'utilisateur, sans droits administrateur, puis lance le programme.

Pas de conteneur, de base de données ni de service annexe. La clé d'API est lue dans un fichier `.env` non versionné : elle est indispensable, sans elle aucune extraction n'est possible.

### 10. Boîte mail (bonus)

Une boîte Gmail dédiée, relevée en IMAP à intervalle régulier, alimente le même traitement que le dossier. Le webhook Gmail est écarté : il impose Google Cloud Pub/Sub et OAuth pour un gain nul à ce stade.

## Conséquences

- Chaque document coûte un appel d'IA, même quand son texte serait lisible sans.
- Le programme ne fonctionne pas sans clé d'API : la personne qui le lance fournit la sienne ou, à défaut, une clé de test que le mainteneur lui prête, liée à un compte de service et adossée à un crédit prépayé.
- Le rapprochement client par égalité stricte du nom bloque à la moindre variante d'écriture : c'est voulu, un humain tranche.
- Deux pharmacies actives de même nom dans la même ville ne sont pas départageables.
- Les colis, les unités gratuites et les doubles remises sont renvoyés à un humain.
- Les prix ne sont comparés à aucun tarif de référence.
