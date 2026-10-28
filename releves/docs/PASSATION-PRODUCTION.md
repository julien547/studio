# Passation à la session de déploiement en production

## Point de départ

Dépôt : **julien547/studio**, branche **`codex/studio-mvp-editor`**.
Cette branche contient le MVP d’édition, le module RunPod, les correctifs de
reconnaissance/recalage et les scripts Illustrator précédemment locaux. Elle intègre
aussi les cinq commits de `main` jusqu’à **`d03c7ea`** (moteur PDF 0.3.5).
Déployer un SHA précis de cette branche, enregistré dans le compte rendu.
Ne pas partir uniquement de `main`, qui ne contient pas encore ce nouveau module.

**Aucun déploiement OVH, changement de vhost ni appel au vrai Pod n’a été effectué
pendant la préparation.** La publication GitHub est distincte de la mise en production.
L’adresse et les accès SSH OVH, l’état réel des services, les secrets et les versions
CUDA doivent être vérifiés par la session qui dispose de ces accès.

Pod cible : **`41m7oy6qjaj2ji`**, nom attendu **`DOEMO-STUDIO-IA`**.
Ne pas reprendre un ancien ID. Ne jamais supprimer le Pod ou son volume réseau.
La clé fournisseur `RUNPOD_API_KEY` reste exclusivement sur le backend OVH.

## Carte des dossiers

| Chemin | Rôle |
| --- | --- |
| `releves/web/` | Interface React, éditeur, dashboard GPU, tests navigateur |
| `releves/backend/` | API, comptes optionnels, SQLite, file de travaux, contrôleur RunPod |
| `releves/backend/doemo_releves/migrations/` | Migrations automatiques 001 et 002 |
| `releves/services/runpod/` | Gateway, adaptateurs IA, sondes, sauvegarde/restauration Python |
| `releves/deploy/` | Modèles systemd et fragment Apache, à adapter au serveur |
| `releves/scripts/` | Configuration privée RunPod, sauvegarde, build local, import SAI |
| `api/releves.php`, `releves/index.php` | Intégration au Studio PHP et à ses sessions existantes |
| `releves/illustrator/` | Connecteur et scripts Adobe ; ne s’exécutent pas sur OVH |
| `bibliotheque pictogrammes/` | Archive SAI en deux parties, déjà versionnée |
| `engine/` | Moteur PDF existant, installation séparée, ne pas remplacer son venv |

Lire aussi [le guide RunPod](runpod-lifecycle.md), [le parcours utilisateur](mvp-demarrage.md),
[l’audit du MVP](mvp-audit.md), [les règles de pictogrammes](regles-pictogrammes.md)
et [les limites des scripts Illustrator](../illustrator/README.md).
Les anciens comptes rendus datés décrivent l’état de leur essai, pas toujours le dernier état.

## 1. Inventaire du serveur et sauvegarde

1. Vérifier le vhost `studio.doemo.fr`, son DocumentRoot, Apache/mod_php ou PHP-FPM,
   la version PHP, les certificats, les services et processus DOEMO existants,
   les ports, les comptes Unix et les chemins de données. Ne pas afficher leurs secrets.
2. Le dépôt décrit `/var/www/studio` avec Apache et session PHP/Dolibarr. **Le chemin
   recommandé ici conserve cette connexion.** Ne pas remplacer `/`, `/app`, les API
   existantes ou la connexion par le serveur autonome sans décision explicite.
3. Vérifier que l’utilisateur `doemo-studio`, les unités `doemo-releves*`,
   `/opt/doemo-studio/src`, `/opt/doemo-studio-venv`, `/run/doemo-studio` et
   `/var/lib/doemo-studio/releves` sont libres ou correspondent bien à ce module.
   Adapter les modèles si le serveur utilise d’autres chemins ou un autre groupe PHP.
4. Avant migration, mettre le module en maintenance, attendre la fin des travaux,
   arrêter ses processus écrivains et sauvegarder données, configuration Apache,
   unités et version précédente du code. Ne pas interrompre les autres applications.
   S’il existe une base, utiliser `scripts/backup.py` avec `DOEMO_RELEVES_DATA`
   correctement défini et une destination neuve. Il sauvegarde SQLite, documents et
   bibliothèques ; il ne sauvegarde pas les secrets, le vhost ou les volumes RunPod.
5. Tester la lecture de la sauvegarde sur une copie isolée avant toute bascule.

## 2. Installer le code CPU hors de la racine publique

