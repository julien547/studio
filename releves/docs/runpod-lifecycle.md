# Gestion automatique du GPU RunPod

Le Pod configuré est **`41m7oy6qjaj2ji`**, nommé **`DOEMO-STUDIO-IA`**.
Le module est développé localement ; il n’a pas été déployé sur OVH ni exécuté
contre ce Pod. La clé API réelle n’a pas été fournie à cet environnement.

## Architecture

Sur OVH, trois processus partagent le même stockage local `DOEMO_RELEVES_DATA` :
l’API, `python -m doemo_releves.queue` et `python -m doemo_releves.gpu`.
SQLite et le verrou POSIX restent sur OVH. Le dashboard lit un état en cache ;
l’éditeur, ses sauvegardes et ses exports restent utilisables lorsque RunPod est arrêté.
Le script de développement `scripts/standalone.sh` lance les trois processus.
En exploitation, les superviser séparément avec systemd et `Restart=on-failure`.

Le contrôleur utilise exclusivement l’API REST v2 officielle :

| Opération | Requête |
| --- | --- |
| Lire le Pod | `GET https://api.runpod.io/v2/pods/{id}` |
| Démarrer | `POST https://api.runpod.io/v2/pods/{id}/action`, `{"action":"start"}` |
| Arrêter | même route, `{"action":"stop"}` |

