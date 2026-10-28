# Contrôler les doubles axes — livraison 0.3.5

La règle DOEMO est **un mur physique = un seul trait noir plein sur son axe médian**.
Les portes et passages interrompent le trait. L’épaisseur graphique reste indépendante
de l’épaisseur physique ; aucune échelle métrique n’est déduite.

Cette livraison repère les paires de propositions proches dans les projets existants,
puis aide le dessinateur à les corriger. Elle ne détermine pas automatiquement si
deux traces appartiennent au même mur. Le modèle sémantique spécialisé reste à
sélectionner et qualifier, indépendamment de RTMDet COCO.

## Dans l’éditeur

1. Ouvrir le projet, puis **Doubles axes possibles** dans le panneau de correction.
2. Choisir une paire et cliquer **Voir les deux traces**. Le cadrage montre les deux
   objets en bleu sur le plan original ; les tracés exportés restent noirs.
3. Si les deux traces sont les bords d’un même mur, utiliser **Même mur → axe médian**.
   La portion commune devient un axe unique à valider. Les parties qui dépassent
   restent indépendantes. La commande conserve sa protection des ouvertures : elle
   refuse les objets portant des ouvertures renseignées et ne les efface pas pour
   permettre la fusion. Contrôler et corriger ces cas individuellement.
4. S’il s’agit de deux murs physiques distincts, cliquer **Confirmer deux murs distincts**
   et renseigner le motif de cette interprétation. Les deux murs restent indépendants.
   Cette décision ne valide pas les murs eux-mêmes.
5. Deux axes exactement superposés doivent être corrigés ou le doublon supprimé.
   Ils ne peuvent pas être confirmés distincts. Pour supprimer, sélectionner dans
   le plan la trace effectivement redondante, puis utiliser **Supprimer**.
6. Vérifier le résultat, valider chaque mur et **Enregistrer sur OVH**.

Annuler/refaire s’applique aux corrections et aux décisions. La confirmation de deux
murs distincts est liée à leurs identifiants, coordonnées, épaisseurs et ouvertures.
Une modification de ces données impose un nouvel examen. Le JSON conserve les
décisions et leur motif ; OVH attribue les nouvelles décisions à l’utilisateur
authentifié, y compris dans le journal.

## Export et apprentissage

Le SVG validé et le contrat Illustrator refusent les paires encore ambiguës dont
**les deux murs sont approuvés**. Le SVG de revue reste disponible pour préparer les
corrections. Un candidat en attente n’entre jamais dans l’export validé.

L’export d’apprentissage exclut tout mur impliqué dans une paire non résolue, y
compris si l’autre proposition est encore en attente. Les autres corrections
approuvées et inchangées restent exportables. Les confirmations de murs distincts
sont jointes aux enregistrements concernés. Aucun entraînement n’est déclenché.

## Portée du contrôle

Le contrôle compare les axes à moins de 24 **unités du document**, presque parallèles
(1 degré), ayant au moins une portion commune de 6 unités. Il soustrait les ouvertures
avant comparaison. Il ne relie jamais deux segments séparés par un passage et ne
modifie aucune géométrie. Ces tolérances ne constituent ni une mesure en mètres ni
une estimation de confiance. Des murs distincts peuvent donc être signalés ; des
doubles traces très déformées, éloignées ou courtes peuvent ne pas l’être.

Le contrôle ne remplace pas la revue de l’ensemble du plan. Les cadres, mobiliers,
marches et fenêtres encore présents dans les propositions restent à interpréter
ou supprimer. La reconnaissance sémantique des murs n’est pas déclarée acquise.

## Vérification

128 tests Python passent, avec comparaison des calculs Python/JavaScript pour les
rotations, sens inversés, ouvertures et décisions. Le parcours Chromium vérifie :
fusion vers un axe noir, refus de l’export ambigu, confirmation explicite de deux
murs, invalidation après modification, annuler/refaire, rechargement JSON et
préservation des ouvertures. Le contrôle serveur de l’export et l’attribution à
l’utilisateur authentifié sont aussi testés.

Sur la page 1 de `2(2).pdf`, les 381 propositions existantes donnent **468 paires
proches**, concernant 294 propositions. Ce sont des signalements géométriques,
**pas 468 doublons identifiés**. Aucun mur n’a été modifié ou approuvé, aucune échelle
n’a été ajoutée. La vérité terrain et les taux de précision restent à établir avec
le dessinateur. Les documents, rapports détaillés et captures restent hors GitHub.

## Installation

Déployer la version 0.3.5 sur OVH avec la [procédure existante](DEPLOIEMENT_OVH.md).
Le moteur Python et `redessin/editor.js` doivent être installés ensemble. Vérifier
la version de `/health`, ouvrir un projet de recette puis tester les choix décrits
plus haut. Les anciens projets sont compatibles ; les contrôles se recalculent à
l’ouverture. Ne pas modifier leur géométrie par un traitement global.

Conserver le menu, l’iframe et l’absence de bandeaux conformément à
[l’avertissement de production](../../AVERTISSEMENT-MODIFICATIONS-STUDIO.md).
Le worker RunPod 0.3.4 déjà installé peut être conservé pour cette mise à jour OVH.
Pour une première connexion des trois moteurs, suivre la
[procédure complète OVH–RunPod](../../INSTALLATION-CONNEXION-IA.md). Aucun déploiement
sur les serveurs réels ni aucune inférence GPU n’a été réalisé depuis cette session.
