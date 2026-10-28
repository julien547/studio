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

## RTMDet : raccordement livré, recette GPU à réaliser

La [procédure RTMDet](ENTRAINEMENT-RTMDET.md) décrit les fichiers, la migration
`004`, le nouveau worker OVH et le profil accepté. La file est raccordée au
navigateur et au gateway : demandes idempotentes, consentement, attente GPU,
pause à la fin d’une époque pour l’inférence, reprise et annulation.

`rtmdet_pipeline.py` appelle réellement `MMEngine Runner.train()` puis `Runner.test()`
avec MMDetection 3.3.0. **Il n’a pas été exécuté sur GPU ici.** La capacité reste
inactive sans recette réelle de `accept_training.py`, qui teste deux époques avec
pause/inférence/reprise et une annulation séparée. Cette recette nécessite une
maintenance et un coût GPU autorisés, organisés uniquement par la session de
déploiement. Aucun script ne stoppe le vLLM préexistant ou un service tiers.

Le simple essai d’une époque du pilote ne suffit plus à activer la capacité :
utiliser la recette complète décrite dans la procédure. Les métriques produites
sont celles du lot test ; elles ne valent pas comparaison à la production.

## PaddleOCR, Qwen, architecture

- `training_data.ocr_splits` convertit les images/transcriptions en labels PaddleOCR.
  Le pilote de reconnaissance CTC et sa file sont maintenant raccordés. Voir
  [ENTRAINEMENT-PADDLEOCR.md](ENTRAINEMENT-PADDLEOCR.md) pour les profils compatibles,
  la recette GPU obligatoire et la nouvelle variable privée. Les poids candidats
  ne sont pas un export de service ; le détecteur existant reste distinct.
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
Le raccordement RTMDet, la priorité, les reprises et les artefacts sont maintenant
implémentés et testés localement. Restent la recette GPU complète, le pilote
Qwen, l’évaluation comparative indépendante, l’approbation administrative,
les pointeurs de production transactionnels par moteur, la version figée par
inférence et le rollback. Aucun candidat n’est automatiquement mis en production.

Validation locale du 28 octobre 2026 : **118 tests backend réussis**. Tests CPU
sur API, persistance, consentement/révocation, corrections et splits, puis protocole
asynchrone, déduplication, réponses perdues, annulation, checkpoints et exclusion.
Aucun entraînement réel, arrêt/redémarrage Pod, build Docker ni promotion d’un modèle
n’a été exécuté dans cette session.

La page React `/entrainement` est maintenant raccordée aux API : import,
corrections, validation/rejet, datasets, exports, référentiel Qwen, analyses
existantes et supervision GPU. Validation locale complémentaire : build TypeScript,
8 tests de géométrie, 6 parcours Playwright avec vrai backend temporaire (dont
redémarrage du processus, conflit de révision, restriction administrateur, murs,
implantations distinctes et résultats RTMDet rejoués sans appel GPU).

## Suite : comparaison Qwen raccordée

La migration `005` et [COMPARAISON-QWEN.md](COMPARAISON-QWEN.md) ajoutent les essais
avec/sans conventions du référentiel sur des plans réservés au test, avec historique
et avis humain. Aucune modification des poids ou promotion. Cette livraison du
gateway modifie son empreinte de runtime : refaire la recette du profil RTMDet
avant de l’activer avec ces nouveaux fichiers. Déploiement et recette GPU sont
exclusivement à la charge de la session serveur.
