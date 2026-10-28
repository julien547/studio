# Reprise du backend IA — audit distant encore requis

La responsabilité de cette session a été clarifiée par l’utilisateur : **développer
la page Entraînement ET son backend**. La session de déploiement s’occupe seule des
serveurs. Lire [la livraison de la page](PAGE-ENTRAINEMENT.md),
[le contrat partagé](CONTRAT-ENTRAINEMENT-IA.md) et
[l’OpenAPI](api/training-openapi.json). Les capacités réelles, pas la présence d’une
route, déterminent quels boutons peuvent être activés.

## Accès

Aucun SSH distant ni appel au Pod n’a été exécuté depuis cette session cloud :
VPN non configuré, autorisations TCP vides, aucun agent SSH. Le transport TCP
supporté exige un VPN Tailscale et une destination privée autorisée ; ajouter l’IP
publique OVH aux domaines HTTP ne donne pas un accès SSH. L’utilisateur confirme
que son SSH fonctionne depuis le Mac. Une session Codex locale sur ce Mac peut
reprendre avec cet accès et la vérification de clé d’hôte existante. Ne jamais
copier de clé privée dans le chat ou Git.

La procédure utilisateur indique, sans vérification distante de cette session :

- serveur Debian 13, code `/opt/doemo-studio-releves/src` ;
- venv OVH `/opt/doemo-studio-releves-venv` ;
- secrets privés `/etc/doemo-studio/runpod/` ;
- services `doemo-releves`, `doemo-releves-worker`, `doemo-releves-gpu` ;
- modèle Qwen `/workspace/doemo-studio/models/qwen/Qwen3.5-9B` ;
- modèles PaddleOCR `/root/.paddlex/official_models/` ;
- archives venv `/workspace/doemo-studio/restore/current/` ;
- code Pod `/workspace/doemo-studio/services/runpod/`.

Les anciens modèles `releves/deploy/` emploient d’autres chemins : ne pas les
installer sans adaptation et ne pas remplacer les services existants globalement.

## Audit en premier

Sur OVH, charger les variables des fichiers privés existants sans les afficher.
`releves/scripts/inspect-runpod.py` effectue seulement un GET fournisseur et affiche
une liste restreinte de métadonnées/coordonnées SSH. Il exclut entièrement `env`.
L’exécuter sur OVH avec l’environnement de service, jamais avec une copie de la clé
sur le Mac/cloud. Aucun démarrage, arrêt, PATCH ou suppression n’est effectué.
Relire le Pod ID actuel et son adresse SSH ; les anciens ID ne sont pas des défauts.
Le helper `configure-runpod.py` exige désormais `--pod-id` explicite ; ne pas recréer
les secrets déjà présents.

Sur le Pod, vérifier activité, GPU et volume avant toute modification. Copier les
nouveaux scripts dans un dossier de recette distinct. Puis, dans une période libre :

```sh
python3 audit_runtime.py --smoke \
  --output /workspace/doemo-studio/exports/audit-ia-nouvelle-session.json
```

Choisir un nom neuf. Le script ne réinstalle rien ; `--smoke` charge les trois moteurs
et effectue des inférences minimales. Sans ce flag, seule la présence/versions/CUDA
est contrôlée et `inference_verified` reste faux. Conserver rapport et journaux.

**PaddleOCR :** vérifier une copie intègre des poids de `/root/.paddlex` sur
`/workspace`. La sauvegarde des venvs `/opt` ne contient pas ces poids. S’ils ne sont
pas persistants, les copier sans supprimer la source, vérifier les hashes et changer
les chemins dans la configuration du Pod, puis tester l’inférence.

## API et persistance déjà utilisables

La migration `003_training.sql` ajoute exemples/révisions, catégories, datasets,
registre, réserve de tâches et audit. Sauvegarder base et documents avant migration.
L’import réutilise les routes existantes. Enregistrement, validation autorisée,
rejet, gel/export et référentiel Qwen fonctionnent sans GPU. Aucun poids ni prompt
de production n’est modifié. Les données SQLite restent sur OVH, jamais sur FUSE.

## RTMDet : recette GPU à réaliser

`rtmdet_pipeline.py` appelle réellement `MMEngine Runner.train()` puis `Runner.test()`
avec MMDetection 3.3.0 : classes DOEMO, paramètres conservateurs, checkpoints par
époque, métriques, événements d’itération/perte et copies vérifiées sur `/workspace`.
**Il n’a pas été exécuté sur GPU ici.** Les validations CPU ne prouvent pas la
compatibilité du profil réel ; la capacité d’entraînement web reste désactivée.

