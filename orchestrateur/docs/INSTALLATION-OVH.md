# Installation de l'orchestrateur sur OVH (28/10/2026)

Service **interne** : il écoute sur `127.0.0.1:8765` uniquement. Rien n'est exposé sur Internet,
aucun fichier Apache n'a été modifié, aucune application existante n'est touchée.

| Élément | Emplacement |
|---|---|
| Code (root, lecture seule) | `/opt/doemo-orchestrateur/src` |
| Environnement Python isolé | `/opt/doemo-orchestrateur/venv` (FastAPI 0.115, uvicorn 0.32) |
| Base SQLite (WAL) | `/var/lib/doemo-studio/orchestrateur/orch.db` (propriétaire `doemo-orch`, 0750) |
| Configuration + jeton d'administration | `/etc/doemo-studio/orchestrateur.env` (`root:doemo-orch`, 0640) |
| Service | `doemo-orchestrateur.service` (utilisateur système `doemo-orch`, sans shell) |

Le service est durci : `NoNewPrivileges`, système de fichiers en lecture seule sauf le dossier de
la base, pas d'accès à `/home`, `/tmp` privé. Le jeton d'administration a été **généré sur le
serveur** ; il n'apparaît ni dans le dépôt ni dans une conversation.

## Exploitation

```sh
sudo systemctl status doemo-orchestrateur
sudo journalctl -u doemo-orchestrateur -n 50 --no-pager
sudo systemctl restart doemo-orchestrateur
```

Lire la vue d'ensemble (depuis le serveur, sans afficher le jeton) :

```sh
sudo sh -c 'set -a; . /etc/doemo-studio/orchestrateur.env; curl -s -H "Authorization: Bearer $DOEMO_ORCH_ADMIN_TOKEN" http://127.0.0.1:8765/v1/admin/overview'
```

Créer une application ou un worker : `POST /v1/admin/apps` et `/v1/admin/workers`. **Le jeton
retourné n'est affiché qu'une fois** ; le déposer dans un fichier `root:` à droits restreints
de l'application concernée, jamais dans Git.

## Mise à jour

Copier le dossier `orchestrateur/` du dépôt vers `/opt/doemo-orchestrateur/src`, lancer les tests
(`sudo -u doemo-orch … pytest`), puis `pip install --no-deps /opt/doemo-orchestrateur/src` et
redémarrer le service. Sauvegarder d'abord `orch.db` dans `/var/backups/doemo-studio/`.

## Retour arrière complet

```sh
sudo systemctl disable --now doemo-orchestrateur
sudo rm /etc/systemd/system/doemo-orchestrateur.service && sudo systemctl daemon-reload
# la base et la configuration peuvent être conservées ou supprimées :
# /var/lib/doemo-studio/orchestrateur  /etc/doemo-studio/orchestrateur.env  /opt/doemo-orchestrateur
```

## Reste à décider : comment les workers GPU (RunPod) joindront l'orchestrateur

Un worker sur RunPod ne peut pas atteindre `127.0.0.1`. Avant de brancher un GPU, il faudra choisir
une voie sécurisée : (a) un chemin HTTPS dédié derrière Apache, limité aux routes `/v1/worker/*` et
protégé par le jeton de worker, ou (b) un tunnel SSH sortant depuis le pod vers OVH. À trancher
avec Julien au moment du démarrage du pod.
