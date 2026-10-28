# Contrat partagé — services d’apprentissage DOEMO Studio

Version `doemo.training/1`. Cette livraison couvre **la page `/entrainement` et son
backend**, conformément à la correction explicite de l’utilisateur. La session de
déploiement conserve seule la responsabilité des serveurs OVH et RunPod. Le module
réutilise React, l’éditeur SVG et FastAPI/SQLite existants.

Voir [la procédure de livraison de la page](PAGE-ENTRAINEMENT.md) pour les fichiers,
les routes publiques, les tests et les limites des services GPU.

## État exact de cette livraison

| Fonction | État |
| --- | --- |
| Page administrative, quatre espaces moteur / quatre onglets, éditeur partagé | Implémenté ; parcours navigateur testés sur le vrai backend local |
| Exemples par moteur, catégories, corrections, consentement, validation, rejet et historique | Implémenté et testé sur CPU |
| Versions immuables de datasets, groupes bâtiment/document, exports avec vraies images | Implémenté et testé sur CPU |
| Qwen : versions du référentiel et recherche lexicale | Implémenté et testé ; aucun poids modifié |
| Qwen : test du référentiel sur le lot test | Implémenté ; ce n’est pas une évaluation de l’inférence Qwen |
| PaddleOCR : images recadrées/transcriptions, conversion des labels, calcul CER/WER | Implémenté et testé sur fixtures ; aucun fine-tuning effectué |
| RTMDet : préparation COCO, pilote de formation MMDetection 3.3.0, checkpoints vérifiés | Pilote écrit ; tests CPU des données/artefacts ; exécution GPU NON réalisée |
| Registre des versions, états, séparation par moteur | Persistant ; versions de référentiel enregistrables |
| Entraînement asynchrone depuis le navigateur | RTMDet raccordé à la file OVH/gateway ; activation conditionnée à la recette GPU réelle |
| Enregistrement de poids | Candidat RTMDet après tâche terminée et artefacts vérifiés, un par tâche |
| Évaluation comparative réelle, approbation, publication, rollback | Opérations refusées : adaptateurs non raccordés |
| Qwen LoRA/QLoRA et entraînement PaddleOCR | À implémenter après audit des modèles/configurations réellement installés |
| IA architecturale | Contrat géométrique uniquement, aucun réseau installé annoncé |
| Image Docker permanente | Recette fournie ; ni construite ni publiée ni testée sur GPU |

L’API `/capabilities` est la source d’autorité pour activer les boutons. Un pilote
écrit mais non validé sur le GPU ne rend pas `training=true`. Aucune route ne
simule un entraînement terminé, une progression, une approbation ou un déploiement.

## Accès et OpenAPI

[Schéma OpenAPI généré depuis les routes réelles](api/training-openapi.json).
Régénération :

```sh
/chemin/venv/bin/python releves/scripts/export-training-openapi.py \
  releves/docs/api/training-openapi.json
```

Préfixe interne : `/projects/training`. Le choix conserve le relais PHP existant,
qui autorise déjà les routes `/projects/*`. Depuis React, utiliser le helper `api` :

- Studio PHP : `/api/releves.php?route=<chemin encodé>`.
- Mode autonome : `/api/projects/training/...`.

Toutes les routes d’apprentissage demandent `admin` ou `administration` sur OVH.
Ne jamais exposer l’API privée faisant confiance à `X-Doemo-*` en TCP public.
Ces en-têtes viennent uniquement du relais PHP/session ou du middleware autonome.
Le navigateur ne reçoit aucun jeton RunPod. L’OpenAPI lui-même est réservé aux
administrateurs via `/projects/training/openapi`.

