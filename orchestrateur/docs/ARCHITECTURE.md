# Orchestrateur IA central DOEMO — architecture et état d'avancement

Rédigé le 28/10/2026. Répond au cahier des charges « Architecture IA multi-applications,
multi-utilisateurs et apprentissage centralisé ».

## 1. État des lieux avant ce chantier (lu dans les branches `codex/*` et `feat/redessin-ovh-tests`)

| Constat | Conséquence |
|---|---|
| La passerelle RunPod (`releves/services/runpod/gateway.py`) prend un verrou `asyncio.Lock` et **répond 409 « GPU occupé »** à toute 2ᵉ requête. | Une seule tâche à la fois, sur tout le GPU. |
| Qwen tourne avec `transformers` et **se recharge à chaque requête** (sous-processus). Pas de vLLM. | Lent, aucun traitement simultané. |
| **Trois files de tâches séparées** : Relevé (SQLite), Redessin (`ai_service/worker.py`), Entraînement IA (`training.py`). | Aucune priorité commune, aucune équité, risque que deux applications se bloquent. |
| Pas de registre de modèles commun, pas de mémoire partagée. | Chaque application réapprend de son côté. |

## 2. Architecture cible

```
 Relevé   Redessin   Entraînement IA   (autres applications)
    \        |            |            /
     └───────┴─── API centrale HTTPS ──┘      jeton par application
                  (orchestrateur, OVH)
        file persistante · priorités · équité · plafonds · registre de modèles · statistiques
                        │  jeton par worker (réclamation par HTTPS, jamais d'accès à la base)
        ┌───────────────┼────────────────────┐
     worker GPU 1    worker GPU 2        worker d'entraînement (à la demande)
   Qwen (vLLM)     OCR · RTMDet · Murs
```

* **Les applications n'appellent jamais les environnements Python des modèles** : uniquement l'API centrale.
* **Les workers viennent chercher le travail** (réclamation avec bail de 120 s, renouvelé par
  signal de présence). Ajouter un GPU = lancer un worker de plus avec son jeton ; rien à
  reconfigurer côté applications.
