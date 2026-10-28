# Raccordement de l’entraînement RTMDet — passation au déploiement

Le navigateur, l’API OVH, le worker persistant et le gateway GPU sont raccordés
dans le code de la branche `codex/ai-training-backend`. **Aucun serveur n’a été
modifié et aucun entraînement GPU n’a été exécuté par cette livraison.** La session
de déploiement reste seule responsable d’OVH et RunPod.

L’entraînement est désactivé par défaut. Son activation exige une recette réelle
produisant un profil accepté pour le code, la configuration et les poids exacts.
La présence d’un GPU ou de packages Python ne constitue pas cette recette.

## Fichiers à livrer ensemble

| Fichier | Fonction |
| --- | --- |
| `backend/doemo_releves/training_jobs.py` | Admission, consentement, déduplication, transport et suivi OVH |
| `backend/doemo_releves/migrations/004_training_jobs.sql` | Demandes persistantes, profil/Pod figés, reprises et unicité |
| `backend/doemo_releves/gpu.py`, `queue.py` | Protection contre l’arrêt et priorité aux analyses |
| `services/runpod/training_service.py` | File persistante GPU, checkpoints, contrôles et résultats |
| `services/runpod/rtmdet_pipeline.py` | Entraînement et test réels MMDetection 3.3 / MMEngine |
| `services/runpod/compute.py`, `gateway.py` | Exclusion GPU partagée et routes privées authentifiées |
| `services/runpod/accept_training.py` | Recette opérateur avec pause, inférence, reprise et annulation |
| `deploy/doemo-releves-training.service` | Modèle du nouveau worker OVH, chemins à adapter |
| `web/src/training/TrainingPage.tsx` | Autorisation du lancement, suivi, annulation et reprise explicite |

Copier tout le dossier `services/runpod/` de la même révision, pas seulement le
pilote. Il importe notamment `training_data.py`, `artifacts.py` et `readiness.py`.
Un seul processus Uvicorn est supporté. Le bootstrap existant restaure les venvs
du volume si nécessaire ; ce raccordement ne remplace pas sa recette.

## Préparer l’installation avec la session de déploiement

1. Examiner l’état actuel des serveurs et les modifications éventuelles de l’autre
   session. Préserver sa configuration. L’ancien Pod ID n’est jamais un défaut :
   lire l’identifiant actuellement configuré sur OVH.
2. Avant migration, suspendre les admissions et workers concernés et vérifier une
   sauvegarde restaurable de SQLite, `documents`, `libraries` et `training-outbox`.
   `scripts/backup.py` inclut désormais ce dernier dossier. Ses ZIP doivent conserver
   exactement leurs octets pour dédupliquer une soumission dont la réponse a été
   perdue. Sauvegarder également le contenu persistant du Pod selon l’exploitation.
3. Livrer le backend, construire le frontend (`npm ci`, `npm run build` dans
   `releves/web`) et suivre `PAGE-ENTRAINEMENT.md`. Le Store applique automatiquement
   les migrations manquantes, dont `004`. Ne pas exécuter le SQL deux fois.
4. Adapter le nouveau service à l’installation existante. Les chemins communiqués
   par la session distante sont `/opt/doemo-studio-releves/src` et
   `/opt/doemo-studio-releves-venv` ; le template emploie des chemins génériques.
   Vérifier utilisateur, groupe, variables privées et `ReadWritePaths`. La commande
   du worker est `python -m doemo_releves.training_jobs` avec le Python du backend.
   Ne pas remplacer globalement les unités déjà présentes.
5. Conserver les workers d’analyse et de cycle de vie GPU. Le nouveau worker ne
   les remplace pas. L’API fournisseur RunPod et sa clé restent exclusivement sur
   OVH. Le Pod reçoit seulement le jeton privé du gateway, jamais la clé fournisseur.
6. Livrer le gateway et les scripts au Pod dans la fenêtre prévue par la session
   de déploiement. Vérifier les trois inférences réelles et résoudre les problèmes
   de disponibilité déjà constatés. Le code exige que les trois moteurs soient
   prêts avant d’admettre l’entraînement.