| Route sous le préfixe | Méthode | Opération |
| --- | --- | --- |
| `/capabilities` | GET | Capacités réelles par moteur et motif d’indisponibilité |
| `/categories` | GET | Catégories et types géométriques |
| `/categories/{code}` | PUT | Créer, renommer ou désactiver une catégorie |
| `/examples?engine=...` | GET | Filtres `project_id`, `category`, `status`, `since=YYYY-MM-DD` |
| `/examples` | POST | Enregistrer un brouillon à partir d’un document existant |
| `/examples/{id}` | PUT | Sauvegarder une correction avec révision optimiste |
| `/examples/{id}/decision` | POST | Validation ou rejet motivé, audit |
| `/datasets?engine=...` | GET | Liste des versions immuables |
| `/datasets` | POST | Figer des exemples validés du même moteur |
| `/datasets/{id}` | GET | Snapshot, transformations, SHA-256 et avertissements |
| `/datasets/{id}/export` | GET | ZIP COCO/images, OCR ou Qwen et données géométriques |
| `/models?engine=...` | GET | Registre et pointeurs de production indépendants |
| `/models/{engine}/versions` | POST | Version du référentiel Qwen ; poids refusés sans entraînement terminé/intègre |
| `/models/qwen/{id}/reference?q=...` | GET | Rechercher les conventions de cette version exacte |
| `/models/{engine}/{id}/test` | POST | Test du référentiel ; évaluation GPU non raccordée |
| `/models/{engine}/{id}/approve` | POST | Refus si comparaison réelle et artefacts vérifiés absents |
| `/models/{engine}/{id}/publish` | POST | Confirmation et approbation requises ; activation GPU non raccordée |
| `/models/{engine}/{id}/rollback` | POST | Même contrôle d’autorisation ; aucun changement simulé |
| `/runs` | POST | Admission RTMDet confirmée et idempotente après recette ; 503 sans capacité |
| `/runs?engine=...`, `/runs/{id}`, `/runs/{id}/logs` | GET | État enregistré et journal, jamais progression inventée |
| `/runs/{id}/cancel` | POST | Annulation immédiate avant envoi, sinon attente de l’accusé GPU |
| `/runs/{id}/resume` | POST | Reprise explicite d’une interruption depuis checkpoint vérifié |
| `/audit` | GET | 200 dernières actions et décisions |

Erreurs JSON : `{"detail":"motif"}`. 401/session expirée au relais, 403/droits,
404/ressource absente, 409/conflit de révision ou précondition, 422/données invalides,
503/capacité non raccordée. Ne pas interpréter un 503 comme une tâche créée.

## Intégration des exemples et de l’éditeur

L’import PDF/image réutilise `POST /projects/{project_id}/documents` avec `role=survey`.
Les analyses réutilisent la file `/projects/{project_id}/jobs`. Leurs résultats sont
séparés des corrections ; le frontend doit les présenter comme propositions puis
copier explicitement les éléments choisis dans un exemple d’apprentissage.
Le moteur COCO RTMDet de base ne doit pas attribuer des catégories DOEMO par défaut.
Ses boîtes sont exposées dans `result.proposals` avec `source_class`, `score`,
`bbox` normalisée, `document_id`, `page`, `category=null` et `anchor=null`.
Elles ne sont jamais ajoutées aux équipements de production. La page les superpose
en bleu et n’en fait des brouillons qu’après copie explicite sous une catégorie
choisie par l’administrateur ; leur validation et leur implantation restent manuelles.
Des boîtes hors image bloquent toutes les superpositions de cette réponse.
La liste des analyses expose un `payload` limité à moteur/document/page pour
retrouver les résultats après rechargement ; les paramètres internes restent privés.

Un exemple porte `engine`, `project_id`, `document_id`, `page`, `floor_id`, `region`,
`rotation` et `labels`. Coordonnées normalisées dans la page source redressée,
origine en haut à gauche ; zoom et rotation d’affichage ne les réécrivent pas.

Chaque label contient :

- `id`, `category`, `bbox` : région du texte ou de l’objet détecté.
- `anchor` : point d’implantation distinct de la boîte, obligatoire pour un équipement validé.
- `segments` : paires de points d’axes médians, réservées aux murs.
- `mask_polygons` : masques polygonaux source, séparés des axes ; jamais des contours à dessiner comme murs.
- `text` : transcription exacte, sans normalisation H₂O/H2O ou CO₂/CO2.
- `origin` : provenance déclarée (`manual`, moteur/version, service de géométrie…).
- `checked` : vérification humaine explicite, distincte de la confiance IA.

Le champ d’exemple `junctions` conserve les raccordements. `observed` conserve la
réponse Qwen proposée, `interpretation` sa correction, `convention` la règle métier.
Un mur reste un seul trait noir plein sur chaque segment d’axe. Le serveur coupe
les segments aux boîtes de portes/ouvertures et refuse les axes identiques dupliqués.
Il ne devine pas l’axe médian depuis deux contours : le service architectural ou le
dessinateur doit le fournir. Une modification remet l’exemple en brouillon.