Le pilote exige une autorisation explicite et un verrou excluant le gateway actif
ou un autre pilote. C’est un outil de recette en **maintenance autorisée**, pas
un entraînement concurrent des dossiers clients. Il ne stoppe aucun service.
Le contrôleur OVH refuse l’arrêt automatique sans santé fraîche du gateway.

Après audit et autorisation de l’essai court :

```sh
/opt/doemo-rtmdet-venv/bin/python rtmdet_pipeline.py \
  --dataset /workspace/doemo-studio/imports/dataset-autorise.zip \
  --config "$DOEMO_RTMDET_CONFIG" --weights "$DOEMO_RTMDET_WEIGHTS" \
  --epochs 1 --batch-size 1 --learning-rate 0.0001 \
  --authorize-gpu-training
```

Ne pas exécuter cette commande sans organiser la maintenance et obtenir
l’autorisation du coût GPU. Le dataset doit avoir trois groupes indépendants,
avec toutes les classes représentées dans train. Les copies sans manifeste complet
ne constituent pas un modèle enregistré. Préemption, reprise et comparaison à la
version précédente restent à implémenter/tester avant le raccordement web.

## PaddleOCR, Qwen, architecture

- `training_data.ocr_splits` convertit les images/transcriptions en labels PaddleOCR.
  `ocr_metrics` calcule CER/WER sans normalisation silencieuse. Auditer le dépôt
  d’entraînement et le YAML de reconnaissance réels avant d’écrire le trainer.
  Le package d’inférence n’implique pas la présence de `tools/train.py`. Ne pas
  remplacer le détecteur de texte quand seule la reconnaissance doit changer.
- Qwen : référentiel persistant versionné et recherche lexicale disponibles ; le
  test actuel ne vérifie pas l’inférence du modèle. Auditer Transformers, PEFT,
  quantification et VRAM avant un LoRA/QLoRA. Distinguer référentiel, prompts et poids.
- Architecture : axes, masques polygonaux, raccordements et ouvertures conservés ;
  aucun réseau de segmentation installé n’est annoncé. Dessiner un seul trait
  noir plein par axe de mur, sans fermer les ouvertures.

## Image Docker permanente

Recette `services/runpod/Dockerfile` fournie mais **non construite/non validée**.
`BASE_IMAGE` doit être l’image exacte auditée. Le contexte privé `restore/` contient
les archives de venv et leur manifeste ; le build vérifie/restaure ces archives.
Le second stage copie `/opt`, sans clé ni poids/dataset. Le bootstrap garde la
restauration de secours depuis le volume persistant.

Ne pas utiliser de secret comme ARG/ENV de build. Ne jamais inclure `runpod-ovh.env`.
Publier l’image dans un registre privé après vérification des interpréteurs, des
poids persistants et des inférences sur GPU. Enregistrer son digest après recette.

## Conditions avant activation en production

Les routes de promotion refusent l’activation tant que les adaptateurs réels ne
sont pas raccordés. Ne pas contourner les contrôles en changeant les statuts SQL.
Il reste à implémenter et tester ensemble : ordonnanceur avec inférence prioritaire,
idempotence, annulation/checkpoints/reprise, tâches persistantes prises en compte
par l’arrêt automatique, évaluation comparative indépendante, ingestion vérifiée
des poids, approbation administrative, pointeurs de production transactionnels par
moteur, version figée par inférence et rollback.

Validation du 28 octobre 2026 : **98 tests backend réussis**, dont 18 nouveaux cas
d’apprentissage/artefacts. Tests effectués : API CPU, persistance après réouverture, consentement/révocation,
conflits, murs/ouvertures, groupes de splits, images/transcriptions exportées,
artefacts/hash, référentiel Qwen et refus des opérations GPU indisponibles.
Aucun entraînement réel, arrêt/redémarrage Pod, build Docker ni promotion d’un modèle
n’a été exécuté dans cette session.

La page React `/entrainement` est maintenant raccordée aux API : import,
corrections, validation/rejet, datasets, exports, référentiel Qwen, analyses
existantes et supervision GPU. Validation locale complémentaire : build TypeScript,
8 tests de géométrie, 5 parcours Playwright avec vrai backend temporaire (dont
redémarrage du processus, conflit de révision, restriction administrateur, murs,
implantations distinctes et résultats RTMDet rejoués sans appel GPU).
