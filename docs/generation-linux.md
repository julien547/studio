# Génération Linux 0.3.5 — lots de test

Le bouton **Générer tous les plans** produit maintenant les PDF puis un ZIP,
sans Illustrator, pour le profil de BAT pris en charge. Il devient disponible
après vérification des identités natives et des trames du dossier client.
Les sorties portent `test_batch_complete`, `production_ready: false` : elles
sont destinées au contrôle visuel demandé, pas à une certification automatique.

## Utilisation

1. Choisir le dossier client (`doemo` ou un dossier voisin).
2. Importer le BAT AI compatible PDF, ou son PDF conservant les données natives
   Illustrator AI24. Attendre l'identification des VEI et pictogrammes.
3. **La délimitation des niveaux est facultative et désactivée par défaut.**
   Sans cette option, tout le dessin du BAT est utilisé, même si des contours
   ont été enregistrés auparavant. Les niveaux ne sont pas réorganisés.
4. Si l'option est activée : dessiner les contours, associer chaque VEI PE à son
   niveau, contrôler les limites et enregistrer. Le PI conserve la composition
   entière. Masquer l'éditeur ne supprime pas les contours en cours de saisie.
5. Générer le lot et télécharger le ZIP ou chaque PDF séparément.

Les repères sont numérotés de haut en bas dans le BAT, puis de gauche à droite.
La trame est sélectionnée automatiquement par PE/PI, format et H/V dans le seul
client choisi. Une trame manquante ou ambiguë bloque le lot complet.

## Ce que réalise le moteur

- Décompose les opérations PDF avec leurs états graphiques, clips, polices,
  images et ressources incorporées ; ne rasterise jamais le dessin.
- Lit les polices TrueType CID `Identity-H` incorporées (tables CIDToGIDMap,
  largeurs W/DW et Unicode), ainsi que les encodages simples WinAnsi, MacRoman
  et StandardEncoding. Les opérateurs de texte et les polices restent ceux du BAT.
  Les couleurs CMJN ICC et les tons directs à fonction de teinte exponentielle
  sont également reconnus pour identifier les flèches ; leurs flux restent intacts.
- Associe les noms natifs aux tracés PDF par comparaison géométrique complète
  des contours échantillonnés dans les deux sens, avec une borne conservatrice
  de correspondance de 0,02 pt. L'échantillonnage sert uniquement à l'association ;
  les PDF générés utilisent les opérateurs vectoriels d'origine, y compris les
  courbes. Une boîte englobante seule ne suffit pas à accepter une association.
- Vérifie les symboles réutilisés contre leur définition native et leur matrice.
  Refuse les associations ambiguës ou incomplètes.
- Identifie chaque pastille, tige, pointe et étiquette VEI ; retire tous les
  composants des autres VEI et les codes PEV/PIV du dessin.
- Oriente la flèche active vers le haut et redresse les symboles de lecture et
  les textes autour de leurs ancres, quel que soit le nom de leur calque visible.
  Les flèches directionnelles
  suivent le bâtiment ; les panneaux « sortie finale » restent lisibles.
- Associe les libellés multilignes aux séquences de glyphes ou au texte Unicode
  des histoires natives Illustrator. Une association unique couvrant tous les
  fragments est requise ; toutes les lignes partagent alors la même ancre.
  Des libellés identiques tels que « BUREAU » peuvent apparaître plusieurs fois,
  chacun conservant son propre emplacement. Les calques `SIG`, `Niveau` ou les
  autres noms ne sont pas refusés uniquement à cause de leur nom.
  Les noms de pièces restent dans le dessin. Les vrais titres de niveaux sont
  extraits et placés sous le niveau concerné en priorité, puis sur le côté si
  l'espace manque. Les regroupements géométriques servent uniquement au placement
  des titres : ils ne déplacent ni ne découpent les bâtiments. Avec une sélection
  PE explicite, seul le titre associé est replacé hors du contour ; les autres
  titres ne laissent pas de lettres tronquées en bordure du plan.
- Utilise les équipements des calques natifs visibles, y compris les neuf
  extincteurs du calque EXT non imprimable du BAT fourni, comme la 1.0.16.
- Place séparément l'adresse, le niveau, la référence/date et le logo client.
  Le masque du logo est conservé ; sa taille est calculée sur la zone visible.
  Le PE réserve l'espace sous Prévention : à gauche en horizontal, à droite en
  vertical. Le PI utilise le bas droit de la page. Le logo reste entièrement
  dans cet espace blanc et ne peut pas recouvrir la légende. Les limites placées
  sont enregistrées dans `layout.logo_bounds` et `layout.level_titles`.
  Un logo isolé en bas du BAT peut aussi se trouver sur le calque Date ; il est
  placé comme logo, séparément du texte de mise à jour.
