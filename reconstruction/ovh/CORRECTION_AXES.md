# Correction des axes — livraison 0.3.2

Cette livraison corrige un défaut géométrique du prototype et ajoute une correction
manuelle pour les doubles traces. Elle ne contient aucun nouveau modèle de
segmentation et n’exécute aucune inférence RunPod.

## Portions manquantes

Auparavant, après avoir apparié deux segments sur une portion commune, l’extracteur
considérait les deux segments entiers comme utilisés. Un long bord ne pouvait plus
être apparié à plusieurs fragments opposés, même si les portions étaient distinctes.

L’extracteur consomme maintenant uniquement l’intervalle utilisé de chaque bord.
Il conserve la portion commune de chaque nouvelle paire, sans prolongement ni
fermeture des coupures. Les endpoints canoniques rendent le résultat indépendant
du sens et de l’ordre des segments. La médiane tient compte des deux extrémités
réellement observées pour les bords légèrement inclinés. La provenance conserve
les bords, leurs intervalles utilisés et les portions appariées.

Exemple : un bord va de 0 à 100, son opposé comporte deux fragments de 0 à 40 et
de 60 à 100. Les deux axes correspondants sont proposés ; l’intervalle 40–60 reste
vide. La largeur reste exprimée en unités du document, sans calibration inventée.

## Correction de deux traces représentant les faces d’un même mur

Dans l’éditeur Studio :

1. Contrôler les deux traces sur le plan original et sélectionner la première.
2. Cliquer **Deux bords → un axe médian**.
3. Cliquer sur la seconde trace du même mur. Échap annule le choix.
4. Contrôler le nouvel axe, ses raccordements et les portions restantes, puis valider.
5. Cliquer **Enregistrer sur OVH**. Annuler/refaire reste disponible avant sauvegarde.

La commande remplace uniquement le recouvrement par une médiane noire. Les parties
qui dépassent restent des traces indépendantes à contrôler. Elle refuse les
traces sans recouvrement, non parallèles (tolérance 1 degré), distantes de plus de
24 unités du document, ou portant une ouverture renseignée. Elle ne supprime pas
ces ouvertures pour permettre la fusion. Tous les objets modifiés repassent en
attente de validation, y compris si les traces originales étaient approuvées.

Cette opération demande une interprétation du dessinateur : ne pas l’utiliser pour
fusionner deux murs voisins distincts ou les deux côtés d’un couloir. Aucune fusion
automatique n’est appliquée aux projets sauvegardés. Pour comparer l’extraction
nouvelle à une ancienne, importer la page dans un nouveau projet.

## Vérification locale

88 tests Python passent, dont les cas de fragments, diagonales, sens inversés,
intervalles non réutilisés, ouvertures protégées et conservation des autres murs.
Un test avec un PDF vectoriel réel généré vérifie la récupération des deux fragments
et des coordonnées. Un parcours Chromium vérifie la correction manuelle, les
extrémités restantes, le refus des ouvertures et annuler/refaire, sans erreur JavaScript.

Sur la **page 1 de `2(2).pdf`**, l’extraction est rejouée à paramètres de rendu et
d’OCR identiques : 913 segments sources ; 327 propositions auparavant, 381 après
correction ; aucun intervalle de bord consommé deux fois ; aucune échelle validée.
Les deux méthodes partagent 272 paires de bords ; 55 anciennes paires ne sont plus
retenues et 109 nouvelles paires apparaissent, du fait de l’allocation des portions
et du calcul des séparations. Le changement n’est donc pas un simple ajout de murs.

La comparaison visuelle confirme que des portions auparavant omises réapparaissent,
mais les cadres, fenêtres et mobiliers produisent encore de faux candidats et
certains murs restent représentés par plusieurs propositions parallèles. **Ces
comptages ne mesurent pas la précision, et la règle d’un axe par mur n’est pas encore
garantie par l’extraction automatique.** La correction manuelle ci-dessus permet
de résoudre les cas identifiés ; le modèle sémantique spécialisé et une annotation
humaine de référence restent nécessaires pour qualifier l’automatisation.

Les projets de comparaison et les images du plan restent hors GitHub. Aucun mur
n’a été approuvé automatiquement et aucun résultat n’a été ajouté à un jeu
d’apprentissage validé.

## Transmission au déploiement

Déployer le dernier commit de `feat/redessin-ovh-tests` en suivant
[DEPLOIEMENT_OVH.md](DEPLOIEMENT_OVH.md), qui conserve les projets et la configuration
de connexion. Le fichier `redessin/editor.js` généré est inclus dans cette livraison.
Vérifier que `/health` indique `0.3.2`, puis tester la commande dans un projet de
recette. Le [raccordement OVH–RunPod](RACCORDEMENT_RUNPOD.md) reste une recette distincte.
