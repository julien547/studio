# Entraînement PaddleOCR — reconnaissance de texte

Le pilote et son raccordement à la page `/entrainement`, au worker OVH et au gateway
sont développés. **Aucun entraînement Paddle réel ni déploiement n’a été effectué
par cette session.** La session de déploiement réalise seule l’audit et la recette
GPU décrits ci-dessous. L’installation des packages d’inférence ne suffit pas à
activer l’entraînement.

## Portée du pilote

Le pilote `services/runpod/paddle_pipeline.py` utilise les factories `ppocr` du
[dépôt officiel PaddleOCR v3.3.0](https://github.com/PaddlePaddle/PaddleOCR/tree/v3.3.0)
et PaddlePaddle 3 compilé CUDA. L’API de référence est
[`tools/train.py`](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.3.0/tools/train.py).
La compatibilité effective du YAML, des poids et du dictionnaire doit être vérifiée
par l’opérateur : ce code n’annonce pas la compatibilité de tous les modèles PaddleX.

- Reconnaissance `CRNN`, `SVTR` ou `SVTR_LCNet`, tête `CTCHead`/`CTCLoss` ou
  `MultiHead`/`MultiLoss` CTC+SAR ou CTC+NRTR, décodage `CTCLabelDecode`.
- `SimpleDataSet`, transformations explicites et dictionnaire UTF-8 local : un
  caractère Unicode par ligne. L’ordre doit être celui des poids d’origine.
- Poids d’entraînement locaux `.pdparams` : toutes les clés et dimensions doivent
  correspondre au modèle. Aucun chargement partiel ou agrandissement silencieux
  du vocabulaire. Un export d’inférence seul ne remplace pas ces poids.
- Boucle propre au pilote : un GPU, Adam, taux constant, sans AMP, 1–100 époques,
  batch 1–4, taux maximal 0,001. Les réglages d’optimiseur du YAML sont remplacés.
- Les modèles de détection de texte, distillation et formules ne sont pas pris en
  charge. Le détecteur de production n’est pas modifié.

Les datasets viennent de la page, avec consentement et annotations validées. Les
lots train/validation/test sont requis. Chaque caractère doit exister dans le
dictionnaire : `H₂O` n’est pas transformé en `H2O`. Une image identique dans deux
lots, une transcription omise ou modifiée par le lecteur provoque un échec explicite.
Une transcription occupe une ligne ; sa longueur doit respecter le YAML. Les
augmentations qui changent ou remplacent des labels doivent être retirées du profil.

Le pilote entraîne sur le lot train seulement. Après les époques prévues, il mesure
séparément validation et test, sans sélection automatique du meilleur checkpoint :
CER (erreurs de caractères), WER (erreurs de mots), proportion de textes exacts et
nombre d’échantillons. Aucun changement de casse ou normalisation Unicode ; le WER
utilise la séparation par espaces. Ces scores ne prouvent pas un gain par rapport
au modèle de production, qui n’est pas évalué par ce pilote.

## Fichiers à livrer ensemble

| Fichier | Fonction |
| --- | --- |
| `services/runpod/paddle_pipeline.py` | Calcul Paddle réel, checkpoints poids + optimiseur, évaluations |
| `services/runpod/paddle_training.py` | Contrôle du profil, des transcriptions et des métriques |
| `services/runpod/training_service.py`, `gateway.py`, `accept_training.py` | Admission par moteur, file commune et recette opérateur |
| `backend/doemo_releves/training_jobs.py` | File OVH, profil Paddle indépendant, vérification des résultats |
| `web/src/training/TrainingPage.tsx` | Parcours administratif existant raccordé à PaddleOCR |

Conserver les autres modules du gateway de **la même révision**. Aucune nouvelle
migration SQL : les migrations `003` à `005` existantes restent nécessaires selon
l’état du déploiement. Voir [PAGE-ENTRAINEMENT.md](PAGE-ENTRAINEMENT.md) pour le build
et [ENTRAINEMENT-RTMDET.md](ENTRAINEMENT-RTMDET.md) pour le worker OVH partagé.

**Cette livraison change l’empreinte du runtime partagé.** Les anciens profils
RTMDet sont donc également invalidés côté Pod : refaire leur recette avant de les
réactiver. Garder les profils OVH et Pod synchronisés. Un profil périmé affiché
côté OVH n’autorise pas l’exécution côté Pod.

## Préparation par la session de déploiement

1. Examiner l’état et les sauvegardes existantes. Ne pas remplacer les chemins,
   services ni secrets déjà configurés. Ne jamais supprimer le Pod ou son volume.
2. Préparer sous `/workspace/doemo-studio` un dépôt source PaddleOCR v3.3.0 audité,
   son YAML de reconnaissance, les poids d’entraînement compatibles et le dictionnaire
   original. Le pilote ne télécharge et n’installe rien.
3. Vérifier dans `/opt/doemo-ocr-venv/bin/python` PaddlePaddle 3 CUDA, NumPy, PyYAML,
   Pillow et les dépendances du dépôt correspondant au profil. Si le venv d’inférence
   diffère, organiser sa mise à jour/restauration avec la session de déploiement,
   puis retester l’inférence existante. Ne pas lancer un `pip install` global.
4. Exporter depuis DOEMO un petit dataset PaddleOCR autorisé avec trois groupes
   indépendants et des transcriptions couvertes par le dictionnaire. Un dataset de
   recette n’est pas une preuve de qualité sur vos plans réels.
5. Organiser une fenêtre de maintenance et autoriser le coût GPU. Le gateway doit
   être arrêté proprement par l’opérateur et aucun calcul tiers ne doit occuper le
   GPU. Le script refuse notamment un vLLM préexistant ; il ne l’arrête pas.

## Recette GPU explicite

Commande **à adapter et exécuter uniquement par la session de déploiement** depuis
le dossier privé `services/runpod` déployé. Les chemins ci-dessous sont des exemples,
non des fichiers dont la présence sur votre Pod aurait été vérifiée :

```sh
/chemin/venv-gateway/bin/python accept_training.py \
  --engine paddleocr \
  --dataset /workspace/doemo-studio/imports/ocr-recette.zip \
  --repository /workspace/doemo-studio/sources/PaddleOCR \
  --config /workspace/doemo-studio/config/ocr-recognition.yaml \
  --weights /workspace/doemo-studio/models/ocr-recognition.pdparams \
  --dictionary /workspace/doemo-studio/config/ocr-dictionary.txt \
  --profile-output /workspace/doemo-studio/config/paddle-training-profile-nouveau.json \
  --authorize-gpu-training --maintenance-confirmed
```

Le Python parent doit fournir les dépendances du gateway. L’enfant utilise le venv
OCR fixe cité plus haut. La recette demande une pause après l’époque 1, vérifie le
checkpoint, effectue une vraie inférence PaddleOCR, reprend l’époque 2 et vérifie
le résultat. Une seconde tâche vérifie l’annulation. Le rapport et le profil ne sont
produits qu’après succès complet. Un échec conserve les journaux et n’active rien.

Après succès, conserver `training/acceptance/<id>/report.json` puis installer le
**même profil JSON** dans un fichier privé sur OVH et sur le Pod. Définir dans les
environnements de l’API OVH, du worker d’entraînement et du gateway :

```dotenv
DOEMO_PADDLE_TRAINING_PROFILE=/chemin/prive/paddle-training-profile.json
```

Le profil RTMDet conserve sa variable distincte `DOEMO_TRAINING_PROFILE`. Le profil
Paddle lie les empreintes du pilote, du runtime, du YAML, des poids, du dictionnaire,
des sources Python `ppocr`/`tools` et du rapport de recette. Ne pas fabriquer les
indicateurs d’acceptation. Une modification nécessite une nouvelle recette.

Après la remise en service par l’opérateur, comparer les `profile_id` de
`engines.paddleocr` sur `/training/capabilities` du gateway et sur
`/projects/training/capabilities` d’OVH. Puis vérifier depuis la page : lancement
confirmé, progression, analyse prioritaire, reprise, annulation et résultat candidat.
L’API fournisseur et sa clé restent exclusivement sur OVH ; le navigateur ne reçoit
aucun secret RunPod.

## Pause, reprise, résultats

PaddleOCR et RTMDet partagent la même file et le même verrou de calcul avec les
inférences. Une pause attend la fin d’époque ; une annulation est examinée entre
les batches. Le délai dépend donc de la durée du batch/de l’époque. Les inférences
restent prioritaires selon le protocole existant. Pendant l’évaluation finale,
la pause est examinée entre les batches ; la reprise refait l’évaluation depuis
le dernier checkpoint sans recommencer les époques terminées. Aucun arrêt GPU n’est autorisé
par le contrôleur tant qu’une tâche non terminale existe.

À chaque époque, poids, état Adam et compteurs sont sauvegardés ensemble ; leurs
empreintes et leur rattachement à la tâche sont vérifiés avant reprise. Le pilote
reprend à l’époque suivante avec une graine déterminée par l’époque. Cela conserve
l’état d’apprentissage, sans promettre des résultats GPU bit à bit identiques.
Après panne, une reprise explicite est requise selon les règles de la file existante.

Les calculs et copies de reprise utilisent `/tmp`. Les checkpoints, résultats et
journaux durables restent sous `/workspace/doemo-studio/training`. Les résultats
comportent `weights.pdparams`, `training_config.yaml`, `dictionary.txt`, `metrics.json`
et `predictions.json`, avec un manifeste vérifié publié en dernier.

**Ces poids sont un candidat d’entraînement, pas un export de service.** Le YAML
conservé décrit le calcul effectué et contient des chemins temporaires. L’export
d’inférence, l’évaluation face à la production, l’approbation, l’activation et le
rollback restent à développer ; aucun modèle actif n’est remplacé par cette livraison.

## Vérifications locales

Tests CPU : Unicode exact, doublons entre lots, refus de profil détecteur,
compteurs CER/WER, checkpoint/reprise de l’optimiseur avec une fixture numérique,
annulation, intégrité, admission API et choix du pilote par le gateway. Le parcours
navigateur utilise un profil fictif dans une base temporaire, sans worker GPU,
puis vérifie conservation après redémarrage et annulation.

Ces tests ne chargent ni Paddle ni des poids réels et ne constituent pas une recette
GPU. Le bilan de la suite complète est dans [PAGE-ENTRAINEMENT.md](PAGE-ENTRAINEMENT.md).