- Construit la légende depuis les symboles vectoriels identifiés. Ses libellés
  viennent des noms natifs ; sa présentation diffère de la bibliothèque Illustrator.
  Un cadre vectoriel vert entoure la légende des PE, rouge celle des PI.
  Le titre gras et coloré est placé au-dessus du cadre. Les libellés sont en
  capitales grasses ; les colonnes sont dimensionnées selon leur contenu avec
  un intervalle de 12 pt, dans un bloc compact centré sous le dessin.
- Place la ligne « Mise à jour… » tout en bas de la page, sous les consignes,
  avec un espace réservé sous le logo. L'indice de mise à jour du BAT est conservé.
  La date du jour est calculée une seule fois au démarrage du lot, en heure de
  Paris (`DOEMO_TIMEZONE`, facultatif, fuseau IANA ; défaut `Europe/Paris`).
  La référence finale suit le numéro du VEI : `CO26100364-1`, `CO26100364-2`, etc.
  Seul ce texte de publication est réécrit en Helvetica ; les textes du dessin
  architectural gardent leurs glyphes incorporés. Le nom des fichiers conserve
  le nom du BAT et le suffixe `VEI-XX` pour identifier la source et la déclinaison.
- Vérifie après réouverture les flux des fragments source, les ressources
  incorporées, les empreintes des entrées et la direction du VEI. La vérification
  des fragments inchangés exclut le cartouche date/référence volontairement réécrit,
  signalé par `publication_metadata_rewritten` dans chaque résultat.

Le ZIP est proposé uniquement après réussite de tous les PDF. Le manifeste est
publié en dernier. Une erreur ne laisse pas un ZIP partiel téléchargeable ; aucun
lot existant n'est remplacé. Limites : 100 VEI et 256 Mio de PDF par lot.

## Profil actuel et limites

Cette première génération prend en charge **un BAT à une page**, sans rotation
PDF préexistante, avec les conventions de calques et symboles Illustrator AI24
contrôlées. Le BAT `CO26100364-1.ai` et son PDF fourni passent l'identification :
27 symboles, trois VEI, deux PE et un PI. Les PDF sans données natives exploitables,
les BAT multipages, les textes fragmentés/multilignes non associés, certaines
polices/encodages et les opérateurs non pris en charge sont refusés explicitement.
`Identity-V`, les CMap composites personnalisées et les polices CID CFF ne sont
pas encore pris en charge. Un message mentionnant une trame H manquante signifie
qu'il faut installer cette trame horizontale dans la collection choisie ; le
moteur ne la remplace jamais automatiquement par une trame verticale.
L'éditeur de niveaux et ses aperçus continuent à prendre en charge plusieurs pages.

La zone de trame est détectée dans cet ordre :

1. Bornes géométriques d'un repère sur un calque `ZONE`, `ZONE_PLAN`,
   `DOEMO_ZONE`, etc., y compris un tracé non peint.
2. Grand rectangle blanc, quel que soit le nom du calque, avec préférence pour
   le calque Date historique. Le blanc CMJN, RVB, gris et ICC est reconnu.
   Les rectangles superposés identiques et les chemins fermés par retour au
   premier sommet sont acceptés.
3. Plus grande zone libre entre les objets visibles : bandeau, consignes,
   cadres et autres éléments fixes. Les champs d'exemple Adresse/Date/Légende
   sont exclus de l'habillage et le filigrane ne constitue pas un obstacle.
   Les cadres laissent leur intérieur disponible. Deux zones de surface
   équivalente à 5 % près restent ambiguës ; le moteur ne choisit pas au hasard.

Cette détection utilise les objets vectoriels, sans rasterisation. Le dessin
réserve ensuite l'espace de l'adresse et du logo client. `layout.zone_detection`
indique la méthode et les coordonnées détectées ; `layout.zone` donne la zone
après ces réservations. La limite de recherche est de 256 régions, avec une
surface minimale de 20 % de la page pour la détection automatique d'espace libre.
La reconnaissance des noms concerne les calques PDF ; un nom d'objet Illustrator
non exporté dans le PDF n'est pas présenté comme un repère nommé reconnu.

Les erreurs précisent désormais le nom de la trame concernée. Pour contrôler
une trame directement sur le serveur, sans BAT :