Validation : `POST /examples/{id}/decision` avec `revision` et `status=validated`.
Le projet doit avoir l’autorisation explicite `metadata.training_authorized=true`,
posée par un administrateur via la route metadata existante. Il faut vérifier
chaque label et renseigner les champs propres au moteur. Un rejet exige `reason`.
Aucune correction de production n’entre automatiquement dans un dataset.

## Datasets et séparation des lots

La version fige labels, catégories, statut/révision, auteur, source/hash, repères,
transformations et split. Les originaux restent dans le stockage privé OVH sauvegardé.
Les adresses normalisées regroupent les bâtiments ; faute d’adresse, le projet sert
au regroupement. Tout document identique est également regroupé, même copié dans
plusieurs projets. Cette union interdit la fuite d’un PDF entre deux lots.

Avec moins de trois groupes indépendants, seul le lot train est produit et un
avertissement interdit de prétendre à une évaluation indépendante. À partir de trois,
les deux derniers groupes d’un ordre déterministe sont réservés à validation/test.
Ce découpage simple est explicite, pas un stratificateur de classes ; la préparation
RTMDet refuse les classes absentes du train. Renseigner l’adresse réelle du bâtiment
avant gel. Vérifier les doublons de scans différents d’un même bâtiment humainement.

Le ZIP contient `examples.json`, `coco.json`, `images/*.png`, puis selon le moteur :
`ocr.jsonl` et `ocr/*.png`, ou `qwen.jsonl` (messages + chemin d’image).
Les axes et masques restent dans `examples.json` ; aucune segmentation n’est inventée
à partir d’un trait. Les boîtes COCO sont en pixels, les anchors restent normalisés
et distincts. L’export est limité à 256 Mio de rasters cumulés avant compression.
La révocation de l’autorisation du projet bloque la réexportation et l’utilisation
par le registre. Elle n’efface pas les versions/audits déjà conservés.

## Qwen : référentiel ≠ fine-tuning

`POST /models/qwen/versions` reçoit `name` et `dataset_id`. Il utilise uniquement
les exemples **train** pour constituer les règles `convention → interpretation`.
La version conserve auteur, date, dataset/hash et hash du référentiel en base OVH.
Elle est `development`, `method=reference`, `weights_trained=false`.

Le test actuel effectue une recherche exacte sur le lot test et compare au
référentiel de production s’il existe. Il indique `model_inference_tested=false` et
`publication_eligible=false` : ce test ne suffit jamais à approuver Qwen. La recherche
lexicale peut alimenter un futur prompt versionné, mais les analyses clients actuelles
ne sont pas modifiées par cette livraison.

## Workers GPU et prochaines étapes

Le [raccordement RTMDet](ENTRAINEMENT-RTMDET.md) implémente la file persistante,
l’idempotence, les ZIP de soumission persistants, le profil de départ figé,
la priorité aux inférences, les checkpoints/reprises et la protection contre
l’arrêt automatique. La progression vient du framework, jamais d’un minuteur.
Les sous-processus et les copies d’artefacts sont testés sur CPU ; leur recette
sur le vrai GPU reste indispensable avant activation de la capacité.

`POST /runs` exige `confirmed=true` et `request_key` stable (16–80 caractères
alphanumériques, tiret ou underscore), moteur, dataset et paramètres. États :
`queued`, `waiting_gpu`, `dispatching`, `running`, `checkpointing`, `paused`,
`cancel_requested`, `cancelled`, `failed`, `completed`, `interrupted`.
Le GET renvoie la demande, son profil/Pod figés, état, progression, erreur contrôlée
et manifeste de résultat lorsqu’il est vérifié. Le journal contient les observations
d’itération, perte et époque ; les logs détaillés restent sur le volume privé du Pod.

Une interruption après redémarrage ne relance pas automatiquement un calcul déjà
commencé. `/runs/{id}/resume` exige `confirmed=true` et un checkpoint vérifié sur le
même profil/Pod. Une pause demandée pour laisser passer les inférences peut reprendre
automatiquement une fois celles-ci terminées. Toute tâche non terminale protège le
GPU contre l’arrêt, même en cas de panne réseau.

Il reste à développer l’évaluation comparative sur des documents indépendants,
l’approbation humaine journalisée, puis la promotion transactionnelle **sur OVH**,
le pointeur précédent, la version figée à l’admission des inférences et le rollback.
Les statuts `approved`, `production`, `archived` existent mais leurs transitions
ne sont pas activées. Qwen/PaddleOCR nécessitent leurs propres pilotes validés ;
un moteur architectural absent reste indisponible.
