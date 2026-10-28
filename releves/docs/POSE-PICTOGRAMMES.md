# Reconnaissance → pictogrammes SAI → Illustrator

Le parcours du relevé intelligent est raccordé : analyse multimodale des équipements
et des positions, association SAI, aperçu des pictogrammes sur le relevé, contrôle
humain et export du paquet Illustrator. Cette livraison est du développement local,
sans intervention sur OVH ou RunPod. La session de déploiement publie le code.

## Utilisation après déploiement

1. Ouvrir le projet et choisir sa bibliothèque SAI dans **Propriétés**, sans
   annotation sélectionnée. La bibliothèque doit inclure les vecteurs vérifiés et
   les symboles approuvés. Un inventaire JSON seul n’apporte pas les dessins.
2. Vérifier dans **Référentiel** les associations PCF, EXT_PORTATIF et VEI.
   Le VEI doit être la vraie ressource fournie par DOEMO. S’il manque, l’associer
   après import/approbation dans **Illustrator & SAI** ; aucun symbole n’est inventé.
3. Dans **Analyses IA**, choisir **Équipements et positions · IA multimodale**, puis
   **Analyser avec l’IA**. La confirmation indique l’envoi au fournisseur configuré
   et son coût éventuel. Attendre le résultat puis cliquer **Ajouter à la revue** :
   les observations sont intégrées et les correspondances préparées sur leur page.
4. Pour des annotations déjà présentes, cliquer **Préparer les pictogrammes**.
   Cette opération peut être répétée ; elle ne relance pas l’IA. Les éléments déjà
   validés ou rejetés restent inchangés. Les corrections manuelles ne sont pas
   remplacées par une ressource choisie automatiquement.
5. Les véritables aperçus SAI apparaissent au point d’implantation. Un cadre en
   pointillés indique un candidat à vérifier. Déplacer le symbole ajuste le point
   de l’équipement, sans déplacer le cadre du texte d’origine. Les choix **Annotations**,
   **Positions et liaisons** et **Pictogrammes SAI** permettent de simplifier la vue.
6. Ouvrir les éléments listés dans **Placements à compléter**. Une position inconnue
   reste vide : utiliser **Pointer sur le plan**. Vérifier la catégorie, le symbole,
   le niveau, l’orientation, la taille, la correspondance métier/SAI et les six
   critères du placement. Rejeter les textes, légendes et propositions non pertinents.
7. Dans **Illustrator & SAI**, importer le BAT `.ai` avec compatibilité PDF et
   confirmer l’association des niveaux aux plans de travail. Recaler chaque niveau
   au moyen des points correspondants et des points de contrôle indépendants ;
   confirmer le recalage et l’état architectural. Le projet courant est conservé
   lors du passage depuis le relevé intelligent et au retour.
8. Cliquer **Exporter pour Illustrator**. Le contrôle refuse les placements
   incomplets ou non vérifiés. Le ZIP contient `placements.json`, les fichiers AI
   SAI utilisés sous `library/`, `DOEMO-Pose-Pictogrammes.jsx` et `doemo-core.js`.
9. Décompresser le ZIP. Dans Illustrator 2024 ou plus récent, **fermer le BAT et
   les ressources SAI ouverts** avant de lancer le script : il les ouvre lui-même.
   Choisir **Fichier → Scripts → Autre script**, puis `DOEMO-Pose-Pictogrammes.jsx`.
   Sélectionner `placements.json`, le BAT original correspondant, le dossier
   `library` et un **nouveau nom de sortie**. Conserver `doemo-core.js` à côté du JSX.
   Contrôler visuellement la nouvelle copie AI et son rapport avant livraison.

La taille affichée sur le relevé est indicative (le scan peut avoir une autre
échelle). L’export utilise le recalage vers le BAT, les dimensions en points,
la taille en millimètres et la rotation. Il conserve le vecteur original ; le
navigateur ne fabrique pas un fichier AI en renommant un PDF ou une image.

## Règles de reconnaissance et d’association

- `H₂O`, `CO₂`, `EXT`, `EP6` et les variantes reconnues d’extincteurs utilisent
  **EXT_PORTATIF**, sans distinction d’agent. Deux positions distinctes restent
  deux placements.
- **PCF** reste une porte coupe-feu ; une ressource explicitement nommée extincteur
  ne lui est pas attribuée automatiquement.
- **PE / Vous êtes ici** utilisent **VEI**, selon la convention demandée pour DOEMO.
  **PI** reste distinct. Le texte original reste conservé.
- Les correspondances de projet confirmées et le référentiel actif fournissent
  les associations. À défaut, seul un nom de ressource reconnu exactement et
  unique, vérifié et approuvé peut être proposé. Les conflits restent à résoudre.
