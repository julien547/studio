# Entraînement Qwen3.5-9B — adaptateur LoRA

Le pilote LoRA est raccordé à la file OVH/gateway et à la carte **Qwen3.5-9B** de
`/entrainement`. L’espace **IA architecturale** reste distinct et ne devient pas un
réseau de redessin de murs avec cette livraison. Le référentiel de conventions et
ses comparaisons Qwen restent disponibles indépendamment du fine-tuning.

**Aucun poids réel, calcul GPU ou déploiement n’a été exécuté par cette session.**
La recette ci-dessous est réservée à la session de déploiement, pendant une fenêtre
autorisée. Sans profil accepté, le bouton d’entraînement demeure indisponible.

## Pilote et contrat

- `services/runpod/qwen_training.py` : boucle réelle PyTorch/Transformers/PEFT,
  LoRA sur les projections `q_proj`, `k_proj`, `v_proj`, `o_proj` du langage.
  Les projections présentes sont sélectionnées dans `language_model`, jamais
  dans la vision. Les blocs linéaires GatedDeltaNet ne sont pas adaptés ici.
- `services/runpod/qwen_training_data.py` : validation du dataset, empreintes des
  fichiers locaux, configuration, prompt supervisé et masque assistant. Ce prompt
  est **distinct** de `qwen_prompt.py`, utilisé pour l’inférence de production.
- `training_service.py`, `gateway.py`, `accept_training.py` : moteur `qwen`, profil
  indépendant, interpréteur fixe `/opt/doemo-qwen-venv/bin/python` et recette.
- `backend/doemo_releves/training_jobs.py` : capacité, paramètres, file, reprise et
  validation des artefacts. Les tables existantes couvrent déjà Qwen : pas de
  nouvelle migration SQL.
- `web/src/training/TrainingPage.tsx` : lancement Qwen, suivi, limites affichées,
  annulation et distinction entre référentiel et adaptateur entraîné.

Charger un modèle **dense Qwen3.5-9B non quantifié** via
`AutoModelForImageTextToText`, avec son processor local. Seuls les paramètres LoRA
sont entraînables ; les poids de base et la vision restent figés. Le pilote refuse
les modèles quantifiés et ne fournit pas de QLoRA dans cette version.

Choix mémoire : BF16, un GPU, batch **1**, gradient checkpointing, attention eager,
pas de cache KV, rang 1–32, alpha 1–64, taux maximal **0,0002**, 1–100 époques.
Le rang 8, 2 048 tokens et 65 536 pixels constituent un point de départ prudent,
**pas une preuve de tenue dans les 48 Go de l’A6000**. La recette vérifie la VRAM
et les versions réellement installées. Un manque de mémoire échoue sans promotion.

Le modèle et le processor utilisent `local_files_only=True`,
`trust_remote_code=False` et le mode hors ligne HF. Aucun package, modèle ou
configuration n’est téléchargé par le pilote. Le dépôt complet doit être local,
avec `config.json`, tokenizer, processor, chat template, index éventuel et fragments
`.safetensors`. Matérialiser les fichiers : les liens symboliques sont refusés.

API officielle consultée pour les projections et le forward multimodal :
[Transformers Qwen3.5](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen3_5/modeling_qwen3_5.py).
Cette lecture de code ne remplace pas une recette du paquet installé. Les versions
exactes de `torch`, `transformers`, `peft` et `safetensors` sont fixées dans le profil
et vérifiées avant de charger le modèle.

## Dataset et évaluation

Utiliser l’export ZIP Qwen existant de DOEMO, avec consentement et exemples validés :
`examples.json`, `qwen.jsonl` et les images PNG. Les trois lots train/validation/test
indépendants sont obligatoires. Le serveur OVH conserve la séparation par groupes
bâtiment/document ; le pilote refuse aussi une même image dans plusieurs lots.

Chaque ligne contient une image, le split et une paire `user`/`assistant` : la
convention et son interprétation corrigée. Le modèle reçoit l’image et la convention ;
la perte porte **seulement sur la réponse assistant**. Les tokens système, utilisateur
et image sont masqués. Le pilote vérifie que le template conserve exactement le
préfixe et refuse une troncature silencieuse. Si un exemple dépasse la limite,
réduire sa taille ou adapter le profil et refaire la recette.

Les validations et tests utilisent une **perte supervisée sur les tokens assistant**,
pondérée par le nombre de tokens : `validation_assistant_loss`,
`test_assistant_loss`, nombres de tokens et d’exemples. Il n’y a pas de génération
automatique, de score inventé, de sélection du meilleur checkpoint sur le lot test,
ni de comparaison à la production. Une baisse de cette perte ne prouve pas une
amélioration de la lecture des plans ou de la précision des positions.

## Préparer la recette — session de déploiement uniquement

1. Examiner la révision et les sauvegardes existantes ; préserver les chemins,
   données et services privés. Livrer tous les modules du gateway de la même
   révision, ainsi que le backend et le build frontend (`npm ci && npm run build`).
2. Vérifier le modèle dense 9B et le venv Qwen existants. Ne pas installer des
   dépendances globales ni remplacer vLLM pendant cette livraison de développement.
   La session de déploiement organise les éventuelles adaptations du venv et leurs
   sauvegardes, puis vérifie que l’inférence existante fonctionne toujours.
