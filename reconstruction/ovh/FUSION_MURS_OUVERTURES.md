# Un axe médian avec ouvertures — livraison 0.3.6

La commande **Même mur → axe médian** accepte désormais les bords portant des
ouvertures. Elle conserve les passages déjà renseignés lors de la correction
vers **un seul trait noir plein sur l’axe médian**. Cette opération reste un choix
explicite du dessinateur : la reconnaissance automatique des ouvertures et le
modèle sémantique spécialisé restent à qualifier.

## Utilisation dans Studio

1. Contrôler les deux bords du même mur sur le plan original, dans **Doubles axes
   possibles** ou avec la sélection habituelle **Deux bords → un axe médian**.
2. Lancer la correction. Le recouvrement devient un axe unique. Les portions qui
   dépassent restent des objets indépendants, avec leurs propres ouvertures.
3. Sélectionner chaque objet résultant. Dans **Ouvertures du mur**, examiner la
   position et le type de chaque ouverture. Utiliser **Corriger** pour les ajuster,
   ou **Valider l’ouverture** si les valeurs sont confirmées par le plan.
4. Valider ensuite le mur. Une ouverture transférée encore en attente empêche
   cette validation. Les murs et ouvertures résultants ne sont jamais approuvés
   automatiquement, même si les objets sources étaient déjà approuvés.
5. **Enregistrer sur OVH**, recharger pour contrôler la persistance, puis exporter.
   Annuler/refaire reste disponible avant la sauvegarde.

Si les deux sources associent des types différents à un même passage, le nouveau
type est **passage provisoire**, en attente de contrôle. L’éditeur signale ce
désaccord ; les indications originales « porte » ou « fenêtre » restent dans la
provenance. Corriger le type ou confirmer explicitement ce passage après examen.

## Conservation géométrique

Chaque ouverture est projetée dans le sens de l’axe résultant, puis limitée à la
portion commune. Un bord orienté dans l’autre sens est traité avec la même règle.
Les intervalles d’ouverture se recouvrant ou se touchant sont réunis. Les portions
pleines séparant deux ouvertures distinctes restent présentes.

Une ouverture indiquée sur un seul bord suffit à réserver le passage. Des positions
discordantes conservent l’union des exclusions observées ; ce choix peut donner
une ouverture plus large que l’une des deux indications, à corriger par le
dessinateur. Aucune largeur de porte standard et aucune échelle métrique ne sont
inventées. Le motif et les intervalles de chaque source restent consultables dans
les données du projet et le journal.

Une ouverture traversant la limite du recouvrement est répartie entre l’axe médian
et la portion restante, sans perdre de passage. Exemple en unités du document :
un bord va de 0 à 100, l’autre de 30 à 70, avec une ouverture de 20 à 40 sur le
premier. L’axe médian conserve l’ouverture de 30 à 40 ; la portion restante de
0 à 30 conserve celle de 20 à 30. Ces deux réservations restent à valider.

Si les ouvertures couvrent tout le recouvrement, la commande est refusée : il
n’existe aucune portion pleine commune à redessiner. Les sources restent intactes.
Les refus précédents pour traces non parallèles, trop éloignées, sans recouvrement
ou exactement superposées restent applicables.

## Exports et contrôle

Le SVG et le contrat Illustrator contiennent des segments noirs sur le même axe,
séparés par les ouvertures ; aucune paire de contours n’est générée. Un mur avec
une porte peut donc produire deux segments colinéaires dans son groupe éditable.
Le contrôle des doubles axes de la version 0.3.5 reste actif. Les données
d’apprentissage ne sont exportées qu’après validation du mur et des ouvertures.

144 tests Python passent. Les cas couvrent les bords inversés, ouvertures communes,
types discordants, parties restantes, diagonales, validation et sauvegarde OVH.
Les calculs Python/JavaScript sont comparés sur 40 configurations synthétiques.
Le parcours Chromium rejoue la correction, le contrôle des ouvertures, les exports,
annuler/refaire et le rechargement JSON. Le test est livré dans
`tests/browser/median-openings.cjs` ; voir les prérequis dans le [README](../README.md).
Ces tests ne constituent ni une inférence RunPod ni une recette Adobe.

## Installation

Déployer **0.3.6 sur OVH**, service Python et `redessin/editor.js` ensemble, selon
la [procédure d’installation](../../INSTALLATION-CONNEXION-IA.md). Un worker RunPod
0.3.4 déjà installé peut être conservé. Vérifier `/health`, puis faire l’essai dans
un projet de recette avec une ouverture connue. Les anciens projets sont relus
sans correction automatique de leurs murs.

Conserver le menu, l’iframe et l’absence de bandeaux conformément à
[l’avertissement de production](../../AVERTISSEMENT-MODIFICATIONS-STUDIO.md).
Aucun déploiement sur les serveurs réels n’a été effectué depuis cette session.