Authentification Bearer, permissions `pods:read` et `pods:write` adaptées au Pod.
Le client ne propose ni suppression, ni terminaison, ni recréation, ni modification
du volume réseau. Il vérifie le nom du Pod avant une commande.
Sources : [présentation v2](https://docs.runpod.io/api-reference-v2/overview),
[transition du Pod](https://docs.runpod.io/api-reference-v2/pods/trigger-a-pod-state-transition),
[migration v1/v2](https://docs.runpod.io/api-reference-v2/migrate-from-v1).
Contrat vérifié dans le dépôt officiel `runpod/docs`, commit
`3b219f9929f6054846e784e01801206c3ae18ac6`, `api-reference-v2/openapi.json`.

## 1. Stocker la clé sur OVH

Depuis le dépôt installé **sur le serveur OVH**, créer la configuration dans un
dossier privé hors du dépôt et hors de la racine web :

```sh
sudo python3 releves/scripts/configure-runpod.py --output-dir /etc/doemo-studio/runpod
```

Le terminal demande la clé en saisie masquée, crée deux fichiers en mode `0600`
et refuse d’écraser une configuration existante. Il n’envoie aucune requête RunPod.

- `runpod-ovh.env` contient la clé fournisseur : **reste exclusivement sur OVH**.
- `runpod-gateway.env` contient seulement un jeton d’inférence indépendant.
  Transférer ce jeton par le mécanisme privé de configuration du Pod.
  Ne jamais copier le fichier OVH sur RunPod, dans le frontend ou dans Git.

Ajouter `EnvironmentFile=/etc/doemo-studio/runpod/runpod-ovh.env` aux trois services
systemd OVH. Conserver leurs autres paramètres, notamment `DOEMO_RELEVES_DATA`.
Avec le gestionnaire systemd système, le fichier peut rester lisible uniquement
par root même lorsque les processus utilisent un utilisateur Unix dédié.
Ne pas placer la clé dans une commande shell, un fichier `VITE_*` ou le chat.

Le fichier commence avec `DOEMO_RUNPOD_MANAGED="0"`. Passer à `"1"` seulement après
la préparation du Pod ci-dessous, puis redémarrer les trois services OVH.
L’ID, le nom et le port HTTP 8000 sont déjà renseignés. Aucun endpoint manuel n’est
nécessaire : le proxy est `https://41m7oy6qjaj2ji-8000.proxy.runpod.net`.
`DOEMO_RUNPOD_ENDPOINT` peut le remplacer pour un accès HTTPS privé.
Le pare-feu OVH doit autoriser l’API RunPod et le proxy HTTPS du Pod.

## 2. Préparer le Pod une fois

Ces opérations exigent un accès au Pod existant et ses environnements déjà validés.
Monter le volume persistant à `/workspace` et copier `services/runpod/` dans
`/workspace/doemo-studio/services/runpod/`. Les modèles, archives de restauration,
entrées, résultats et journaux restent sur ce volume.

1. Exécuter `python3 check-existing.py` depuis ce dossier. Vérifier les environnements
   séparés `/opt/doemo-qwen-venv`, `/opt/doemo-ocr-venv`, `/opt/doemo-rtmdet-venv`.
   Ne pas remplacer les versions CUDA/ML fonctionnelles.
2. Créer `/opt/doemo-gateway-venv` seulement s’il est absent, avec `python3 -m venv`,
   puis installer `requirements.txt` dans ce quatrième environnement uniquement.
   Utiliser `/tmp` pour les caches et un Python de base fourni par l’image (`/usr`)
   ou sous `/opt`. La restauration refuse un interpréteur de base éphémère ailleurs.
3. Configurer le jeton `DOEMO_RUNPOD_TOKEN` et les chemins des modèles existants :
   `DOEMO_QWEN_MODEL`, `DOEMO_PADDLE_DETECTION_MODEL`,
   `DOEMO_PADDLE_RECOGNITION_MODEL`, `DOEMO_RTMDET_CONFIG`, `DOEMO_RTMDET_WEIGHTS`.
   Le code Qwen utilise par défaut `/workspace/doemo-studio/models/qwen/Qwen3.5-9B`.
   Les modèles doivent être locaux ; aucun téléchargement implicite n’est prévu.
4. Lancer chaque sonde avec son propre Python depuis le dossier des scripts :

   ```sh
   /opt/doemo-qwen-venv/bin/python readiness.py qwen
   /opt/doemo-ocr-venv/bin/python readiness.py paddleocr
   /opt/doemo-rtmdet-venv/bin/python readiness.py rtmdet
   ```

   Ces sondes effectuent une véritable inférence minimale. Leur compatibilité avec
   les paquets actuellement installés doit être vérifiée sur le Pod.
5. Définir `DOEMO_RUNTIME_IMAGE_TAG` avec une référence d’image immuable et conserver
   cette même valeur lors des redémarrages. Capturer les environnements validés :

   ```sh
   python3 environments.py snapshot /workspace/doemo-studio/restore/current
   ```

   Le dossier destination doit être neuf. Les archives peuvent être volumineuses ;
   prévoir la place correspondante sur le volume. Le manifeste contient les hashes
   SHA-256, versions Python et chemins de base. Il ne contient pas de clé RunPod.
6. Configurer dans le Pod le port **HTTP 8000** et la commande de démarrage :

   ```sh
   python3 /workspace/doemo-studio/services/runpod/bootstrap.py
   ```

   Conserver les variables du jeton et des modèles dans la configuration du Pod.
   L’image doit fournir Python et les bibliothèques système/CUDA compatibles.
   Le bootstrap restaure uniquement les environnements absents dans `/opt`.
   Un environnement existant incomplet déclenche une erreur explicite, sans écrasement.
   Le gateway utilise exactement **un worker** et un verrou local de processus.

Au démarrage, les trois sondes sont relancées. Une présence de fichiers ou une
réponse HTTP seule ne suffit pas à afficher « GPU prêt ». Si la restauration échoue
avant le lancement du gateway, le dashboard affiche une connexion indisponible ;
le motif technique reste dans `/workspace/doemo-studio/logs/bootstrap-*.json`.

## Fonctionnement et reprise

Les administrateurs disposent des boutons **Démarrer le GPU**, **Arrêter le GPU**
et du journal. Les autres utilisateurs voient l’état et les trois moteurs.
Un travail GPU en attente provoque le démarrage automatique ; le worker attend
un contrôle récent des trois moteurs avant de transmettre l’image.

Le verrou OVH sérialise admission des travaux, prise en charge et commandes de Pod.
L’intention de démarrage est enregistrée avant l’appel fournisseur. Après une réponse
incertaine, un nouveau contrôleur relit le Pod avant toute nouvelle tentative.
Les erreurs fournisseur et les indisponibilités de capacité produisent des tentatives
espacées, avec respect de `Retry-After`, sans créer de Pod de remplacement.

L’arrêt automatique nécessite **30 minutes d’inactivité côté OVH et côté gateway**,
un état frais, aucune tâche en cours ou en attente, puis une confirmation `/quiesce`
qui bloque toute nouvelle inférence. La lecture du dashboard ne remet pas ce compteur
à zéro. L’arrêt manuel n’attend pas 30 minutes mais conserve les protections contre
les tâches actives ou en attente. Un gateway inaccessible ne permet pas de prouver
l’inactivité : l’arrêt est refusé et le GPU peut donc rester facturé jusqu’au diagnostic.

Les entrées et résultats résident dans `/workspace/doemo-studio/jobs/{id}/`.
Une reprise avec le même identifiant et la même image récupère le résultat terminé
sans refaire l’inférence. Après interruption, les travaux GPU sont repris après
expiration du bail OVH (650 secondes). Les erreurs d’inférence transitoires sont
retentées jusqu’à cinq fois, puis signalées comme échec à relancer manuellement.
Une attente de capacité ne consomme pas ces tentatives. Les tâches CPU interrompues
nécessitent une relance explicite. Les sorties IA restent séparées des corrections
humaines tant qu’elles n’ont pas été ajoutées à la revue.

Un changement de `DOEMO_RUNPOD_POD_ID` impose un nouveau contrôle du Pod : aucun état
« prêt » ni commande en attente de l’ancien Pod n’est transféré. Redémarrer ensemble
API, worker et contrôleur avec la même configuration, après la fin des analyses.
Le contrôleur ne commande plus l’ancien Pod ; un ancien GPU encore allumé reste à
gérer séparément dans RunPod.

Journal OVH : table SQLite `gpu_events`, visible pour les administrateurs.
Journaux Pod : `/workspace/doemo-studio/logs/` et journaux des travaux persistants.
Les erreurs affichées n’incluent pas les réponses fournisseur brutes ou les secrets.
Arrêter le service contrôleur ou désactiver `MANAGED` ne termine ni ne supprime le Pod.

## Vérifications avant mise en service

Les tests locaux simulent RunPod et les moteurs : droits administrateur, contrat REST
v2, absence de secret dans les réponses, démarrages concurrents, actions incertaines,
attente des trois moteurs, changement d’ID, inactivité, refus d’arrêt en présence de
travaux, quiescence, reprise de résultat et restauration d’archives.
Ils ne valident pas la capacité GPU réelle ni les versions CUDA du Pod.

Vérification locale du 28 octobre 2026 : **80 tests backend réussis**, dont 24 cas
du module GPU ; **8 tests JavaScript réussis**, compilation TypeScript/Vite réussie,
et parcours navigateur Playwright réussi avec le nouveau panneau GPU. Le parcours
vérifie notamment l’identifiant, les commandes désactivées sans configuration et
la sauvegarde/export des relevés sans GPU.

Sur le Pod réel, vérifier successivement les sondes, une analyse de chaque moteur,
la persistance des résultats après arrêt/démarrage et la restauration après perte
du disque conteneur. Vérifier que l’éditeur OVH reste accessible pendant ces étapes.
Ne pas activer l’arrêt automatique avant d’avoir capturé et validé les environnements.
