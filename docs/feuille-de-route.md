# Feuille de route DOEMO Studio

Mise à jour du 28 octobre 2026. Le moteur PDF et les modules existants conservent leurs périmètres. Le module de reconstruction architecturale est ajouté comme chantier distinct, destiné à produire des objets géométriques éditables dans Illustrator.

## Reconstruction architecturale

| Étape | État | Livrable et condition de passage |
| --- | --- | --- |
| Import et coordonnées | Prototype implémenté | PDF vectoriels récupérés avant analyse raster ; scan conservé ; régions de niveaux sur une même page sans déplacement de coordonnées. Tester les documents représentatifs, rotations et recadrages avant généralisation. |
| Reconstruction des murs | Prototype local implémenté | Paires de bords parallèles, axes et épaisseurs en unités du document, raccords explicites, export en un trait noir médian par mur. Les cadres, équipements et marches produisent encore des faux positifs. |
| Édition et validation | Prototype implémenté | Ajouter, supprimer, déplacer, prolonger, raccorder, changer l’épaisseur, réserver/corriger une ouverture, couper, annuler/refaire et sauvegarder. Les modifications annulent l’approbation. |
| Prototype Animalis | Généré sur R−1 et RDC, à valider | Scan reçu `mon-plan (1).pdf`, A3, une page, deux niveaux. Deux régions distinctes, référence conservée et propositions éditables. Zéro mur approuvé automatiquement. Pas de calibration métrique. |
| Segmentation spécialisée | À sélectionner et entraîner ou acquérir | Comparer code, poids ET données ; obtenir des droits commerciaux explicites. Worker ONNX isolé préparé, sans modèle fourni. Ajouter masques sémantiques, confiance et post-traitement topologique. |
| Portes, fenêtres, escaliers et pièces | À développer | Reconnaissance sémantique et géométrie paramétrique ; conserver les passages, escaliers et limites non résolus ; ne pas déduire un contour fermé en bouchant une ouverture. |
| Trois IA existantes | À intégrer aux services réels | Infrastructure précisée : RunPod RTX A6000, Qwen3.5-9B, PaddleOCR et RTMDet. Connecteurs isolés, API privée et contrôleur de tâches développés ; accès SSH et recette RunPod à terminer. Le checkpoint COCO est exclu du module murs. Réutiliser uniquement pour OCR, classification ou contrôle visuel mesurable ; ne pas leur déléguer la validation géométrique. |
| Éditeur Studio et persistance serveur | À intégrer | Raccordement à l’application React et aux sessions existantes, travaux privés, verrouillage/révisions, droits par projet, sauvegarde durable, journal d’audit et quotas. Le prototype est un éditeur HTML local avec traitement CLI. |
| Connecteur Illustrator | Contrat et import JSX préparés, branchement à faire | Adapter le connecteur local existant au contrat versionné ; calques natifs, objets indépendants, référence embarquée masquée, absence d’écrasement des fichiers. Recette sur la version Illustrator du dessinateur. |
| Apprentissage DOEMO | Journal local et export JSONL implémentés | Enregistre uniquement des murs explicitement approuvés et encore identiques à leur dernière approbation. Ajouter identité serveur, droits d’usage des documents, jeux séparés par chantier et versionnement avant entraînement. |

## Conditions de recette

Sur R−1 et RDC Animalis, le dessinateur doit confirmer les deux régions, contrôler la superposition de chaque mur, corriger les faux positifs et les raccords, vérifier chaque porte/fenêtre, puis approuver les géométries. L’échelle exige une cote linéaire ou un relevé fiable validé ; les surfaces 84 m² et 166 m² et la mention imprimée 1/100 ne constituent pas une calibration validée.

Le passage en production exige : aucun passage artificiellement fermé après correction ; aucune géométrie incertaine dans l’export approuvé ; objets de murs indépendants et calques vérifiés dans Illustrator ; conservation des coordonnées et de la référence ; rechargement fidèle des corrections ; absence d’entraînement sur une proposition non approuvée. Mesurer précision, rappel, erreur géométrique et temps de correction sur un jeu annoté avant d’annoncer un taux de qualité.

## Licences des approches étudiées

