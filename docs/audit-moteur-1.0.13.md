# Analyse du moteur Illustrator 1.0.13 et premier moteur PDF

## Livraison reçue

Le ZIP `DOEMO-Studio-nouveau-moteur-1.0.13.zip` remplace les trois scripts historiques
attendus pour cet audit, conformément à l'indication de l'utilisateur. Il contient
deux points d'entrée et quatre modules : `core.js`, `illustrator.jsx`, `legend.jsx`
et `panel.jsx`. Ces six fichiers ont été lus intégralement ; les huit empreintes
déclarées dans `SHA256SUMS.json` ont été vérifiées. Les scripts originaux n'ont pas
été modifiés ni exécutés dans Illustrator sur le serveur.

Provenance déclarée par l'archive : `julien547/script-illustrator`, commit
`2597dc0a91fe622b275e5a2f96adc0b55c627edf`. La provenance distante n'a pas été
vérifiée indépendamment ; la correspondance des empreintes de l'archive l'a été.

La documentation annonce 120 tests avec un DOM Illustrator simulé. Les tests ne
sont pas livrés et n'ont pas été relancés ici. Elle signale des pictogrammes
manquants et aucune validation native complète de la version 1.0.13. Le statut
`complete` de ce moteur n'est pas une validation visuelle de production.

## Règles et divergences

| Sujet | Référence 1.0.13 | Décision pour Studio |
| --- | --- | --- |
| Étiquettes | PE/PI, numéros, H/V, ponctuation et format A0–A4 | Réutiliser la convention ; une étiquette seule reste un candidat |
| Direction | Tangente terminale du tracé, avec sens déterminé par la pastille | Conserver cette règle ; ne pas utiliser la ligne pastille→pointe si elle est coudée |
| Association | Rayons de proximité 40/65/140 pt et ambiguïté à 8 pt | Indices à vérifier, pas une preuve de séparation dans le PDF |
| Rotation | `90 - atan2(dy, dx)` dans le repère Y croissant vers le haut | Calcul implémenté et testé |
| Lecture | Contre-rotation des textes et symboles non directionnels autour de leur ancrage transformé | Calcul implémenté ; application individuelle conditionnée à une séparation vérifiée |
| Échelle | Le script maintient séparément certaines épaisseurs de trait | Studio conserve le graphisme sous une transformation uniforme, sans retouche indépendante des contours |
| Centrage | Version 1.0.13 privilégie le centre de page contraint par la zone | Le cahier des charges Studio impose le centre de la zone utile |
| Légende | Masquage de l'ancienne et reconstruction depuis une bibliothèque | Interdit par le cahier des charges Studio ; conserver la légende d'origine |
| Adresse/niveau/cartouche | Placement séparé de blocs | Ne pas transposer automatiquement ; le périmètre du dessin doit être explicite |
| Trames | AI natif ; masquage de certains éléments et zone explicite/nommée/déduite | Utiliser les vrais PDF ; zone explicite à valider ; pas de modification silencieuse |
| Sortie | AI principal, PDF complémentaire | PDF vectoriel uniquement |

## Apport des données natives AI

Le `.ai` possède 15 blocs `AIPrivateData` contenant un flux AI24 Zstandard. Il a
été décompressé et lu sans Illustrator, sans exécution de PostScript. Le flux
décompressé mesure 37 280 183 octets. L'analyse de ce sous-ensemble inventorie :

- 21 définitions de symboles ;
- 18 instances dans `Pictos`, visible dans le PDF ;
- 9 instances `Extincteur Portatif` dans `EXT`, masqué dans le PDF ;
- les noms des symboles et leurs matrices natives de placement.

Les 18 instances visibles comprennent 7 symboles d'évacuation/sortie, 3 pastilles
`Nouveau symbole 11` et 8 autres symboles (sanitaires, porte coupe-feu, local
électrique, déclencheur manuel, ouverture de porte, TGBT et SSI).

