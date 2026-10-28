# Contrat de revue et de placement v1

`doemo.review/1` conserve les annotations proposées et rejetées, les extraits référencés,
les pages, les légendes, les niveaux, les points et matrices de recalage, les
correspondances et six validations indépendantes. La sauvegarde SQLite utilise une
révision optimiste ; un changement concurrent retourne HTTP 409. Les imports de
revue vérifient le projet et les empreintes des documents.

Les coordonnées source sont normalisées entre 0 et 1 dans **l’image rendue de la page**,
origine en haut à gauche, X vers la droite et Y vers le bas. L’extraction EXIF fait
partie de ce repère documenté. Les rotation/zoom de lecture de l’interface ne changent
pas ces données ; les clics utilisent la matrice inverse de l’affichage SVG.

Le recalage est une matrice homogène 3×3 de ce repère source vers le même repère normalisé
de la page d’aperçu BAT. Pour une position `[x,y,1]`, appliquer la matrice et diviser par
la troisième composante. Les matrices et erreurs envoyées par le navigateur ne sont
jamais prises pour preuve : le serveur les recalcule depuis les points de calcul et de
contrôle. Les points colinéaires, les matrices dégénérées et les erreurs excessives
bloquent l’acceptation. Un recalage ne prouve pas que les états architecturaux concordent.

`doemo.placements/1` contient exclusivement les placements confirmés. Il inclut les
empreintes SHA-256 du BAT et des AI SAI, les UUID, la version et l’empreinte du
dictionnaire, les sources/pages/annotations, le niveau/plan de travail, les coordonnées,
la matrice source et la correction manuelle éventuelle. Une bibliothèque provisoire,
une ressource non approuvée, un équipement non associé, un niveau ou un recalage non
acceptés bloquent l’export. Aucun point inconnu n’est remplacé par le centre d’un mot.

Le repère exporté est en **points Illustrator (72 pt = 25,4 mm)**, relatif au coin
supérieur gauche du plan de travail, Y descendant. Le JSX utilise le repère document :

```text
x_document = artboardRect[0] + x
y_document = artboardRect[1] - y
```

La taille est le plus grand côté visible, avant rotation, en millimètres ; la mise à
l’échelle conserve le rapport des dimensions. La rotation exportée est horaire et
devient `-rotation_deg` pour l’appel Illustrator. L’aperçu PDF doit avoir les dimensions
du plan de travail natif à 0,1 pt près, sinon le JSX refuse le traitement.

Les métadonnées des groupes natifs contiennent `project_id`, `placement_id`, la source,
l’UUID SAI, la signature du placement et une empreinte de l’objet placé. Le JSX compare
les placements existants, détecte les corrections manuelles et ne supprime pas les
objets retirés du relevé. La reprise d’une sortie AI utilise ses métadonnées d’origine
et une empreinte architecturale, pas une assimilation aveugle de toute copie au BAT.

L’empreinte architecturale vérifie les bornes et la géométrie des tracés et groupes,
les principaux paramètres de couleur, les textes et leurs matrices, et les références
des SymbolItems. Elle ne certifie pas chaque propriété du DOM Adobe, les définitions
internes de tous les effets ou l’apparence des polices. La comparaison avant/après et
après réouverture sert à détecter les modifications indésirables du script ; une revue
visuelle et les tests Adobe réels restent obligatoires avant toute validation de production.

`doemo.placement-report/1` distingue `native_ai_verified` (réouverture et identités),
`architecture_unchanged` (propriétés contrôlées), les mesures de position et
`conformity_passed` (concordance des placements validés). Les données originales de
reconnaissance y restent séparées des quantités effectivement placées.
