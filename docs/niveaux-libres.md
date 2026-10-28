# Niveaux : contours libres et découpage vectoriel

L'éditeur de `/app/orientation` est une **option désactivée par défaut**, activée
par « Délimiter les niveaux (facultatif) ». Sans cette option, le dessin complet
est utilisé ; les sélections sauvegardées ne sont pas appliquées automatiquement.
L'éditeur propose rectangle, polygone libre, lasso et
Bézier, ainsi que déplacement des sommets/poignées, ajout et suppression de
sommets, zoom, déplacement de la vue, annulation et rétablissement. L'ajout
d'un sommet sur une courbe utilise une subdivision de Bézier, sans remplacer
la courbe par des segments droits. Le tracé au stylet utilise les événements
Pointer ; les coordonnées décimales sont conservées.

Un niveau possède un ID, un nom, une page PDF source, une couleur, plusieurs
contours fermés et les identifiants de ses VEI. Les contours d'inclusion sont
réunis par union, puis les exclusions sont soustraites. Le chevauchement de
deux zones incluses ne crée donc pas de trou. Les exclusions traversant ce
chevauchement restent des vides. Chaque contour reste éditable séparément.
Les autres niveaux de la même page restent visibles avec leur couleur.

## Coordonnées et stockage

Le JSON versionné contient `source`, `levels`, `markers`, `revision` et
`review_acknowledged`. `source` associe l'empreinte SHA-256 du BAT aux MediaBox,
CropBox, rotations et unités de toutes ses pages. Les sommets et leurs poignées
`in`/`out` sont exprimés dans le repère PDF, indépendamment du zoom de l'écran.
PDF.js réalise la conversion inverse du pointeur, y compris pour une page tournée.

Le JSON conserve les coordonnées originales ; l'union/différence n'écrase pas
les contours éditables. Les opérations booléennes de découpage utilisent
skia-pathops 0.9.2 avec sa précision numérique native ; elles conservent les
courbes, sans approximation rectangulaire ou raster. La boîte englobante ne
remplace jamais le chemin de sélection.

Les sauvegardes sont privées :
`/var/lib/doemo-studio/private/jobs/<job>/levels.json`, à côté du BAT. Un projet
avec ce fichier est exclu de la purge automatique des travaux de 14 jours.
Il reste disponible dans « Reprendre un projet enregistré ». La sauvegarde est
atomique, avec verrou et révision pour refuser l'écrasement par un onglet ancien.
Un dessinateur ne voit que ses projets ; les administrateurs peuvent les reprendre.
L'export/import JSON permet de transporter les sélections.

Un autre BAT, une autre page ou un autre repère est refusé à la réimportation.
Même avec des dimensions identiques, un SHA-256 différent n'est pas réutilisé
automatiquement. Un import accepté doit être contrôlé puis enregistré.

## Découpage PDF disponible

```sh
doemo-pdf levels-init BAT.ai
doemo-pdf levels-validate BAT.ai niveaux.json
doemo-pdf levels-preview BAT.ai niveaux.json niveau-PE.pdf --mode PE --level IDENTIFIANT
doemo-pdf levels-preview BAT.ai niveaux.json complet-PI.pdf --mode PI --level IDENTIFIANT
```

PE : découpe uniquement les contours du niveau choisi sur sa page source.
PI : conserve toutes les pages originales, dans leur ordre et à leurs positions
d'origine, sans appliquer le contour d'un niveau et sans réorganiser les étages.
Pour un BAT multipage, l'aperçu PI reste multipage : aucune juxtaposition d'étages
sur une seule feuille n'est inventée.

Le moteur place les flux et ressources source inchangés dans un Form XObject et
ajoute seulement le chemin vectoriel de découpage. Il contrôle les empreintes
des flux/ressources après réouverture et l'absence de modification du BAT.
Les calques optionnels et profils OutputIntents sont conservés. Les annotations
et unités personnalisées ne sont pas prises en charge par cet aperçu et sont
refusées explicitement. Le canvas du navigateur sert à l'affichage ; il n'est
jamais utilisé pour construire le PDF exporté.

**Il s'agit d'aperçus du découpage**, avant sélection du VEI actif, rotation,
contre-rotations et composition dans une trame. Ils portent
`status: clipping_preview`, `production_ready: false`. Ils ne remplacent pas
la [génération Linux du lot](generation-linux.md), désormais disponible pour le
profil AI24 à une page. Cette génération utilise les contours PE seulement si
l’option est explicitement activée ; le PI conserve la composition complète.

## Contrôle des limites

L'interface affiche l'avertissement avant le contrôle visuel : les murs, textes,
portes ou pictogrammes traversant le contour peuvent être coupés. Le moteur
ne prétend pas conserver un objet entier situé de part et d'autre d'une limite.
Une case enregistre le contrôle de l'utilisateur ; toute modification d'un
contour ou d'une association l'invalide. Enregistrer un brouillon reste possible.

Les VEI peuvent être associés/réassociés à un niveau et positionnés manuellement
dans l'aperçu. Le rapport distingue position inconnue, intérieure, extérieure et
à moins de 3 points de la limite. Ce contrôle porte sur le point placé par le
dessinateur, pas sur la séparation vérifiée de tous les composants du VEI.

## API et déploiement

Les actions privées `source`, `projects`, `project`, `levels` (GET/POST) et
`clip-preview` sont dans `api/_orientation_levels.php`, inclus après
l'authentification de `api/orientation.php`. Les rôles dessinateur, administration
et admin sont admis ; les accès aux travaux sont contrôlés par propriétaire.

Installer les dépendances mises à jour dans `/opt/doemo-studio/venv-pdf/` :

```sh
/opt/doemo-studio/venv-pdf/bin/python -m pip install -r engine/requirements.lock
/opt/doemo-studio/venv-pdf/bin/python -m pip install --no-deps ./engine
```

Publier **les deux fichiers PHP**, puis reconstruire `doemo-app` sur
`feat/studio-host` avec `npx vite build -c vite.studio.config.js` et publier le
contenu de `dist-studio/` dans `/var/www/studio/app/`. Préserver les projets privés.
Les chemins de production par défaut restent inchangés. Pour un environnement
de test isolé, `DOEMO_PRIVATE_JOBS`, `DOEMO_RESULTS_ROOT`, `DOEMO_PDF_BIN` permettent
de substituer les emplacements du service, jamais par des paramètres HTTP.

## Contrôles effectués

19 nouveaux tests Python couvrent rectangle, L, U, diagonales, courbe cubique,
zones disjointes, chevauchement par union, vide intérieur, règles de remplissage,
VEI proche de limite, BAT multipage, pages tournées, incompatibilité de BAT,
coordonnées invalides, aller-retour JSON et refus d'écrasement.

Un rendu indépendant à 144 dpi vérifie les masques sur des PDF synthétiques :
zéro désaccord sur 784 points par cas rectangle/L/U/diagonale/zones composées,
et 779 points pour la courbe (échantillons hors bord anticrénelé).
Les flux graphiques source restent inchangés et aucune image n'est ajoutée.
Cela ne constitue pas une garantie de fidélité universelle de tout PDF.

Les tests navigateur vérifient le contour en L, l'exclusion, la précision après
zoom, la reprise, les associations VEI, les courbes, l'ajout de sommet,
l'annulation/rétablissement et un lasso sur une autre page. Leurs API sont
simulées ; le déploiement serveur reste à vérifier avec les vrais BAT.