L'appartenance à un calque ne prouve pas à elle seule la visibilité de chaque
occurrence native. La visibilité individuelle et les effets hérités devront aussi
être vérifiés. Les neuf extincteurs du calque masqué ne sont pas automatiquement
réactivés : cela modifierait le contenu visible de la source.

Le PDF conserve le calque `Pictos` mais a aplati la plupart de ces instances en
tracés ordinaires. Les pastilles utilisent un Form XObject partagé. Les autres
symboles ne possèdent pas tous un Form XObject identifié. Dans ce calque, 69
paires `q/Q` entièrement contenues ont été observées : ces blocs d'état graphique
ne sont pas 69 pictogrammes. Un même symbole peut avoir plusieurs tracés et un
état graphique peut traverser une limite de calque.

La métadonnée native rend l'association possible à étudier. Elle ne fournit pas
encore une correspondance vérifiée entre chaque instance et la liste complète
de ses opérateurs PDF. Le moteur ne doit pas confondre proximité géométrique et
identité graphique.

## Premier essai réel : portée exacte

Deux compositions de diagnostic ont été exécutées depuis le vrai AI et les
trames PE-A3-V et PI-A3-V, avec marge expérimentale de 12 pt :

| Essai | Rotation | Échelle | Objet de l'essai |
| --- | --- | --- | --- |
| PE | −90° | 63,936586 % | Direction gauche déclarée, page BAT complète |
| PI | 180° | 69,270337 % | Direction bas déclarée, page BAT complète |

Les sorties sont conservées hors du dépôt dans
`/workspace/studio-audit/diagnostic-001/` et portent `DIAGNOSTIC-NON-PRODUCTION`
dans leur nom et un statut `diagnostic_nonconforming` dans leur rapport.

Contrôles réussis : réouverture PDF sans anomalie syntaxique, dimensions de la
trame, direction déclarée tournée vers le haut, échelle uniforme, inclusion de la
page entière dans la zone candidate, flux source et ressources embarquées
inchangés, empreintes des sources inchangées.

Une vérification avec un moteur de rendu distinct de pikepdf (PyMuPDF 1.26.6,
utilisé seulement pour l'audit) a donné à 144 dpi **zéro pixel modifié hors de la
zone d'insertion du BAT** sur les deux trames. Les nombres d'enregistrements de
dessin rendus sont additifs : 342 + 844 = 1186 pour PE et 342 + 62 = 404 pour PI.
Cela atteste le comportement de ce test, pas la préservation de tous les cas PDF.

**La validation métier échoue volontairement à ce stade** : la page source
complète conserve son ancien bandeau, tous ses VEI et ses textes tournés. Les
pictogrammes n'ont pas encore reçu de contre-rotation dans ces sorties. Le test
ne doit donc pas être présenté comme une déclinaison prête à imprimer.

## Validation du code et suite

67 tests automatisés du nouveau module Python ont été exécutés avec succès :
orientations cardinales et obliques, matrices inverses, centrage, proportions,
contre-rotation et conservation de l'ancrage, lecture native bornée, caractères
échappés, conservation des ressources et visibilités PDF, refus des entrées
incompatibles, sélection explicite d'une page et absence d'écrasement.

Ces tests utilisent des documents synthétiques pour les cas unitaires ; ils ne
remplacent pas les contrôles sur le BAT décrits ci-dessus. Les 120 tests annoncés
par l'archive JSX ne sont pas comptabilisés dans ces 67 tests.

Mise à jour de la transmission serveur : huit tests supplémentaires vérifient
la collection `doemo` par défaut, les dossiers clients voisins et le refus des
chemins invalides ou liens symboliques. Le total actuel est de 75 tests réussis.

La production avancée reste bloquée sur la correspondance complète symbole ↔
contenu PDF, sur les textes à contre-pivoter et sur le périmètre du dessin à
composer. Le [contrat d'export structuré](contrat-export-structure.md) décrit une
voie vérifiable pour obtenir ces associations sans Illustrator sur le serveur.
Le serveur ne doit pas faire fonctionner les JSX de génération en arrière-plan.
