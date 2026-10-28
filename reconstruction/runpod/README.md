# Raccordement OVH / RunPod — prototype 0.2.2

**Architecture courante : image Docker privée versionnée, prise en charge par une autre session.** Pour le premier essai d’inférence, suivre [TEST_DEPLOIEMENT.md](TEST_DEPLOIEMENT.md). Son lanceur ne restaure rien et doit être intégré au démarrage de cette image. Les procédures de restauration ci-dessous sont conservées comme secours et ne constituent pas le démarrage normal.

État au 28 octobre 2026 : code et tests locaux disponibles ; aucun déploiement ni appel aux trois IA RunPod effectué dans cet environnement. Dernier état rapporté par le propriétaire : les trois environnements ont été restaurés sur le nouveau Pod. Qwen dispose de CUDA et de quatre fichiers de poids ; PaddleOCR utilise gpu:0 avec son cache PaddleX ; RTMDet/MMDetection 3.3.0 dispose de CUDA. Ce rapport remplace les relevés antérieurs de chemins manquants. Il ne constitue pas une inférence effectuée par cette session. L’accès TCP/SSH depuis Codex reste indisponible. La clé privée SSH de développement n'est incluse dans aucun livrable.

## Répartition des responsabilités

- **OVH** : projets, préparation PDF, conservation des coordonnées, module spécialisé DOEMO Walls, reconstruction vectorielle, SQLite local pour les tâches, corrections et validation humaine.
- **RunPod existant** : Qwen3.5-9B pour interpréter des zones identifiées ; PaddleOCR pour les textes et leurs polygones ; RTMDet COCO uniquement en diagnostic d'objets génériques. Le module murs ne dépend pas de RTMDet.
- **Segmentation architecturale** : point d'extension séparé. Aucun poids qualifié disponible. `POST /jobs/detect-walls` répond explicitement 503 `architectural_segmentation_not_qualified` ; il ne bascule pas vers COCO.
- **Illustrator** : contrat `doemo.architecture.illustrator/2`, tracés ouverts, noirs, sans remplissage, épaisseur graphique distincte. Transport réel et recette Adobe restent à effectuer.

## Audit et restauration de secours sur le Pod

En cas de panne seulement, commencer par l'inventaire, sans changer les environnements. Lancer `restore.py` uniquement si l’inventaire confirme un composant manquant ; les trois IA déclarées restaurées n’exigent pas cette procédure :

```bash
python3 runpod/inventory.py
python3 runpod/restore.py --inventory
python3 runpod/restore.py
python3 runpod/audit.py
```

`inventory.py` relève l’identité du Pod, le GPU, le montage de `/workspace`, les dossiers persistants et l’état exact de chaque interpréteur. La présence d’un exécutable ne vaut jamais test d’inférence.

`bootstrap.sh` et `restore.py --apply` exigent une identité RunPod présente, une RTX A6000 accessible et les répertoires modèles/sauvegardes sur le montage persistant attendu. Ces contrôles précèdent les écritures. Un contrôle effectué sur OVH ou sur le poste de développement ne renseigne pas l’état du Pod. La restauration vérifie aussi l’espace disque local disponible.

`restore.py` est en simulation par défaut. Il contrôle les racines archivées, les sorties de répertoire, liens, types spéciaux et doublons. `--apply` restaure uniquement une destination absente, dans un répertoire temporaire sur le même disque local, puis publie le composant. Un environnement présent mais cassé n'est jamais écrasé : le rapport demande une réparation distincte. Les sept archives restent intactes. Un verrou local interdit deux restaurations simultanées.

Les composants par défaut sont Python 3.11.18, les trois venvs `/opt`, et `/root/.paddlex`. Le lien de compatibilité Python est créé seulement s'il manque. Pour `doemo-uv.tar.gz` et `rtmdet-poids.tar.gz`, inspecter le contenu puis ajouter leurs racines réelles à un manifeste `[{archive,component,target}]` passé par `--manifest`. Le nom d'une archive ne permet pas de deviner sa structure. Les poids RTMDet déjà présents sont réutilisés ; aucun téléchargement n'est lancé.

Les caches pip/uv et les fichiers d'inférence temporaires sont sous `/tmp`. Aucun venv ni fichier SQLite ne doit être placé sur le volume FUSE `/workspace`. Les données persistantes et résultats restent sous `/workspace/doemo-studio`.

Après restauration : renseigner `models.example.json` avec les répertoires Paddle réellement présents et les fichiers config/checkpoint RTMDet déjà installés. Les valeurs `REPLACE_WITH...` sont volontairement bloquantes. Renseigner des versions de modèles stables, idéalement des empreintes de snapshots. Les runners imposent le chargement local et n'installent aucun paquet dans les trois venvs.

```bash
/opt/doemo-service-venv/bin/python runpod/audit.py --functional --config /chemin/models.json --image /chemin/test.png
```