- Un score OCR, une couleur ou une classe COCO ne prouvent pas la position réelle.
  L’analyse multimodale propose un point direct, une pointe de flèche ou de rappel ;
  un point ambigu reste vide. Le centre d’un texte n’est pas une implantation.
- L’affectation de niveau utilise les découpes du relevé uniquement quand une
  seule zone contient le point. Des zones qui se chevauchent exigent un choix humain.
- Aucune correspondance, orientation ou proposition IA ne vaut validation humaine.
  Les éléments confirmés ne sont pas remis en revue par la préparation automatique.

## Moteur utilisé

Le choix **Équipements et positions** utilise le fournisseur multimodal HTTPS déjà
prévu par `recognition.py` : variables privées `DOEMO_VISION_ENDPOINT`,
`DOEMO_VISION_MODEL`, `DOEMO_VISION_API_KEY`. La clé reste côté backend/worker OVH.
Le service de file d’analyse exécute la tâche ; l’API seule ne suffit pas.

PaddleOCR reste une lecture de texte, Qwen RunPod une analyse textuelle par zones,
et RTMDet COCO un diagnostic générique. Leurs résultats peuvent enrichir la revue,
mais cette livraison ne transforme pas un RTMDet COCO en détecteur incendie entraîné.
Le moteur multimodal ne dépend pas du démarrage de RunPod et n’en provoque pas un.
La préparation, l’aperçu SAI et l’export fonctionnent sans GPU.

## Passation à la session de déploiement

Branche `codex/ai-training-backend`, dépôt `julien547/studio`. Examiner et reprendre
ensemble les fichiers suivants, en conservant les chemins et services existants :

| Fichier | Rôle |
| --- | --- |
| `releves/backend/doemo_releves/placement.py` | Règles métier, associations, affectation de niveau et bilan |
| `releves/backend/doemo_releves/studio_api.py` | Capacités privées et préparation avec contrôle de révision/propriétaire |
| `releves/backend/doemo_releves/queue.py` | Tâche multimodale dans la file OVH, distincte des tâches RunPod |
| `releves/backend/doemo_releves/recognition.py` | Reconnaissance des équipements et positions, conventions DOEMO |
| `releves/web/src/studio.tsx`, `PlanCanvas.tsx`, `main.tsx` | Parcours, aperçus déplaçables et liaison avec l’espace Illustrator |
| `releves/backend/doemo_releves/exchange.py`, `api.py` | Export existant avec vérification des placements et des vecteurs |
| `releves/illustrator/DOEMO-Pose-Pictogrammes.jsx`, `doemo-core.js` | Connecteur Illustrator existant inclus dans le ZIP |

Construire `releves/web` avec `npm ci && npm run build`, puis livrer le backend et
`releves/dist` de la même révision. Adapter les éventuels chemins publics `/app` à
l’intégration déjà en production : ils ne sont pas remplacés par cette livraison.
Cette modification n’ajoute aucune migration SQL et ne modifie pas le gateway GPU.
Elle ne nécessite pas de modifier les profils d’entraînement RunPod existants.

La session de déploiement vérifie que le service API **et le worker d’analyse**
reçoivent la configuration multimodale privée. L’API
`GET /projects/placement-capabilities` renseigne uniquement sa présence, pas une
preuve d’inférence réussie. Préserver les secrets, ne pas les copier dans le build,
GitHub ou le navigateur. Faire une recette autorisée sur un relevé représentatif
et vérifier les vrais symboles SAI, les deux niveaux, le recalage et le fichier AI.

## Validation locale et limites

- 143 tests backend : préparation, distinctions PCF/extincteur/VEI, deux extincteurs,
  conservation des corrections, positions inconnues, conflits, propriété, répétition
  sans duplication, refus d’export prématuré et ZIP avec les octets vectoriels attendus.
- 9 parcours navigateur, dont intégration d’un résultat de fixture, aperçu SAI,
  déplacement d’un symbole indépendamment du texte, persistance, export ZIP et
  passage à l’espace Illustrator avec conservation du projet.
- Build TypeScript et 6 tests du cœur JavaScript Illustrator validés. Les tests
  utilisent des données synthétiques et aucune
  inférence réelle ; ils ne prouvent pas la précision du fournisseur sur vos relevés.
- Le script Illustrator est réutilisé ; ses tests JavaScript ne remplacent pas
  son exécution dans le DOM Adobe. La recette native sur le poste dessinateur reste
  nécessaire. Aucun déploiement ou calcul GPU de production effectué ici.