```sh
/opt/doemo-studio/venv-pdf/bin/doemo-pdf inspect-template /var/lib/doemo-studio/templates/doemo/PI-A3-H.pdf
```

Les trames d'essai contiennent SPECIMEN,
conservé dans les sorties. Les groupes de transparence sont préservés ; des
espaces de fusion non CMJN incompatibles ou des OutputIntents à harmoniser sont
refusés. Si un BAT utilise un profil ICC CMJN et la trame DeviceCMYK, la trame
est conservée dans un groupe isolé avec son espace de fusion d'origine ; le BAT
garde son profil ICC sur la page.

Le BAT `CO26100010-1.ai` vérifie aussi l'import : 48 symboles, cinq VEI et 17
blocs de texte, dont cinq multilignes. Les trois déclinaisons verticales ont été
générées avec les trames disponibles dans l'environnement de test. Les deux
horizontales demandent `PI-A3-H.pdf` et `PE-A3-H.pdf`, déjà présentes sur le serveur
selon Julien. Le PDF exporté joint à ce BAT ne contient plus les données natives :
utiliser le `.ai` pour la génération. Le message d'import le précise désormais.
La 0.3.4 a aussi été testée sur le lot des cinq VEI, avec les deux vraies trames
verticales et deux trames horizontales synthétiques sans repère blanc : cinq PDF
et ZIP générés. Ce test valide le traitement complet et la détection d'espace
libre, pas le placement dans les trames horizontales privées du serveur.

La 0.3.5 traite `CO26100179-1.ai` : quatre VEI, trois PI et un PE, libellés de
pièces sur Niveau, texte de signature sur SIG et logo sur Date. Le contenu de
signature reste présent ; aucun calque utilisateur n'est supprimé par cette
correction. Les exports PDF Illustrator utilisant les balises `Layer/Title`
et les métadonnées `AltAI8` sont également lus. Les flux alternatifs des calques
masqués ne sont jamais exécutés comme des opérations de dessin.
Les deux titres de niveaux de `CO26100010-1.ai` sont conservés comme fragments
vectoriels et replacés sous leurs niveaux, y compris après rotation. Les trois
sorties portrait ont été contrôlées avec les trames fournies. Le placement du logo
PE horizontal sous la colonne Prévention gauche est testé sur une trame
synthétique ; le rendu avec la trame horizontale réelle du serveur reste à
contrôler après déploiement.

Un contour qui masque la zone occupée par le VEI actif est refusé : la pastille
et sa flèche doivent rester visibles. Élargir explicitement le contour dans ce
cas ; le moteur ne le modifie jamais tout seul.

Un découpage peut masquer partiellement un mur, un texte ou un équipement qui
traverse sa limite. Le moteur ne promet pas de conserver automatiquement l'objet
entier. Contrôler les aperçus avant d'activer la délimitation pour un lot.

Les chemins de dessin, polices et équipements sont conservés, mais la composition
et la légende ne sont pas annoncées identiques à celles d'Illustrator. La
validation visuelle de Julien reste nécessaire. L'ancienne action `compose`
reste bloquée ; `compose-diagnostic` reste un autre outil, non utilisé par ce bouton.

## API et fichiers

- `POST orientation.php?action=plan` : candidats et contrôle natif pour la
  génération ; `batch.generation.generation_available` active le bouton.
- `POST …?action=generate-test-batch` : `{job, collection, use_levels: false}`.
  `true` utilise un instantané des sélections enregistrées et contrôlées.
- `GET …?action=batch-file&job=…&batch=…&file=plans.zip` : archive privée.
  Le même endpoint fournit les noms PDF du manifeste et `rapport.json`.

Les trois routeurs PHP doivent être présents : `orientation.php`,
`_orientation_levels.php`, `_orientation_batch.php`. Les accès sont contrôlés par
session, rôle et propriétaire ; un verrou interdit deux générations simultanées
sur le même BAT. Le délai moteur est de 240 s avec limites CPU/mémoire/fichier.
Ce fonctionnement est synchrone ; il n'y a pas encore de file persistante de workers.

```text
/opt/doemo-studio/src/engine/                 code moteur
/opt/doemo-studio/venv-pdf/                   environnement Python 0.3.5
/var/www/studio/api/                         PHP, dont les deux routeurs internes
/var/www/studio/app/                         build doemo-app, branche feat/studio-host
/var/lib/doemo-studio/templates/doemo/        trames DOEMO
/var/lib/doemo-studio/templates/<client>/     trames personnalisées
/var/lib/doemo-studio/private/jobs/<job>/     BAT, métadonnées et niveaux facultatifs
/var/lib/doemo-studio/results/<job>/lot-<id>/ PDF, rapport.json et plans.zip
```