Les imports et l'exécution d'une inférence sont deux contrôles distincts. L'audit énumère les versions Torch, Torchvision, MMCV, MMEngine et MMDetection, et contrôle CUDA. Le test fonctionnel doit réellement fonctionner avec les versions installées ; les adaptateurs Paddle 2/3 et Transformers Qwen n'ont pas encore été vérifiés sur ce Pod. Une incompatibilité doit être corrigée dans l'adaptateur avant toute modification de venv.

## Service privé

Le service utilise un environnement léger séparé `/opt/doemo-service-venv` : FastAPI, Uvicorn, HTTPX, cryptography et le paquet DOEMO. C'est un service de communication sur le Pod existant, sans nouvelle infrastructure GPU ni nouveau modèle. Installer le code relu dans cet environnement ; démarrer avec **un seul processus**. Ne pas ajouter ces dépendances aux trois venvs de modèles.

`bootstrap.sh` restaure les composants absents, journalise, vérifie les imports puis démarre le worker. Il inclut également la restauration de `/opt/doemo-service-venv` depuis une archive dédiée `doemo-service-venv.tar.gz`. Cette archive supplémentaire doit être créée après l’installation initiale du service, sans remplacer les sept sauvegardes IA existantes. Si le service est absent et sa sauvegarde manque, le démarrage échoue explicitement ; aucune installation automatique improvisée ne modifie les moteurs. Son démarrage lance aussi une inférence de contrôle sur chacun des trois modèles ; `/health.ready` reste faux tant que ces contrôles n'ont pas tous réussi. La restauration automatique suppose ce bootstrap et sa configuration enregistrés dans le stockage persistant, puis son lancement dans la commande de démarrage du conteneur RunPod, en conservant les autres services utiles. Une préparation de scripts ne constitue pas une activation du démarrage automatique.

Variables RunPod : `DOEMO_MODELS_CONFIG`, `DOEMO_ENGINE_RUNNER`, `DOEMO_OVH_PUBLIC_KEY` (fichier public), éventuellement `DOEMO_RUNPOD_RESULTS`. `DOEMO_WORKER_EXCLUSIVE=1` exige que tous les travaux du Pod passent par cette file ; sans ce réglage, l’arrêt automatique est refusé. Le port applicatif proposé est 8009 ; il doit être exposé via HTTPS RunPod ou un tunnel privé contrôlé. Le port Jupyter n'est pas utilisé par le navigateur ni par les jobs.

Variables OVH : `RUNPOD_API_KEY`, `RUNPOD_NETWORK_VOLUME_ID`, `DOEMO_SERVICE_ID=DOEMO-STUDIO-IA`, `DOEMO_OVH_PRIVATE_KEY`, `DOEMO_OVH_PUBLIC_KEY`, `DOEMO_JOBS_DB` sur disque local, `DOEMO_WORKER_PORT=8009`, `DOEMO_AUTOSTOP=0` pour la première recette. La clé API RunPod et la clé privée de signature restent sur OVH ; seul le vérificateur public va sur le Pod. Générer une paire Ed25519 dédiée au service, distincte de la clé SSH.

```bash
/opt/doemo-service-venv/bin/python -m uvicorn doemo_reconstruction.ai_service.service:app_factory --factory --host 127.0.0.1 --port 8010 --workers 1
```

Le backend Studio autorise l'accès au projet avant de signer un jeton de service. Les appels internes sont signés avec `auth.issue`, audience `doemo-orchestrator`, portée `jobs`, durée maximale 300 secondes. Le client OVH signe les appels au worker avec audience `doemo-runpod`, portée `worker`. HTTPS est obligatoire hors loopback, vérification TLS active, pas de suivi de redirections avec les jetons. Le worker ne reçoit aucun secret de contrôle RunPod.

L'API privée OVH expose `/health`, `/models`, `/jobs/analyze-floorplan`, `/jobs/detect-walls`, `/jobs/{id}` et `/jobs/{id}/results`. Les POST d'analyse exigent `Idempotency-Key` et le contrat `AnalysisRequest` : projet, page, SHA-256 de source et PNG, dimensions exactes, régions connues, versions des modèles, paramètres. La page est rendue sur OVH ; le PNG préparé est envoyé au Pod. Les résultats OCR et Qwen sont des observations en pixels du PNG. `evidence.attach_evidence` contrôle la provenance et transforme explicitement les coordonnées vers celles du document sans modifier les murs validés ni calibrer une échelle.

Les corps HTTP sont limités à 13 Mio, y compris en transfert fragmenté ; ajouter aussi une limite de requêtes au proxy OVH. Ne pas publier ces routes comme une API utilisateur sans les contrôles d'accès par projet de Studio. L'éditeur HTML livré est un banc autonome et ne contient aucun secret ni appel direct à RunPod.

## Tâches, reprise et coût GPU

SQLite OVH conserve UUID, projet/page, paramètres, versions, progression par étapes réelles, horodatages, tentatives, erreurs et résultat. Les étapes ne simulent pas le pourcentage de calcul interne d'un modèle. Une relance identique récupère le même job ; un résultat terminé n'est pas remplacé. Une même clé avec d'autres paramètres est refusée. Les propositions IA sont séparées du projet corrigé par le dessinateur.