3. Créer une configuration JSON privée sous `/workspace/doemo-studio/config`.
   Exemple à compléter avec les **versions exactes constatées** ; les valeurs
   `REMPLACER` font volontairement échouer le pilote :

   ```json
   {
     "schema": "doemo.qwen-lora/1",
     "rank": 8,
     "alpha": 16,
     "max_tokens": 2048,
     "max_pixels": 65536,
     "runtime_versions": {
       "torch": "REMPLACER",
       "transformers": "REMPLACER",
       "peft": "REMPLACER",
       "safetensors": "REMPLACER"
     }
   }
   ```

4. Exporter un petit dataset Qwen autorisé, avec trois lots, idéalement plusieurs
   exemples train. Organiser une maintenance et autoriser le coût GPU. Le gateway
   doit être arrêté proprement par l’opérateur et aucun calcul tiers ne doit occuper
   la carte. Le contrôle refuse un vLLM préexistant ; il ne l’arrête jamais.
5. Depuis `services/runpod`, exécuter la recette avec le Python du gateway. Les
   chemins ci-dessous sont des exemples à adapter, non vérifiés sur votre serveur :

   ```sh
   /chemin/venv-gateway/bin/python accept_training.py \
     --engine qwen \
     --dataset /workspace/doemo-studio/imports/qwen-recette.zip \
     --config /workspace/doemo-studio/config/qwen-lora.json \
     --weights /workspace/doemo-studio/models/qwen/Qwen3.5-9B \
     --profile-output /workspace/doemo-studio/config/qwen-training-profile-nouveau.json \
     --timeout 3600 \
     --authorize-gpu-training --maintenance-confirmed
   ```

Pour Qwen, `--weights` désigne le **répertoire complet** du modèle, pas un fragment.
La recette attend un vrai premier batch avant de demander la pause, vérifie un
checkpoint avant la fin du calcul, exécute une vraie inférence PaddleOCR de contrôle,
reprend jusqu’à deux époques et vérifie le résultat. Une autre tâche teste l’annulation.
Un échec ne crée aucun profil accepté. Conserver les logs pour diagnostic.

Après succès, conserver `training/acceptance/<id>/report.json`, puis installer le
même profil JSON privé sur OVH et sur le Pod. Définir dans les environnements du
backend, du worker d’entraînement OVH et du gateway :

```dotenv
DOEMO_QWEN_TRAINING_PROFILE=/chemin/prive/qwen-training-profile.json
```

Le profil lie les empreintes du pilote, du runtime, de la configuration LoRA, de
**tous les fichiers du modèle de base** et du rapport. Il s’agit d’empreintes SHA-256
et d’un fichier administrateur de confiance, **pas d’une signature cryptographique**.
Ne pas le fabriquer en positionnant les indicateurs d’acceptation à `true`.

**Le runtime partagé change avec cette livraison : les anciens profils RTMDet et
PaddleOCR sont également invalidés côté Pod.** Les recetter à nouveau avant activation,
puis synchroniser les profils OVH/Pod. Le calcul des empreintes du modèle 9B peut
prendre du temps au démarrage et avant une tâche ; aucun hash factice n’est utilisé.

Après remise en service par l’opérateur, comparer les `profile_id` de
`engines.qwen` sur `/training/capabilities` et `/projects/training/capabilities`.
Vérifier ensuite le parcours de bout en bout depuis la vraie page : lancement,
progression, demande d’analyse prioritaire, reprise, annulation et candidat.

## Reprise et conservation

La file, les verrous de calcul, l’idempotence et la protection contre l’arrêt GPU
sont ceux de RTMDet/PaddleOCR. Une tâche en attente ou non terminale interdit l’arrêt.
La pause est examinée entre les batches ; le batch en cours et la copie du checkpoint
doivent se terminer. L’initialisation du modèle doit aussi se terminer avant que
le processus puisse libérer proprement ses ressources.

Les checkpoints contiennent adaptateur safetensors, configuration PEFT, état AdamW,
curseur exact du prochain exemple et configuration de formation. Ils sont enregistrés
à chaque fin d’époque et à la demande de pause. La reprise vérifie la tâche, le
profil, le dataset, les paramètres et toutes les empreintes. L’ordre des exemples
et les graines sont déterminés par époque/itération ; cela ne garantit pas une
identité bit à bit entre deux exécutions CUDA. Après panne, la reprise repart du
dernier checkpoint durable et demande une action explicite selon la file existante.

Calculs et copies de reprise dans `/tmp`, données/checkpoints/résultats/logs durables
sous `/workspace/doemo-studio/training`. Aucun verrou, renommage atomique ni SQLite
sur le volume réseau. Résultat final : `adapter_model.safetensors`,
`adapter_config.json`, `training_config.json`, `metrics.json` et manifeste vérifié.
Les poids de base ne sont ni fusionnés ni remplacés.

Le registre peut conserver cet **adaptateur candidat**. L’évaluation comparative
sur des réponses générées, l’approbation, le branchement de l’adaptateur dans les
inférences, la publication et le rollback restent désactivés. Un avis favorable
sur un référentiel Qwen n’active pas un adaptateur LoRA.

## Tests locaux

Tests CPU du contrat multimodal/masque assistant, séparation des lots, empreintes,
refus de profil non recetté, admission, limites mémoire, choix du pilote, pause à
l’intérieur d’une époque, restauration de l’optimiseur, annulation et intégrité.
Les sessions numériques sont des fixtures explicites, sans import Torch/PEFT.
Le navigateur vérifie la carte Qwen, ses limites, la demande persistante et son
annulation, ainsi que l’indisponibilité distincte de l’IA architecturale.
Aucun de ces tests ne charge les poids réels ni ne démontre la qualité du modèle.