- [CubiCasa5K, licence du dépôt](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) : CC BY-NC 4.0, consultée le 28 octobre 2026. Pas d’intégration commerciale des éléments couverts sans droits complémentaires. Aucun poids ni jeu de données CubiCasa n’a été téléchargé ou intégré.
- [CubiCasa5K, méthode multi-tâches et FloorTrans](https://github.com/CubiCasa/CubiCasa5k) : segmentation et points de jonction sont utiles comme principes d’architecture. Les versions de PyTorch et CUDA du dépôt d’origine sont anciennes ; ne pas les ajouter à l’environnement du moteur PDF.
- [FloorplanTransformation, licence du code](https://github.com/art-programmer/FloorplanTransformation/blob/master/LICENSE) : MIT. Conserver les mentions si du code est repris ; la licence du code seule ne règle pas les droits des poids et données. Aucun code tiers de ce dépôt n’a été intégré.

Voir `reconstruction/README.md` pour exécuter et vérifier le prototype.

## Raccordement au module existant

La branche `feat/studio-host` de `julien547/doemo-app` possède déjà une feuille de route Studio Plans et un moteur v0.24. Le nouveau banc de ce dépôt ne remplace pas les fonctions précédemment livrées. L’adaptateur d’analyse v3 préserve la correspondance canevas/source ; les essais Animalis du moteur existant sont conservés séparément (264 et 133 propositions, aucune ouverture reconnue). L’ajout à la feuille de route de cette application est préparé dans une branche de revue distincte, sans données du plan ; sa publication suit l’autorisation du propriétaire.

## Priorité courante — module spécialisé DOEMO Walls 0.2

Le document de référence courant est `2(2).pdf`, page 1 exclusivement. Le module murs possède son contrat de masques architecturaux et son moteur d’axes ; il n’est pas une quatrième utilisation de RTMDet. Épaisseur détectée et trait graphique sont indépendants. L’API refuse la détection sémantique de murs tant qu’un modèle spécialisé et ses droits ne sont pas qualifiés.

Le prototype comprend : post-traitement de masques testé sur données synthétiques ; regroupement expérimental des contours du scan ; SVG noirs ouverts et JSX `/2` ; éditeur avec coupe, correction d’ouverture et annuler/refaire ; file OVH durable et idempotente ; authentification à signature et expiration ; runners séparés ; restauration non destructive ; découverte RunPod par volume/marqueur ; garde d’arrêt après 30 minutes réelles d’inactivité. Aucun déploiement, appel RunPod ou essai Adobe effectué.

L’essai page 1 produit 400 candidats bruts puis 101 axes de revue, dont 37 diagonaux, avec 221 traces isolées non interprétées. Aucune ouverture reconnue, aucun mur approuvé, aucune échelle validée. Le résultat reste incomplet et ne constitue pas un plan exploitable sans correction. Les taux de détection et le temps de correction nécessitent des annotations humaines.

Prochaines conditions de passage : accès SSH et réseau sécurisé ; audit puis tests fonctionnels des trois IA ; validation d’un modèle de segmentation et des droits sur code/poids/données ; annotation de la page 1 ; comparaison mesurée ; raccordement React/Illustrator et recette utilisateur. L’autorisation de publier la feuille de route dans la branche de revue est acquise ; aucun document client n’est versionné.

## État RunPod actualisé par le propriétaire

Les trois environnements Qwen3.5-9B, PaddleOCR et RTMDet ont été restaurés et vérifiés sur le nouveau Pod RTX A6000. CUDA, le cache PaddleX et les quatre fichiers de poids Qwen sont signalés présents. Cet état rapporté remplace les observations antérieures de chemins manquants. La session Codex n’a pas d’accès TCP/SSH opérationnel et ne prétend pas avoir vérifié directement ces installations ni exécuté les inférences.

Correctif local 0.2.1 : inventaire de l’identité du Pod, du montage et des interpréteurs ; restauration conditionnée au bon hôte et à l’espace disponible ; conservation des composants présents ; identité du worker vérifiée après migration ; provenance d’exécution des résultats. Les scripts de restauration sont désormais un secours : l’architecture permanente est une image Docker privée versionnée confiée par le propriétaire à une autre session.

Paquet 0.2.2 : lanceur du service d’inférence sans restauration, configuration vérifiée avant démarrage, client signé pour la page 1, reprise du même identifiant après un délai réseau, vérification de la provenance et du Pod. Le transport privé et l’exécution réelle des trois adaptateurs sur RunPod restent à vérifier. La segmentation architecturale reste distincte et non qualifiée.

## Livraison OVH 0.3.0

Le module de test web est publié dans [studio PR 1](https://github.com/julien547/studio/pull/1). Il ajoute l’import d’une page, la file de traitement locale, l’éditeur d’axes, la sauvegarde privée par utilisateur et l’export SVG validé, derrière la session DOEMO. Le lien du menu React est livré dans [doemo-app PR 2](https://github.com/julien547/doemo-app/pull/2).

La [procédure OVH](../reconstruction/ovh/DEPLOIEMENT_OVH.md) décrit l’installation isolée, le service systemd, le pont PHP sur socket Unix, la connexion RunPod facultative, la recette et le retour arrière. Le propriétaire a confié le déploiement réel à une autre session. Les branches ne sont pas fusionnées et le VPS n’a pas été modifié depuis ce fil.

50 tests Python passent. Un parcours Chromium avec PHP, socket Python et stockage réels en local valide l’import de la page 1, la correction, la sauvegarde et le SVG. L’extraction de cette livraison produit 327 propositions de revue ; ce comptage n’est pas une précision mesurée. La segmentation spécialisée, les inférences réelles RunPod et la recette Adobe restent à qualifier.

## Raccordement 0.3.1 — priorité avant l’essai IA

Le contrôle de connexion est implémenté dans Studio et dans une commande de recette
du service OVH actif. Une configuration renseignée ne prouve plus la disponibilité
des moteurs : le contrôle signé exige l’identité du worker courant, trois versions
locales vérifiées et les tests de démarrage réussis. 64 tests locaux passent ; les
tests d’inférence utilisent des doubles. Le branchement réel reste à faire suivant
la [transmission OVH–RunPod](../reconstruction/ovh/RACCORDEMENT_RUNPOD.md), par la
session désignée pour déployer. Aucun déploiement ni appel GPU réel effectué ici.

## Axes médians 0.3.2

L’extraction conserve maintenant les intervalles de bords non utilisés après un
premier appariement et n’étend pas les axes au-delà des observations communes.
L’éditeur ajoute la correction humaine « Deux bords → un axe médian », avec
conservation des portions restantes, protection des ouvertures et annuler/refaire.
88 tests Python et le parcours Chromium de cette correction passent.

La page 1 produit 381 propositions non validées. Les doubles traces et les faux
candidats ne sont pas tous résolus automatiquement : aucune qualité architecturale
n’est déduite du nombre de propositions. Voir la
[recette et les limites](../reconstruction/ovh/CORRECTION_AXES.md). La segmentation
spécialisée et les inférences réelles sur RunPod restent à qualifier séparément.