Après un redémarrage OVH, une tâche qui pouvait encore tourner sur le Pod passe en `interrupted`. `JobStore.reconcile(job_id, remote_idle=True)` ne doit être appelé qu'après vérification de l'activité distante. Cette réconciliation n'est pas automatisée à l'aveugle.

Sur FUSE, le worker conserve le résultat par empreinte puis un manifeste de validation, avec relecture de contrôle. Une sauvegarde incomplète bloque l'arrêt, y compris après redémarrage du worker. L'opérateur doit récupérer ou réparer ces dossiers avant reprise. Un résultat déjà enregistré est retourné sans répéter l'inférence.

Le contrôleur retrouve le Pod à chaque opération par volume réseau **et** nom fonctionnel ou variable `DOEMO_SERVICE_ID`. En cas de migration, reporter ce marqueur dans le nouveau Pod ; aucun ID ou hôte fixe n'est codé. Zéro ou plusieurs correspondances bloquent la commande. Un échec de démarrage GPU appelle une intervention contrôlée ; aucun Pod ni volume n'est supprimé ou recréé automatiquement.

L'arrêt à 30 minutes nécessite : aucune tâche en attente, active, en sauvegarde ou interrompue ; résultats OVH validés ; worker distant prêt, inactif et sans sauvegarde en cours, propriété exclusive déclarée et aucun processus de calcul GPU détecté ; au moins 30 minutes sans activité observée. L'admission des tâches et l'arrêt partagent le même verrou. Le worker est placé en drainage avant l'arrêt. Un échec ambigu de l'API d'arrêt laisse le worker drainé et exige une réconciliation. Activer `DOEMO_AUTOSTOP=1` seulement après la recette sur le Pod existant ; le code ne remplace pas la vérification que le Pod n'héberge pas d'autres traitements extérieurs à cette file.

API officielles vérifiées le 28 octobre 2026 :

- [Liste des Pods](https://docs.runpod.io/api-reference/pods/GET/pods), `GET https://rest.runpod.io/v1/pods`, authentification Bearer.
- [Démarrage](https://docs.runpod.io/api-reference/pods/POST/pods/podId/start), `POST /v1/pods/{podId}/start`.
- [Arrêt](https://docs.runpod.io/api-reference/pods/POST/pods/podId/stop), `POST /v1/pods/{podId}/stop`.
- [Capacité GPU au redémarrage](https://docs.runpod.io/pods/troubleshooting/zero-gpus) : le démarrage demandé ne garantit pas une capacité GPU disponible. La disponibilité effective est contrôlée par le worker.

## Segmentation spécialisée à qualifier

CubiCasa5K/FloorTrans est intéressant pour la segmentation multi-classe et les jonctions. La [licence du dépôt](https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) est CC BY-NC 4.0 ; aucun élément couvert n'est intégré commercialement dans ce prototype.

Piste proposée : un U-Net pour murs/cloisons/ouvertures, entraîné sur des annotations DOEMO autorisées, dans `/opt/doemo-wall-seg-venv`. [Segmentation Models PyTorch](https://github.com/qubvel-org/segmentation_models.pytorch/blob/main/LICENSE) a une licence générale MIT, mais ses [licences par composant](https://github.com/qubvel-org/segmentation_models.pytorch/blob/main/licenses/LICENSES.md) comportent des exceptions, dont un encodeur SegFormer à usage non commercial. Il faut donc vérifier l'implémentation et l'encodeur exacts, les poids initiaux et les droits des données. Il ne suffit pas de lire la licence générale. Aucune installation ni acquisition de poids n'est effectuée avant validation du choix.

Le worker ONNX existant reste isolé, sans poids. `wall_module.reconstruct_mask` transforme un masque architectural dans son repère explicite en axes médians, conserve les branches et exclut les classes portes/fenêtres/textes. Cette chaîne est testée sur masques synthétiques ; elle n'a pas encore reçu de masque produit par un modèle réel sur le PDF fourni.

## Preuves après migration

La santé du worker retourne son Pod ID actuel et un identifiant d’instance renouvelé à chaque démarrage. Le client OVH refuse un worker dont l’identité diffère du Pod redécouvert ; le contrôleur d’arrêt applique le même contrôle. Chaque nouvelle inférence enregistre son instance d’exécution. Un résultat déjà commis peut être relu après migration avec sa provenance d’origine.

La présence des venvs, CUDA, caches et poids se vérifie avant les tests. La disponibilité fonctionnelle exige ensuite une véritable inférence Qwen, OCR et RTMDet. Aucun de ces contrôles ne prouve une reconnaissance de murs : le modèle architectural reste à sélectionner et qualifier séparément.

Vérification du code : 40 tests locaux, avec des configurations synthétiques pour les scénarios de migration, identité de Pod et interpréteur cassé. Aucun test distant RunPod n’a été exécuté dans cette session.