Prérequis : Linux, Python **3.12 recommandé**, venv/pip, Node 20.19+ ou 22.12+,
Tesseract avec langue française, PHP 8.2+ avec curl/sessions/mbstring pour le mode
historique. Les dépendances ML lourdes restent sur RunPod. Installer les paquets
manquants sans remplacer les versions utilisées par les autres applications.

Commandes indicatives depuis un compte d’administration OVH, une fois les chemins
vérifiés. Si le dépôt ou le venv existe, utiliser une nouvelle release ou le chemin
validé ; ne pas écraser une installation inconnue.

```sh
git clone --branch codex/studio-mvp-editor --single-branch \
  https://github.com/julien547/studio.git /opt/doemo-studio/src
cd /opt/doemo-studio/src
git rev-parse HEAD
python3.12 -m venv /opt/doemo-studio-venv
/opt/doemo-studio-venv/bin/python -m pip install -r releves/backend/requirements.lock
/opt/doemo-studio-venv/bin/python -m pip install --no-deps -e releves/backend
/opt/doemo-studio-venv/bin/python -m pip check
npm --prefix releves/web ci
npm --prefix releves/web run build
```

Créer si absent le compte système `doemo-studio`, sans connexion interactive.
Créer le dossier de données en mode `0700`, propriétaire `doemo-studio:doemo-studio`.
Le code et le venv peuvent appartenir au compte de déploiement/root et rester
non modifiables par le service. Le build `releves/dist` et ses dossiers parents
doivent être lisibles/traversables par PHP ; les données et secrets restent privés.

Créer `/etc/doemo-studio` en `0700`, puis copier et adapter
`releves/deploy/releves.env.example` en `/etc/doemo-studio/releves.env`, mode `0600`.
Ne pas copier un fichier contenant des secrets dans Git ou dans `/var/www`.
Au premier démarrage, `Store` applique les migrations sous verrou SQLite ; il n’y a
pas de commande de migration destructive à exécuter. Ne pas lancer sur la production
la commande de création d’un utilisateur de test des tests navigateur.

## 3. Démarrer les services OVH en mode CPU

Les quatre modèles dans `releves/deploy/` sont prévus pour **le mode PHP** :

- `doemo-releves.socket` : socket privé, mode `0660`, groupe `www-data` à adapter.
- `doemo-releves.service` : API privée, un worker, reçoit le socket systemd sur fd 3.
- `doemo-releves-worker.service` : file persistante CPU/GPU.
- `doemo-releves-gpu.service` : contrôleur, sans action tant que `MANAGED=0`.

Les trois services partagent **exactement le même dossier de données local OVH**.
Ne pas le mettre sur NFS/FUSE ni lancer des contrôleurs sur plusieurs machines.
Les unités lisent le fichier RunPod optionnel après le fichier général ; son
`DOEMO_RUNPOD_MANAGED` est donc prioritaire s’il existe.

Après revue des comptes, chemins et unités préexistantes :

```sh
sudo install -m 0644 releves/deploy/doemo-releves.socket /etc/systemd/system/
sudo install -m 0644 releves/deploy/doemo-releves.service /etc/systemd/system/
sudo install -m 0644 releves/deploy/doemo-releves-worker.service /etc/systemd/system/
sudo install -m 0644 releves/deploy/doemo-releves-gpu.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/doemo-releves*.service \
  /etc/systemd/system/doemo-releves.socket
sudo systemctl daemon-reload
sudo systemctl enable --now doemo-releves.socket doemo-releves.service \
  doemo-releves-worker.service doemo-releves-gpu.service
```

Vérifier l’état et les journaux des trois services. Tester `/health` via le socket
depuis le compte PHP. L’API privée fait confiance aux en-têtes du relais : **ne
jamais la rendre accessible en TCP public ou via un proxy public direct**.
Le socket systemd détermine ses droits ; aucun `chmod 777` n’est nécessaire.

## 4. Raccorder le Studio HTTPS existant

Sauvegarder puis publier uniquement :

| Source | Destination décrite par le dépôt |
| --- | --- |
| `releves/index.php` | `/var/www/studio/releves/index.php` |
| `releves/dist/assets/` | `/var/www/studio/releves/assets/` |
| `api/releves.php` | `/var/www/studio/api/releves.php` |