## Mise à jour pour l'autre session

Depuis les checkouts existants, préserver les modifications locales et utiliser
les commits publiés sur `studio/main` et `doemo-app/feat/studio-host`.

```sh
cd /opt/doemo-studio/src
git pull --ff-only origin main
/opt/doemo-studio/venv-pdf/bin/python -m pip install -r engine/requirements.lock
/opt/doemo-studio/venv-pdf/bin/python -m pip install --no-deps ./engine
/opt/doemo-studio/venv-pdf/bin/python -c "from importlib.metadata import version; print(version('doemo-studio-pdf'))"
/opt/doemo-studio/venv-pdf/bin/doemo-pdf generate-test-batch --help
```

Publier les trois PHP depuis `api/` vers le dossier API du site avec les droits
habituels. Ne pas installer tout le dépôt dans la racine web. Dans le checkout
`doemo-app`, récupérer `feat/studio-host`, puis :

```sh
npm ci --ignore-scripts --no-audit --no-fund
npx vite build -c vite.studio.config.js
```

Publier le contenu de `dist-studio/` dans `/var/www/studio/app/`. Conserver le venv
historique `/opt/doemo-studio/venv/` ; seul **venv-pdf** est concerné. Préserver les
trames clients et projets privés. Adapter si nécessaire le délai PHP/FPM/proxy
à 250 s uniquement pour cette API ; vérifier les permissions d'écriture des
résultats pour le compte PHP. Voir aussi [le guide serveur](deploiement-serveur.md).

Contrôle après déploiement : ouvrir `https://studio.doemo.fr/app/orientation`,
choisir le dossier client approprié, charger le BAT fourni, laisser la
délimitation décochée et générer. Vérifier le nombre de PDF dans le ZIP : trois
pour CO26100364, quatre pour CO26100179, cinq pour CO26100010. Tester ensuite la
délimitation facultative. Pour CO26100010, contrôler spécialement le logo du
PE horizontal sous Prévention à gauche, et les titres sous chaque niveau du PI.
Cette correction 0.3.5 nécessite la réinstallation du moteur Python ; elle
ne nécessite pas de reconstruire un frontend déjà à jour.
Le serveur cible n'est pas accessible depuis cette session : son activation et
ses délais doivent être contrôlés par la session de déploiement.

## Contrôles locaux

- 166 tests Python passent en 0.3.5, dont titres sous les niveaux, repli latéral,
  suppression du titre hors sélection PE, noms de pièces conservés et logo PE
  horizontal sous Prévention à gauche sans recouvrement de la légende.
  Les 27 scénarios HTTP et cinq tests navigateur ont été validés lors de la
  livraison de la génération ; cette correction ne modifie pas ces interfaces.
- Chaîne HTTP réelle avec le BAT fourni : contrôle natif, génération des trois
  PDF par le moteur Python puis téléchargements individuels et ZIP via PHP 8.4
  authentifié en environnement isolé. Empreintes téléchargées identiques,
  environ 17 s pour génération et téléchargements. Ce n'est pas un test du
  serveur public de production.
- Recomposition du BAT fourni sans transformation : rendu strictement identique
  à l'original à 144 dpi dans un moteur indépendant, après conservation du groupe
  de transparence CMYK. Cette comparaison n'est pas une preuve universelle.
- Génération réelle sur Linux des trois plans depuis le BAT, en environ 18 s
  dans cet environnement, avec les trames fournies ; logo PE contrôlé visuellement.
- Vérification des appels de dessin des trois sorties réelles : une pastille
  VEI par PDF, les 129 opérations architecturales du BAT dessinées une seule
  fois et les sept textes du plan redressés.
- Tests Python : associations, refus d'une géométrie modifiée, un seul appel de
  dessin de la pastille par PDF, suppression des codes, orientation, ZIP complet,
  absence de repli entre clients, absence d'écrasement, échec atomique,
  masques d'image et niveaux PE facultatifs sans découper le PI.
- Tests HTTP : droits, origine, verrou de génération, téléchargement ZIP/PDF,
  refus des chemins non autorisés, instantané facultatif et suppression du lot
  incomplet (CLI simulé pour ces cas).
- Tests navigateur : bouton, liens du lot, option désactivée par défaut et reprise
  des contours quand l'éditeur est masqué puis réaffiché (API simulée).
