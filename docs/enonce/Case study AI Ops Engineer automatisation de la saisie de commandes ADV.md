# Case study — AI Ops Engineer : automatisation de la saisie de commandes ADV

Nov 6, 2026 · @Olivier van Stratum

## Contexte

Respire est une marque française de dermocosmétique naturelle, vendue en ligne et dans environ 6000 pharmacies. Chaque jour, l'équipe ADV (administration des ventes) reçoit par mail les bons de commande des pharmacies, en PDF.

Ces PDF viennent de logiciels d'officine différents : des exports texte, des scans, parfois des documents annotés à la main. L'ADV ressaisit chaque commande à la main dans notre ERP, **Odoo**, sous forme de bon de commande. La saisie est lente et source d'erreurs : mauvais article, prix ou remise erronés, client mal rattaché et peut nécessiter des aller-retours avec le client (rupture de stock).

## Le défi

À chaque mail reçu, on veut que la commande soit prête dans Odoo, et que l'ADV n'intervienne que lorsque c'est nécessaire. On te demande deux choses :

1. **Proposer le process cible**, du mail reçu jusqu'à la commande dans Odoo : les étapes, qui intervient, ce qui est automatique et ce qui passe en revue humaine.
2. **Construire un MVP du cœur du process** : à partir des documents fournis, produire pour chacun une commande structurée, prête à être créée dans Odoo, et signaler ce qui pose problème.

On n'attend pas un outil prêt pour la production, ni une interface soignée. On veut voir comment tu découpes le problème, ce que tu automatises en premier et comment tu gères les cas où la machine ne doit pas décider seule.

## Ce que tu reçois

| Élément | Format | Contenu |
| --- | --- | --- |
| Documents reçus par l'ADV | 4 PDF (données anonymisées) | Tels que reçus par mail |
| Base articles | CSV | SKU (référence interne Odoo), EAN, désignation, gamme, format, parfum, statut archivé, SKU de référence (`universal_sku`) |
| Base clients | CSV | ID client, CIP, nom, adresse, groupement, classification (15 pharmacies) |
| Format cible Odoo | JSON (ci-dessous) | Champs d'une commande de vente (`sale.order`) |

Pour chaque document, le MVP doit produire une commande au format suivant. Les clients sont identifiés par leur id\_client, les articles par leur SKU.

```json
{
  "partner_id": 10103,
  "client_order_ref": "208532",
  "commitment_date": "2026-01-13",
  "order_line": [
    {
      "product_ref": "DSTPFC50",
      "product_uom_qty": 12,
      "price_unit": 10.75,
      "discount": 35.0
    }
  ]
}
```

## Livrables attendus

1. **Une note de process** d'une à deux pages : un schéma du flux, depuis le mail jusqu'à Odoo ; la gestion des cas incertains et de la revue humaine ; le passage en production (déclenchement, monitoring, coûts, sécurité). Indique aussi si tu développerais cet outil en interne ou si tu achèterais une solution existante, et pourquoi.
2. **Le code du MVP** (repo Git ou archive), lançable en une commande. En entrée, un dossier de documents ; en sortie, un JSON par commande et un rapport des anomalies détectées.
3. **Les sorties obtenues** sur les 4 documents fournis.
4. **Un README** : tes choix techniques, les limites connues, ce que tu ferais avec deux semaines de plus, et le temps réellement passé.

## Règles du jeu

- **Temps** : n'y passe pas des jours. Mieux vaut un MVP limité qui fonctionne et une note claire qu'un outil complet à moitié fini.
- **Outils** : langage, librairies et API au choix.
- **Odoo** : tu n'as pas accès à notre instance. Le MVP s'arrête au JSON au format cible. Écris la fonction qui l'enverrait à Odoo (API XML-RPC ou JSON-RPC) sans l'exécuter.
- **Mails** : simule leur arrivée, par exemple avec un dossier surveillé ou des fichiers .eml. La connexion à une vraie boîte mail n'est pas demandée.
- **Bonus (facultatif)** : crée une boite mail ou une instance sur laquelle on peut déposer un fichier et récupérer l'output.
