# Génération Linux 0.3.0 — lots de test

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
  les textes du calque `texte` autour de leurs ancres. Les flèches directionnelles
  suivent le bâtiment ; les panneaux « sortie finale » restent lisibles.
- Utilise les équipements des calques natifs visibles, y compris les neuf
  extincteurs du calque EXT non imprimable du BAT fourni, comme la 1.0.16.
- Place séparément l'adresse, le niveau, la référence/date et le logo client.
  Le masque du logo est conservé ; sa taille est calculée sur la zone visible.
  Le PE réserve l'espace sous Prévention, le PI le bas droit de la page.
- Construit la légende depuis les symboles vectoriels identifiés. Ses libellés
  viennent des noms natifs ; sa présentation diffère de la bibliothèque Illustrator.
- Vérifie après réouverture les flux des fragments source, les ressources
  incorporées, les empreintes des entrées et la direction du VEI.

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
L'éditeur de niveaux et ses aperçus continuent à prendre en charge plusieurs pages.

La zone de trame est actuellement identifiée par un unique grand rectangle blanc
sur le calque Date, présent dans les deux trames fournies. Une trame personnalisée
sans cette convention est refusée. Les trames d'essai contiennent SPECIMEN,
conservé dans les sorties. Les groupes de transparence sont préservés ; des
espaces de fusion incompatibles ou des OutputIntents à harmoniser sont refusés.

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
/opt/doemo-studio/venv-pdf/                   environnement Python 0.3.0
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
choisir `doemo`, charger le BAT fourni, laisser la délimitation décochée, générer
et vérifier trois PDF dans le ZIP. Tester ensuite la délimitation facultative.
Le serveur cible n'est pas accessible depuis cette session : son activation et
ses délais doivent être contrôlés par la session de déploiement.

## Contrôles locaux

- 123 tests Python, 27 scénarios HTTP ciblés et cinq tests navigateur passent.
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
