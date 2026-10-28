# PDF incorrect remonté le 28 octobre 2026

Fichier reçu : `diagnostic-20261028-014609.pdf`.
SHA-256 : `7289797e578b5ee89e49111581767d46e985b3557eb254d7a68534b5f8a8a64f`.
Une page A3 portrait. Fichier et rendu conservés hors Git, dans le stockage privé.

## Constat visuel

Le PDF a été ouvert et rendu. Il ne répond pas à la demande de déclinaison :

- bandeau source « PLAN D'INTERVENTION » retourné dans une trame « PLAN
  D'ÉVACUATION », avec chevauchement des consignes ;
- trois VEI encore visibles ;
- textes, pastilles, niveau et légende retournés ;
- mentions SPECIMEN superposées ;
- ancienne présentation du BAT conservée à l'intérieur de la nouvelle trame.

La cause est le transfert de la **page BAT complète** sous une matrice globale.
Il ne sépare pas le bâtiment de l'habillage, ne sélectionne pas un VEI et
n'applique pas les contre-rotations individuelles. Ajuster seulement l'angle,
la marge ou la zone ne corrige pas ces défauts.

## Correction immédiate du raccordement

`api/orientation.php?action=compose` appelait `compose-diagnostic`, puis renvoyait
`ok: true` dès que le processus réussissait, malgré `production_ready: false`.
Les métadonnées et le rapport de diagnostic ne suffisaient pas à empêcher le
parcours de restituer un faux plan.

Désormais :

- `compose` répond HTTP 422, `ok: false`, code `GENERATION_NOT_IMPLEMENTED`,
  avant toute création de PDF ou lancement du moteur ;
- `capabilities` annonce `generation_available: false` et
  `diagnostic_available: true` ;
- le banc d'essai exige l'action explicite `compose-diagnostic` et renvoie
  `status: diagnostic_nonconforming`, `production_ready: false` et son avertissement
  au premier niveau de la réponse, avec un contrôle de cohérence du rapport ;
- les uploads, trames et anciens résultats ne sont pas supprimés.

Le frontend doit afficher l'erreur de génération. Lors de son adaptation, il
peut consulter `capabilities` pour afficher « Génération indisponible ».
**Ne pas remplacer simplement `compose` par `compose-diagnostic` dans le bouton
de génération** : cela réintroduirait le même problème sous un autre nom.

Sept scénarios HTTP passent sous PHP 8.4 : session anonyme, rôle non autorisé,
méthode GET, origine externe, refus de génération sans fichier, capacités et
contrôle du travail demandé dans le diagnostic explicite. Commande :

```sh
php tests/orientation-api.php
```

Les sessions et le serveur de test sont temporaires ; aucun appel Dolibarr ni
déploiement n'est effectué. La syntaxe de `api/orientation.php` a aussi été vérifiée.

## Transmission serveur

Après récupération de `main`, publier le fichier `api/orientation.php` selon le
[guide de déploiement](deploiement-serveur.md). Aucun changement de chemin ni de
venv n'est nécessaire pour ce refus explicite. Vérifier depuis une session admin
que l'ancien bouton affiche l'erreur et ne propose plus de nouveau PDF.
Le frontend React est dans un autre dépôt et n'a pas été modifié ici.

Ce correctif empêche de présenter le diagnostic comme une génération. Il ne
répare pas le moteur métier : séparation du dessin/habillage, sélection complète
des composants du VEI, contre-rotation des textes et symboles, cadrage après
contre-rotation et comparaison visuelle au BAT restent nécessaires. La référence
[Illustrator 1.0.14](audit-moteur-1.0.14.md) ne s'exécute pas sur le serveur PDF.
