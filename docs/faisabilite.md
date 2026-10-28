# Audit préparatoire — DOEMO Studio

Mise à jour : le moteur unifié 1.0.13 a depuis été reçu et lu intégralement.
Un module Python de diagnostic et 67 tests ont été ajoutés. Voir le
[rapport actuel](audit-moteur-1.0.13.md). Les mentions d'attente des scripts et
d'absence de moteur ci-dessous décrivent l'étape initiale de cet audit.

## Statut et périmètre

**Faisabilité métier non démontrée.** Le BAT PDF et AI a désormais été reçu et inspecté ; voir le [rapport du BAT réel](audit-bat-CO26100364-1.md). Deux trames PDF ont ensuite été fournies séparément et inspectées ; voir le [rapport des trames](audit-trames-A3-V.md). L'archive complète dépasse la limite de transfert de l'outil. Les scripts restent absents : leur analyse est requise avant de développer le moteur et de réaliser la première composition métier.

Le cahier fourni s'interrompt sur « Si les fichiers PDF ». Sa copie est conservée telle quelle dans `cahier-des-charges.md` ; aucune suite n'a été inventée.

Ce document prépare l'audit. Il ne constitue ni un rapport de conformité ni une preuve de fidélité graphique.

## Pièces attendues

| Pièce | Utilisation | État |
| --- | --- | --- |
| `Generer-plans-complets.jsx` | Règles de composition, sélection des trames et niveaux | Non reçu |
| `Generer-plans-VEI.jsx` | Identification, associations et rotations des VEI | Non reçu |
| `Generer-legende.jsx` | Compréhension des conventions ; aucune reconstruction de légende autorisée | Non reçu |
| `CO26100364-1.ai` et son PDF vectoriel | Compatibilité PDF, structure, objets, orientations et conservation du dessin | Reçus et inspectés ; PDF intégré lisible |
| ZIP complet `trames/`, avec son arborescence | Catalogue, clients, versions et formats | `trames 2.zip` joint, transfert refusé car supérieur à 32 Mio |
| `ERP - A3H.ait`, `ERP - A3V.ait` et exports PDF vectoriels | Première composition sur une vraie trame | `PI-A3-V.pdf` et `PE-A3-V.pdf` reçus séparément et inspectés ; autres formats non examinés |
| Définition de `ZONE_PLAN` pour la trame du premier essai | Centrage et contrôle des zones protégées | Rectangles candidats relevés sur les deux PDF ; usage et marges à confirmer avec les scripts |

Un fichier AI n'est exploitable que si sa représentation PDF est réellement lisible. L'extension ne suffit pas. Si cette représentation manque, demander un export PDF vectoriel ; ne pas simuler de conversion. Les AIT nécessitent un PDF de référence exporté lors de la configuration initiale.

## Composants candidats

Métadonnées consultées auprès des registres officiels le 28 octobre 2026. Ce sont des candidats à évaluer sur les documents réels, pas des dépendances déjà installées ou une sélection définitive.

| Composant | Version observée | Licence déclarée | Usage envisagé |
| --- | --- | --- | --- |
| pikepdf | 10.17.0 | MPL-2.0 | Inspection des objets et ressources PDF, traitement des flux, composition vectorielle avec qpdf |
| pypdf | 6.21.3 | BSD-3-Clause | Extraction textuelle et comparaison des possibilités de transformation/composition |
| PDF.js / pdfjs-dist | 6.4.299 | Apache-2.0 | Prévisualisation navigateur ; ne remplace pas le moteur de production vectoriel |

Sources : <https://pypi.org/pypi/pikepdf/json>, <https://pypi.org/pypi/pypdf/json>, <https://registry.npmjs.org/pdfjs-dist/latest>.

Python 3.12 et Node.js 24 disponibles dans l'environnement satisfont les prérequis déclarés de ces versions. La compatibilité fonctionnelle reste à tester. Examiner les notices des distributions et dépendances transitives, dont qpdf, avant de figer les versions et le déploiement. Conserver les obligations de redistribution et celles applicables aux modifications de composants MPL.

Architecture pressentie : frontend React/TypeScript, API Python, moteur PDF dans un worker séparé, file de travaux persistante, base de données et stockage privé. Le choix définitif des services et de leurs limites suivra l'examen des fichiers et les mesures de traitement. Aucun service externe ni identifiant n'est requis pour cette préparation documentaire.

## Ordre des travaux

1. Lire intégralement les trois scripts et tracer leurs règles vers les fonctions du futur moteur. Recenser les hypothèses dépendant des objets natifs Illustrator.
2. Calculer les empreintes des fichiers reçus. Examiner des copies avec des limites de taille, de temps et de mémoire. Ne pas exécuter les scripts JSX.
3. Inventorier les pages, boîtes, unités, rotations existantes, polices, images, tracés, transparences, masques, calques éventuels et Form XObjects.
4. Distinguer contenu vectoriel, raster et mixte. La présence de quelques tracés ne prouve pas que le dessin architectural est vectoriel.
5. Identifier un VEI réel, automatiquement si justifiable, sinon par déclaration manuelle. Distinguer position, direction, type PE/PI et orientation H/V. Aucune flèche anonyme ne suffit à identifier un VEI.
6. Définir explicitement le dessin concerné et `ZONE_PLAN` sur une trame réelle. Ne pas déduire arbitrairement les niveaux ou recadrer des éléments architecturaux.
7. Produire une composition vectorielle par transformation globale, puis vérifier le résultat. Si plusieurs VEI ne peuvent pas être isolés, le PDF d'essai doit rester un diagnostic non conforme ; ne pas le présenter comme une déclinaison de production.
8. Évaluer séparément la contre-rotation et l'exclusion des autres VEI. Ne commencer l'interface complète qu'après la preuve technique exigée.