Conserver `api/_s.php` et l’authentification existante après comparaison avec le dépôt.
Le HTML compilé reste lu depuis le chemin privé `DOEMO_RELEVES_DIST`.
Garder les anciens assets jusqu’à la fin de la bascule pour les onglets déjà ouverts.
Ne jamais synchroniser tout le dépôt dans le DocumentRoot.

Adapter le fragment `deploy/apache-releves.conf.example` au vhost existant. Il
transmet le chemin du socket et du build à PHP et ajuste la CSP pour les aperçus
`blob:` et `data:`. Vérifier les en-têtes effectivement renvoyés : une autre CSP
plus restrictive peut encore bloquer les images.
Pour PHP-FPM, régler les variables et limites dans le pool approprié ; les
directives mod_php ne s’y appliquent pas. Les limites PHP/Apache doivent accepter
l’archive SAI de 178 Mo si import via navigateur ; les documents ordinaires restent
soumis aux limites applicatives. Prévoir aussi le timeout du relais (210 secondes).

Exécuter `apachectl configtest` avant le rechargement du seul serveur web concerné.
Tester une connexion Studio existante, puis `https://studio.doemo.fr/releves/`.
La publication du nouveau menu/lien dans l’application `/app` dépend de son dépôt
distinct `doemo-app` : ce build n’est pas versionné ici. L’URL directe suffit pour
la recette initiale ; ne pas prétendre avoir modifié le menu de cette application.

**Alternative autonome** : `auth:standalone --factory` est disponible avec comptes
locaux, sur loopback, pour une instance isolée. Voir `mvp-demarrage.md`. Ses routes
`/session`, `/login`, `/logout`, `/api/*` doivent être servies sur une origine dédiée
ou intégrées explicitement ; ne pas les substituer aux routes PHP existantes.
Les unités ci-dessus ne sont pas des unités du mode autonome.

## 5. Bibliothèque et ressources Illustrator

Réunir les deux parties SAI dans l’ordre avec `scripts/reassemble-library.py`,
hors de la racine web. SHA-256 attendu :
`01f8702f33094659c3cb95e94f9a42a9a6b1cc6f344d2724a651c5c50fef2fde`.
L’import requiert aussi l’inventaire JSON utilisateur, qui n’est pas dans ce dépôt.
Importer par l’interface administrateur ou la CLI, puis vérifier et approuver les
ressources natives. Un catalogue provisoire ne suffit pas à autoriser une pose.

Règles confirmées : tous les extincteurs utilisent **Extincteur Portatif** ;
les **portes coupe-feu** ont leur propre symbole. Le **VEI n’est pas dans SAI** et
doit être importé depuis la ressource native fournie par l’utilisateur.
Les règles de numéros de zones sont propres au dossier Animalis.

Les PDF/AI clients, résultats de traitement, fichiers privés d’audit, inventaire et
modèles GPU ne sont pas embarqués dans Git. Les récupérer depuis le stockage privé
ou la session utilisateur. Les chemins `/workspace/...` des anciens rapports sont
des traces locales, pas des liens de téléchargement utilisables depuis OVH.

## 6. Préparer RunPod puis activer l’automatisation

Suivre intégralement [runpod-lifecycle.md](runpod-lifecycle.md) :

1. Sur **OVH**, exécuter `scripts/configure-runpod.py --output-dir /etc/doemo-studio/runpod`
   dans un terminal, avec les droits nécessaires. Saisir la clé sans l’afficher.
2. Ne transmettre au Pod que le jeton gateway, jamais `runpod-ovh.env`.
3. Vérifier le Pod `41m7oy6qjaj2ji`, son nom et le volume persistant `/workspace`.
4. Copier le code gateway dans `/workspace/doemo-studio/services/runpod`, vérifier
   les trois environnements ML existants et les chemins de modèles locaux.
5. Exécuter les trois sondes réelles ; capturer les quatre environnements validés
   avec `environments.py snapshot`. Ne pas réinstaller CUDA/ML arbitrairement.
6. Configurer le bootstrap persistant comme commande de démarrage, exposer le port
   HTTP 8000 via le proxy HTTPS authentifié, vérifier l’accès depuis OVH.
7. Garder `MANAGED=0` tant que les étapes précédentes ne sont pas vérifiées. Pour
   la première recette contrôlée, définir `MANAGED=1`, `AUTOSTART=0`, `AUTOSTOP=0`
   dans le fichier OVH, puis redémarrer les trois services ensemble sans travail actif.
8. Tester les commandes administrateur, les trois moteurs, la persistance, puis
   activer `AUTOSTART=1` et `AUTOSTOP=1` et redémarrer les trois services.