Le service vLLM préexistant doit être pris en compte par l’opérateur. Le pilote
refuse de démarrer si `nvidia-smi` voit un processus de calcul existant. Il ne tue
ni vLLM ni aucun service tiers. Il faut une stratégie de disponibilité compatible
avant activation ; une simple quantité de VRAM libre ne suffit pas.

## Recette GPU réelle, uniquement par la session de déploiement

Utiliser un petit dataset RTMDet autorisé, exporté par l’application, avec trois
groupes indépendants train/validation/test et toutes les classes dans train.
Vérifier la configuration et les poids locaux. La configuration est du Python de
confiance choisi par l’opérateur ; aucun client web ne peut en envoyer.

Organiser une maintenance explicitement autorisée et le coût GPU de cet essai.
La commande suivante **exécute réellement un entraînement**. Le gateway doit être
arrêté proprement par l’opérateur et aucun autre calcul ne doit être présent. Le
script ne fait lui-même aucun arrêt de service. Adapter le Python au venv gateway
qui fournit FastAPI, Pillow et python-multipart ; le pilote enfant utilise le venv
RTMDet fixe `/opt/doemo-rtmdet-venv/bin/python`.

```sh
/chemin/venv-gateway/bin/python accept_training.py \
  --dataset /workspace/doemo-studio/imports/dataset-autorise.zip \
  --config "$DOEMO_RTMDET_CONFIG" \
  --weights "$DOEMO_RTMDET_WEIGHTS" \
  --profile-output /workspace/doemo-studio/config/rtmdet-training-profile-nouveau.json \
  --authorize-gpu-training --maintenance-confirmed
```

La recette effectue deux époques, demande une pause au premier checkpoint, exécute
une vraie inférence de contrôle PaddleOCR, reprend jusqu’au résultat vérifié puis
teste l’annulation sur une autre tâche. Le délai est borné (`--timeout`, 3600 s par
exécution par défaut). En cas d’interruption, seuls ses propres sous-processus sont
terminés, puis récoltés avant libération du verrou. Un échec ne crée aucun profil
accepté ; les journaux sont conservés pour diagnostic.

Après succès seulement :

- Conserver le rapport sous `training/acceptance/<id>/report.json` et les journaux.
- Installer le profil produit dans un fichier privé lisible par le service sur
  OVH et sur le Pod. Le contenu doit être identique ; le chemin du fichier peut
  différer. Définir `DOEMO_TRAINING_PROFILE` dans leurs environnements de service.
- Ce fichier contient les empreintes du pilote, du runtime, de la configuration,
  des poids et du rapport, ainsi que les chemins privés config/weights sur le Pod.
  Ne pas le fabriquer à la main en positionnant les quatre indicateurs à `true`.
- Redémarrer les services concernés selon la procédure de la session de déploiement.
  Vérifier `/training/capabilities` sur le gateway et
  `/projects/training/capabilities` sur OVH. Les `profile_id` doivent correspondre.
- Depuis la page administrateur, réaliser une recette de bout en bout autorisée :
  lancement, progression réelle, analyse prioritaire, annulation/reprise, résultat
  candidat. Vérifier le refus d’arrêt GPU pendant une tâche active ou en attente.

Une modification du runtime, du profil ou des poids invalide la recette côté Pod.
Refaire la recette avant activation du nouveau profil. Le backend peut encore
présenter l’ancien profil jusqu’à mise à jour ; le gateway refuse alors la demande
incompatible. Aucun changement silencieux de base ou de Pod n’est effectué.

## Contrat et garanties de fonctionnement

`POST /projects/training/runs` exige `confirmed=true` et un `request_key` stable
(16 à 80 caractères lettres/chiffres/tiret/underscore), en plus du moteur, dataset,
époques, batch et taux d’apprentissage. La clé est unique par administrateur.
Répéter la même demande renvoie la même tâche ; changer ses paramètres renvoie 409.
Le frontend réutilise sa clé après une erreur réseau tant que le formulaire reste
monté. Après rechargement, consulter l’historique avant un nouveau lancement.