## Géométrie et fidélité à démontrer

Normaliser explicitement les coordonnées PDF, les coordonnées du navigateur, les boîtes de page et la rotation de page existante. Conserver la transformation de passage entre ces systèmes dans le rapport.

Dans un repère cartésien où Y croît vers le haut, un vecteur non nul `v = (dx, dy)` est orienté vers le haut par `theta = pi/2 - atan2(dy, dx)`. Vérifier ensuite que la composante X du vecteur transformé est proche de zéro et que sa composante Y est positive. Ne pas réutiliser cette formule directement sur des coordonnées écran où Y croît vers le bas.

Pour une rotation R et une échelle positive s, la transformation globale est `p' = s R p + t`. Les quatre coins des limites explicites du dessin permettent de calculer les limites après rotation. Pour une zone utile de largeur W et hauteur H, après retrait des marges, et des limites tournées de largeur w et hauteur h :

- Ajustement maximal : `s = min(W/w, H/h)`.
- Réduction seule : `s = min(1, W/w, H/h)`.
- Translation : faire coïncider les centres du dessin transformé et de la zone utile.

Ces limites doivent inclure les contours et les extensions des objets contre-pivotés ; les seules extrémités des tracés ne suffisent pas. Les formes après contre-rotation nécessitent un nouveau contrôle des débordements. Rejeter les dimensions nulles, vecteurs nuls, coordonnées non finies et zones invalides.

La composition doit conserver les ressources graphiques et les systèmes de couleur nécessaires. Une transformation uniforme conserve mathématiquement les proportions, mais ne prouve pas à elle seule la fidélité des transparences, du rendu ou de la gestion des couleurs.

## Séparabilité : décision par objet

| Élément | Preuve nécessaire avant transformation individuelle | En l'absence de preuve |
| --- | --- | --- |
| Texte | Objet isolable, police, matrice, état graphique et ancrage conservables | Signaler le blocage ; aucune reconstruction OCR |
| Pictogramme non directionnel | Identité métier, contenu isolable, ancrage et ressources conservables | Bloquer la déclinaison avancée |
| Flèche directionnelle | Classification et appartenance au dessin établies | Ne pas contre-pivoter arbitrairement |
| VEI inactif | Objet isolable sans suppression de contenu architectural ou technique | Bloquer l'exclusion ; aucun masque rectangulaire destructeur |

Un Form XObject ou un calque n'est pas automatiquement un symbole métier. Les objets peuvent partager des ressources, des clips, des masques et des états graphiques. La modification d'une ressource partagée ne doit jamais affecter d'autres occurrences.

## Contrat d'export structuré à préciser après audit

Si le BAT ordinaire ne suffit pas, envisager un paquet contenant :

- Un fond PDF vectoriel dont sont absents uniquement les objets explicitement séparés.
- Les objets vectoriels séparés, incluant les VEI et les éléments nécessitant une contre-rotation.
- Un manifeste versionné décrivant identifiants, pages, rôles métier, ressources, empreintes, matrices, ancrages, ordre de composition et comportement de rotation.
- Pour chaque VEI : position, vecteur de direction, type, format et rattachement explicite au dessin concerné.
- Les conventions de coordonnées, unités, boîtes de page et limites de dessin.

L'export doit permettre de reconstituer le BAT original sans rotation et de comparer ce résultat à sa référence avant toute génération. Si l'ordre de composition, les masques, les transparences ou les mélanges interdisent une séparation fidèle, signaler cette incompatibilité. Ce contrat reste à confronter aux scripts et aux fichiers ; il n'est pas encore implémenté.

## Critères de la première démonstration

| Contrôle | Preuve attendue | Résultat actuel |
| --- | --- | --- |
| Lecture AI/PDF | Ouverture de la représentation PDF réelle et inventaire des pages | Réussi pour les deux fichiers ; une page A3 portrait |
| Identification du VEI | Repère réel identifié ou déclaré, vecteur vérifié | Trois repères observés ; association complète et direction à valider |
| Rotation | Vérification numérique de la direction finale et inspection visuelle | Non exécuté |
| Trame et mise en page | Bonne trame, page aux bonnes dimensions, marges et zone respectées | Non exécuté |
| Conservation vectorielle | Inspection des flux et ressources avant/après, absence de rasterisation nouvelle | Non exécuté |
| Conservation du contenu | Traçabilité des objets, contrôle inverse applicable et comparaison visuelle | Non exécuté |
| Intégrité des sources | Empreintes identiques avant/après | Vérifié après inspection ; génération non réalisée |
| Séparabilité | Diagnostic explicite des textes, symboles, flèches et VEI | Inspection partielle réalisée ; suppression et contre-rotation non démontrées |
| Validation métier | Examen du PDF réel par DOEMO | Non exécuté |

L'intégrité syntaxique d'un PDF, une empreinte source inchangée ou un test géométrique réussi ne prouvent pas, séparément, la conformité de son contenu. Le rapport devra distinguer les contrôles automatiques, les validations visuelles, les échecs et les contrôles non réalisés. Tout contrôle critique non résolu interdit de déclarer le résultat prêt pour la production.

## Suite bloquée par les pièces métier

Aucun moteur n'a été développé et aucun PDF de production n'a été généré. Le BAT et deux trames PDF vectorielles sont accessibles. La prochaine étape est la réception des scripts pour poursuivre l'audit obligatoire et confirmer les règles de composition. Aucune modification DNS, aucun déploiement et aucune intervention sur l'application DOEMO existante n'ont été effectués.
