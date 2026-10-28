# Installer la connexion de Studio aux trois IA RunPod

Livraison **0.3.3**, dépôt privé `julien547/studio`, branche
`feat/redessin-ovh-tests`, [PR 1](https://github.com/julien547/studio/pull/1).
Cette procédure est destinée à la session disposant des accès OVH et RunPod.
Le code est publié ; **la connexion sur vos serveurs doit encore être installée
et vérifiée avec les inférences réelles**.

## Préserver la production

Lire d’abord [AVERTISSEMENT-MODIFICATIONS-STUDIO.md](AVERTISSEMENT-MODIFICATIONS-STUDIO.md).
Cette livraison met à jour uniquement `/redessin/`, `api/redessin.php` et le service
privé du redessin. Elle ne reconstruit pas `/app/` et ne déploie rien dans `/releves/`.

- Conserver le menu actuel et `StructureBatiment.jsx` / `FramedApp.jsx` de
  `doemo-app`, branche **`feat/studio-host`**. Le redessin reste dans l’iframe sous le menu.
- Ne pas déployer l’ancienne branche `feat/redessin-ovh-navigation` / PR doemo-app 2.
- Aucun bandeau `<header>` dans `redessin/index.php` ni dans l’éditeur intégré.
- Conserver les règles Apache de production : `SAMEORIGIN` et `frame-ancestors 'self'`
  sur `/redessin/` uniquement ; conserver les restrictions du reste du site.
- Les sauvegardes de cette installation vont sous `/var/backups/doemo-studio/`,
  jamais sous le DocumentRoot.

## Ce que cette livraison raccorde

```text
Studio, sous son menu actuel
  → API PHP de session sur OVH
  → service doemo-redessin sur socket Unix privé
  → tunnel privé ou HTTPS + signature Ed25519
  → worker RunPod
  → PaddleOCR, Qwen3.5-9B et RTMDet, chacun dans son environnement existant
```

L’application vérifie la disponibilité des trois moteurs à l’ouverture. Le bouton
**Analyser la page avec les trois IA** envoie la page au worker, suit la tâche puis
enregistre les résultats. Les textes OCR et les zones commentées apparaissent dans
l’éditeur. Les murs corrigés sont conservés. Le compteur RTMDet reste un diagnostic
d’objets génériques : il ne produit ni murs ni équipements incendie validés.

## 1. Préparer la version sur OVH

Récupérer la branche dans un checkout dédié, sans écraser les modifications d’une
autre session. Pour une première copie :

```bash
git clone --branch feat/redessin-ovh-tests --single-branch https://github.com/julien547/studio.git /opt/doemo-redessin-source
cd /opt/doemo-redessin-source
git rev-parse HEAD
python3 reconstruction/ovh/build_web.py
```

Si ce checkout existe déjà, contrôler `git status --short`, puis actualiser avec
`git pull --ff-only` seulement s’il est propre et sur cette branche. Noter le SHA.

Relever le vrai DocumentRoot. Attendre la fin des tâches ; réconcilier toute tâche
interrompue avant de stopper le seul service `doemo-redessin`. Si le DocumentRoot
confirmé est `/var/www/studio`, préparer la version :

```bash
sudo bash reconstruction/ovh/install-release.sh /opt/doemo-redessin-source /var/www/studio
```

Le script sauvegarde les fichiers concernés, crée le compte de service et le venv
OVH, puis installe l’unité systemd. Il n’active pas le service, ne touche pas au menu,
ne réinstalle aucune IA et refuse une source contenant l’ancien bandeau.
Pour une première installation, suivre aussi les prérequis PHP/Apache de
[DEPLOIEMENT_OVH.md](reconstruction/ovh/DEPLOIEMENT_OVH.md). Ne pas remplacer la
configuration Apache de cadrage déjà présente en production.

## 2. Préparer la clé et l’adresse privée sur OVH

Le transport privé doit exposer le worker RunPod. L’exemple ci-dessous utilise
**le port local 8009** ; utiliser le port réel si le transport existant est différent.
Une URL HTTPS privée peut remplacer cette URL, avec vérification TLS active.

```bash
sudo /opt/doemo-redessin/venv/bin/python \
  /opt/doemo-redessin/current/ovh/configure-runpod.py \
  --url http://127.0.0.1:8009 --generate-key
```

Cette commande prépare `/etc/doemo-redessin/service.env`, crée la paire dédiée si
elle est absente et conserve une paire existante. Elle ne montre jamais la clé
privée, ne fait pas de rotation implicite et ne redémarre aucun service. Les autres
paramètres du fichier sont conservés. Une clé publique existante sans sa clé privée
provoque un arrêt : retrouver la paire avant de continuer.

Pour une paire de service déjà gérée, utiliser `--private-key CHEMIN_REEL` à la place
de `--generate-key`. Le fichier privé doit appartenir à `doemo-redessin`, être lisible
uniquement par ce compte, et être accessible dans le confinement systemd ; préférer
`/etc/doemo-redessin/`, pas un répertoire personnel. Ne pas utiliser la clé SSH.

Transférer **uniquement** `/etc/doemo-redessin/worker-signing-public.pem` vers
`/workspace/doemo-studio/config/ovh-worker-public.pem` sur RunPod par le canal privé
existant. Ne pas écraser une clé différente sans réconcilier la configuration.
Comparer les SHA-256 du fichier public des deux côtés. La clé privée reste sur OVH.

## 3. Intégrer le worker à l’image RunPod existante

À faire par la session responsable de l’image privée versionnée. Vérifier l’image
réelle actuellement utilisée et les trois venvs restaurés avant la construction :

- `/opt/doemo-qwen-venv/bin/python` ;
- `/opt/doemo-ocr-venv/bin/python` ;
- `/opt/doemo-rtmdet-venv/bin/python`.

Conserver ces environnements dans l’image et les modèles sur `/workspace`. Ne pas
repartir de l’ancienne image PyTorch publique en supposant qu’elle contient les IA.
Ne pas installer les venvs sur FUSE et ne pas restaurer les moteurs au démarrage normal.

Ajouter le code `reconstruction/doemo_reconstruction/` et `reconstruction/runpod/`
sous `/opt/doemo-inference-test/`. Installer les seules dépendances légères du worker
dans `/opt/doemo-service-venv`, lors de la construction. Exemple de fragments à
intégrer au Dockerfile existant, avec le dépôt comme contexte :

```dockerfile
RUN test -x /opt/doemo-qwen-venv/bin/python \
 && test -x /opt/doemo-ocr-venv/bin/python \
 && test -x /opt/doemo-rtmdet-venv/bin/python
COPY reconstruction/doemo_reconstruction /opt/doemo-inference-test/doemo_reconstruction
COPY reconstruction/runpod /opt/doemo-inference-test/runpod
RUN python3 -m venv /opt/doemo-service-venv \
 && /opt/doemo-service-venv/bin/pip install -r /opt/doemo-inference-test/runpod/requirements-test-service.txt
```

Conserver le verrou des dépendances et le registre privé gérés par la session image.
Intégrer [supervisor-doemo-ai.conf](reconstruction/runpod/supervisor-doemo-ai.conf)
au superviseur **déjà utilisé par cette image**. S’il utilise un autre superviseur,
intégrer la même commande de premier plan dans celui-ci :

```bash
/bin/bash /opt/doemo-inference-test/runpod/start-service.sh
```

Ne pas remplacer l’entrypoint existant ni lancer un second superviseur. La commande
doit démarrer automatiquement après chaque redémarrage normal du Pod ; aucune
commande JupyterLab ne doit être nécessaire. `RUNPOD_POD_ID` vient du Pod courant.

Préserver ou créer une seule fois `/workspace/doemo-studio/config/models.json` à
partir de [models.example.json](reconstruction/runpod/models.example.json).
Renseigner les chemins **observés sur RunPod** du modèle Qwen, des modèles PaddleOCR
de détection/reconnaissance et de la configuration/checkpoint RTMDet. Remplacer les
versions `to-verify` par des identifiants de modèles locaux vérifiés. L’exemple
incomplet est volontairement refusé. Ne pas télécharger d’autres poids pour le remplir.

Avant démarrage, vérifier la configuration avec le même lancement :

```bash
/bin/bash /opt/doemo-inference-test/runpod/start-service.sh --check
```

Ce contrôle vérifie les fichiers, pas l’inférence. Au lancement normal, chaque
moteur effectue son test d’inférence, séquentiellement. Une erreur reste visible
dans `/health` et les journaux privés ; elle ne déclenche aucune réinstallation.

## 4. Assurer le transport permanent

Réutiliser le tunnel ou le proxy privé géré par l’infrastructure. Le worker écoute
par défaut sur `127.0.0.1:8009` dans RunPod. Une requête d’inférence peut durer
2 800 secondes : le transport doit supporter ce délai.

Si aucun tunnel n’existe, un [exemple systemd SSH](reconstruction/ovh/doemo-redessin-tunnel.service.example)
est fourni. Le contrôleur existant doit maintenir l’alias `doemo-runpod-active` dans
`/etc/doemo-redessin/runpod-ssh.conf` avec l’hôte, le port et l’utilisateur courants,
selon [cet exemple de configuration SSH](reconstruction/ovh/runpod-ssh.conf.example),
une clé SSH autorisée et une clé d’hôte vérifiée. Le fichier et la clé SSH doivent
être lisibles par `doemo-redessin`. Ne pas fixer l’ancien identifiant de Pod ni son
ancienne IP, et ne pas désactiver la vérification de clé d’hôte. Le contrôleur doit
actualiser la cible et relancer le tunnel après migration.

L’exemple de tunnel n’est pas installé automatiquement : vérifier le transport
existant et le port avant de l’activer. Ce module ne démarre et n’arrête aucun Pod ;
le contrôleur RunPod reste celui de l’autre session.

## 5. Activer OVH et faire la recette complète

Après le contrôle des tâches et de la configuration de cadrage :

```bash
sudo apache2ctl configtest
sudo systemctl enable --now doemo-redessin.service
sudo -u doemo-redessin /opt/doemo-redessin/venv/bin/python \
  /opt/doemo-redessin/current/ovh/check-connection.py
```

Le contrôle doit retourner `state: ready`, `can_analyze: true`, les trois moteurs
avec `startup_inference_verified: true` et le code de sortie 0. Les états d’erreur
sont détaillés dans [RACCORDEMENT_RUNPOD.md](reconstruction/ovh/RACCORDEMENT_RUNPOD.md).

Dans **l’application habituelle**, ouvrir **Structure bâtiment → Redessin des murs** :

1. Le menu doit rester affiché, sans bandeau dupliqué ni page vide.
2. Vérifier l’état des trois moteurs, puis ouvrir le projet de la page 1 de `2(2).pdf`.
3. Cliquer **Analyser la page avec les trois IA** et attendre la fin de la tâche.
4. Vérifier les textes OCR, les zones commentées et les trois réponses dans les détails.
5. Recharger le projet : observations persistantes, murs corrigés conservés.
6. Vérifier le refus d’un appel au worker sans signature, puis répéter le contrôle
   après le redémarrage normal géré par l’infrastructure.

Contrôle du bandeau : `grep -c "<header>" /var/www/studio/redessin/index.php` doit
afficher **0** (le code de sortie 1 de grep signifie ici qu’aucune correspondance
n’a été trouvée). Le reste du site conserve ses restrictions de cadrage.

Le raccordement n’est déclaré réussi qu’après les trois inférences réelles.
Le redessin sémantique des murs reste un module spécialisé à qualifier ; RTMDet
COCO n’est jamais utilisé comme détecteur de murs.

## Règle de dessin à vérifier dans la recette

**Un mur = un seul trait noir plein sur l’axe médian, jamais les deux bords parallèles.**
Les portes et passages interrompent cet axe. L’épaisseur du trait est indépendante
de l’épaisseur physique et aucune échelle n’est inventée. Les doubles propositions
encore produites par le traitement géométrique doivent être corrigées, notamment
avec « Deux bords → un axe médian », avant validation. L’export validé exclut les
propositions en attente ; contrôler dans Illustrator qu’aucun mur n’a été approuvé
deux fois sous la forme de deux tracés parallèles.