API officielle : `https://api.runpod.io/v2`, actions `start`/`stop` via
`POST /pods/{id}/action`. Pas de suppression/recréation de Pod. Le démarrage peut
attendre une capacité GPU disponible. Un gateway inaccessible empêche un arrêt
automatique sûr : diagnostiquer l’erreur, le GPU peut rester facturé pendant ce temps.

## 7. Recette de production à consigner

- Sans GPU : connexion, import PDF, deux niveaux, annotations/ancrages distincts,
  sauvegarde, rechargement, historique et export JSON.
- Rôles : un dessinateur voit l’état GPU ; seuls les administrateurs commandent
  démarrage/arrêt et lisent le journal d’administration. Vérifier les accès aux projets.
- GPU arrêté : une analyse déclenche un seul démarrage ; elle attend Qwen3.5-9B,
  PaddleOCR et RTMDet réellement prêts. Tester une inférence de chaque moteur.
- Tâche active/en attente : l’arrêt manuel et automatique sont refusés. Les résultats
  restent en revue, sans remplacer les corrections humaines.
- Inactivité : l’arrêt arrive après au moins 30 minutes réellement inactives des
  deux côtés. Garder le dashboard ouvert ne doit pas empêcher cet arrêt.
- Reprise : interruption/reconnexion, résultat conservé avec le même ID, journaux
  persistants, modèles et fichiers conservés après arrêt/démarrage.
- Restauration : valider les archives dans une cible de test avant de simuler une
  perte du disque conteneur. Ne pas supprimer les environnements de production
  pour un essai improvisé, ni supprimer le Pod ou son volume réseau.
- Illustrator : ouvrir, poser, sauvegarder une nouvelle copie AI et la rouvrir sur
  un poste Illustrator 2024+. Les tests Linux ne valident pas le DOM Adobe.
- Vérifier que les autres applications DOEMO et l’atelier OVH restent accessibles.

Validation locale déjà effectuée : 80 tests backend, 8 tests JavaScript d’éditeur,
compilation TypeScript/Vite et parcours navigateur. Les six fichiers de tests
Illustrator passent avec DOM simulé. Les commandes réelles RunPod et les unités
systemd/Apache doivent encore être validées sur leurs machines cibles.
Après intégration des mises à jour de `main`, les **166 tests du moteur PDF** passent
également. La syntaxe des unités systemd a été contrôlée sur des copies temporaires
avec le chemin Python de l’environnement cloud ; aucun service n’y a été installé.

## 8. Retour arrière

Bloquer les nouveaux travaux, attendre les analyses en cours, puis arrêter le
contrôleur, le worker, l’API **et le socket** pour éviter une réactivation automatique.
Restaurer le vhost et les seuls fichiers publics du module depuis la sauvegarde,
ainsi que la release précédente. Si retour à un schéma antérieur, restaurer ensemble
base et documents de la sauvegarde cohérente dans un dossier neuf, puis faire pointer
la release précédente dessus. Conserver séparément les données postérieures pour
réconciliation ; ne pas tenter un downgrade SQL improvisé.

Arrêter le contrôleur ne stoppe pas le GPU. Si un Pod reste allumé, vérifier
l’absence de travail et procéder à son arrêt contrôlé, **jamais à sa suppression**.
Un ancien Pod encore actif n’est pas géré par le nouvel identifiant ; vérifier
séparément sa facturation. Consigner SHA déployé, chemins, configuration non secrète,
services, résultats de recette, état GPU et procédure exacte de rollback.

## Message à donner à la prochaine session

> Déploie DOEMO Studio depuis `julien547/studio`, branche `codex/studio-mvp-editor`.
> Commence par `releves/docs/PASSATION-PRODUCTION.md` et `releves/docs/runpod-lifecycle.md`.
> Vérifie l’existant OVH, sauvegarde et préserve les autres applications et sessions PHP.
> Installe le module CPU avant d’activer RunPod. Pod : `41m7oy6qjaj2ji`, nom :
> `DOEMO-STUDIO-IA`. Clé RunPod exclusivement sur OVH, jamais dans le chat ni Git.
> Prépare et vérifie le bootstrap et les modèles réels avant l’automatisation.
> Ne supprime ni Pod ni volume. Effectue la recette et fournis le SHA déployé et
> les preuves de fonctionnement. Les essais cloud précédents ne sont pas une
> validation de production ni une validation native Illustrator.