* **Un seul processus accède à la base** (l'orchestrateur). Les workers, même distants, passent par l'API.

### Choix de la base : SQLite (WAL) maintenant, PostgreSQL plus tard si besoin

Le cahier des charges suggère PostgreSQL + Redis/RQ « ou équivalent adapté à la stack
existante ». Le serveur OVH n'a ni l'un ni l'autre (MariaDB seulement) et la stack Relevé est
déjà en SQLite. Comme l'orchestrateur est le **seul** client de la base, une base SQLite en
mode WAL suffit largement pour des dizaines de dessinateurs (quelques tâches par seconde au
plus) et évite d'installer et d'exploiter deux services de plus en production. Le schéma
n'emploie que du SQL standard ; passer à PostgreSQL ne demande que de remplacer `db.py`.
**Point à confirmer** (§8).

## 3. Livré dans cette première étape (code + 23 tests, non déployé)

Dossier `orchestrateur/` : `db.py`, `scheduler.py`, `service.py`, `registry.py`, `api.py`.

* **Identification de chaque tâche** : application, utilisateur, projet, moteur (`qwen`, `paddleocr`,
  `rtmdet`, `murs`), type, priorité, version du modèle, état, avancement, étape.
* **Trois classes** : `interactive` (dessinateur qui attend), `batch`, `training`.
* **Ordonnancement** : `score = base(classe) + 5×priorité + âge×vieillissement − pénalité d'équité`.
  Les analyses interactives passent d'abord ; un lot qui attend depuis ~5 min passe devant une
  demande interactive neuve (pas de famine). La pénalité réduit la part d'une application ou
  d'un utilisateur qui occupe déjà des emplacements et du temps de calcul récent.
* **Plafond dur par application** (`max_running`) : une application ne peut pas accaparer le GPU.
* **Protection contre la surcharge** : 500 tâches en attente par application, 100 par utilisateur (HTTP 429).
* **Doublons** : une clé `dedupe_key` renvoie la tâche active existante au lieu d'en créer une autre.
* **Annulation** (immédiate en file ; signalée au worker si en cours), **relance** manuelle,
  **reprise automatique** avec délai croissant si un worker disparaît ou échoue, puis échec définitif.
* **Isolation** : une application ne voit ni n'annule les tâches d'une autre ; un worker ne peut
  clore que ses propres tâches ; jetons stockés sous forme d'empreinte SHA-256.
* **Registre de modèles** : version candidate (SHA-256 obligatoire, chemin relatif) → approbation
  explicite → sélection par application → retour arrière à la version précédente ; une version
  utilisée ne peut pas être retirée. Chaque tâche embarque la version approuvée de son application.
* **Statistiques d'administration** (`/v1/admin/overview`) : applications, utilisateurs actifs, en
  cours / en attente, délais d'attente et de traitement moyens, workers (VRAM, modèles chargés),
  répartition par moteur / application / utilisateur / type, erreurs. `gpu_cost_usd` est vide pour l'instant.
* **Test de concurrence** : 8 workers se disputent 40 tâches sur une vraie base ; aucune n'est attribuée deux fois.

## 4. Contrats pour les autres sessions (extraits)

Application : `POST /v1/tasks` `{user, engine, kind, project, priority, payload, dedupe_key}` →
`GET /v1/tasks/{id}` (état, `queue_position`, résultat) · `POST …/cancel` · `POST …/retry` ·
`GET /v1/models`. Worker : `POST /v1/worker/claim|heartbeat`, `…/tasks/{id}/progress|complete|fail`.
Administration : `/v1/admin/overview|apps|workers|models`. Les payloads portent des **références
de fichiers** (256 Ko max), jamais les images elles-mêmes.

* **Relevé** : remplacer `queue.py` (appel direct de la passerelle) par `POST /v1/tasks`.
* **Redessin** : idem pour `ai_service/worker.py`, moteur `murs`.
* **Entraînement IA** : publie ses versions via `POST /v1/admin/models` ; la validation passe par `approve`.

## 5. Mémoire commune (conception, à réaliser)

Trois niveaux, stockés par l'orchestrateur et servis par API, **jamais par accès direct aux dossiers** :
**globale DOEMO** (abréviations, règles de lecture, conventions, catégories — écriture après
validation et droit « admin »), **par application** (instructions, paramètres, exemples non partagés)
et **projets clients** (restent dans l'application d'origine ; l'orchestrateur ne reçoit que des
références). Une correction n'entre dans le jeu de données commun qu'avec : application d'origine,
projet, type d'annotation, modèle d'origine, auteur, date, statut de validation et autorisation de réutilisation.
Jeux de données **distincts** par moteur (Qwen, PaddleOCR, RTMDet, Murs), formats non mélangés.

## 6. Ce qui reste à faire (dans cet ordre)

| # | Étape | Besoin d'accord / coût |
|---|---|---|
| 2 | **Agent worker** (boucle de réclamation, présence, annulation) et installation de l'orchestrateur sur OVH (service systemd, en HTTPS local derrière Apache) | Déploiement en production : **votre accord** |
| 3 | **Qwen avec vLLM** : mesurer VRAM, longueur de contexte, limites d'images, batching continu, nombre de requêtes actives | **Démarrer le pod RunPod (≈0,59 $/h)** : votre accord |
| 4 | Services **OCR** et **RTMDet** concurrents ; politique de chargement/réservation VRAM (ne pas supposer que les 4 modèles tiennent ensemble) | Pod allumé |
| 5 | Branchement de Relevé, Redessin, Entraînement IA (3 sessions) | Coordination des sessions |
| 6 | Mémoire commune + jeux de données par moteur + pipeline d'entraînement versionné/évalué | — |
| 7 | **Benchmarks** : 1, 3, 5, 10 dessinateurs, plusieurs applications, vrais PDF ; attente, latence, débit, VRAM, erreurs, coût par tâche | Pod allumé |
| 8 | Étude RunPod Pods vs Serverless et recommandation du nombre de GPU **d'après les mesures** | Aucun serveur payant créé sans politique budgétaire approuvée |
| 9 | Tableau de bord dans studio.doemo.fr (API déjà prête) | Déploiement |
| 10 | LoRA multiples avec vLLM : compatibilité réelle avec Qwen3.5-9B à vérifier avant toute promesse | Pod allumé |

## 7. Ce qui n'est PAS fait (à ne pas annoncer)

vLLM, workers OCR/RTMDet/Murs, routage multi-GPU en conditions réelles, mémoire commune,
pipeline d'entraînement, tableau de bord visuel, benchmarks, étude de coûts RunPod. **Aucune capacité
(nombre de dessinateurs, nombre de GPU) n'est annoncée : elle viendra des mesures de l'étape 7.**

## 8. Décisions demandées à Julien

1. SQLite pour démarrer (recommandé) ou PostgreSQL + Redis dès maintenant (deux services de plus à installer sur OVH) ?
2. Autorisation de **démarrer le pod RunPod** pour les mesures (étapes 3, 4, 7, 10), avec un plafond de dépense.
3. Politique budgétaire pour un éventuel 2ᵉ GPU (montant mensuel maximal, validation manuelle ou automatique).