OVH fige les SHA-256 du dataset, du profil et l’ID du Pod avant transport. Une
intention de soumission est persistée avant tout envoi. Après réponse perdue,
le worker relit le même identifiant ou retransmet le même ZIP. Le gateway déduplique
et une annulation laisse une trace qui bloque même un premier envoi tardif.
Les interruptions réseau sont réessayées ; un état distant incohérent devient
`interrupted`. La révocation du consentement déclenche une demande d’annulation,
sans prétendre que le calcul est arrêté avant accusé de réception.

Les états non terminaux, y compris pause, interruption et demande d’annulation,
empêchent l’arrêt automatique et manuel du GPU. `/quiesce` refuse aussi tant que
le Pod connaît une tâche non terminée ou un téléversement en cours. Une panne ne
doit pas être résolue en effaçant des lignes SQL pour libérer cette protection.

Un seul calcul lourd peut utiliser le GPU via ce gateway. L’inférence est prioritaire :
elle demande une pause **à la fin de l’époque**, après checkpoint vérifié. Ce délai
peut être important ; ce n’est pas une préemption instantanée. Pendant la copie et
la libération du processus, l’analyse reste en attente sans épuiser ses tentatives
réseau. L’annulation est vérifiée à chaque itération et aux frontières du test ;
un appel framework bloqué peut donc retarder son accusé de réception. Ne pas annoncer
une annulation immédiate ni une garantie de délai sans recette sur les vrais modèles.

Après la fin des analyses, une pause pour inférence reprend automatiquement depuis
le checkpoint. Une interruption de service exige la commande administrative
`POST /runs/{id}/resume` avec `confirmed=true`. Sans checkpoint vérifié, annuler
l’ancienne demande puis en créer une nouvelle explicitement. Les tâches non encore
démarrées restent en file après redémarrage. Une tâche interrompue peut retenir la
file : l’opérateur doit décider de la reprendre ou l’annuler.

## Stockage, résultats et limites

- OVH : SQLite et ZIP dans `<DOEMO_RELEVES_DATA>/training-outbox`. Journaux d’actions
  et observations réelles dans `training_audit`, consultables via `/runs/{id}/logs`.
- Pod : `training/queue/<id>`, `training/jobs/<id>`, `training/logs/<id>` sous
  `/workspace/doemo-studio`. Manifestes de checkpoints et résultats avec SHA-256.
- Calculs temporaires, fichiers de commande et verrous POSIX dans `/tmp`. Aucune
  base SQLite, opération chmod ou renommage atomique n’est exigée sur le volume FUSE.
- Un résultat n’est `completed` qu’après événements valides, vérification des
  artefacts et code de sortie zéro. La progression vient des itérations du framework.
- Le registre permet d’enregistrer **un candidat** par tâche terminée, avec poids,
  configuration, classes et métriques du lot test. Ces métriques ne comparent pas
  encore le candidat à la production. Aucun modèle actif n’est remplacé.
- L’évaluation comparative, l’approbation, la publication et le rollback des poids
  restent indisponibles. Le réseau architectural
  reste à développer. Le [pilote LoRA Qwen](ENTRAINEMENT-QWEN.md) est raccordé
  et exige une recette GPU distincte. Le référentiel Qwen existant est distinct de ses poids.

## Validation locale de cette livraison

118 tests backend, 8 tests de géométrie, 6 parcours Playwright et build TypeScript
réussis. Les tests du
gateway emploient des sous-processus CPU et des artefacts de fixture explicitement
identifiés ; ils ne constituent pas une recette GPU. Ils vérifient déduplication,
perte de réponse, annulation concurrente, priorité, checkpoints, arrêt du processus,
intégrité des artefacts, révocation et refus d’activation en production.

## Ajout du moteur PaddleOCR

Le [pilote PaddleOCR](ENTRAINEMENT-PADDLEOCR.md) utilise la même file et un profil
indépendant. Cette livraison change le runtime partagé : les profils RTMDet
antérieurs doivent également être recettés à nouveau avant activation.
