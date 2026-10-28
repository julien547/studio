# Déployer le module de test du redessin sur OVH

La session chargée du VPS déploie cette livraison. Le code est destiné à
**studio.doemo.fr**, dans l’application existante : aucune modification de
`plans.doemo.fr`, de l’API de connexion DOEMO ou des trois environnements IA.

## Ce qui sera disponible

URL après déploiement : **https://studio.doemo.fr/redessin/**.

Un administrateur ou dessinateur connecté peut importer un PDF, PNG ou JPEG,
sélectionner une page, obtenir des axes proposés, les corriger, enregistrer le
projet sur OVH et télécharger les murs validés en SVG. Chaque utilisateur accède
uniquement à ses projets. Les fichiers sources restent hors du répertoire web.
La page est autonome par rapport au build React : ce premier essai ne nécessite
pas de remplacer le dossier `/app/`. Un lien de menu React peut être livré séparément.

Les PDF vectoriels sont analysés en priorité. Pour les scans, cette version utilise
un traitement géométrique expérimental. **Le modèle de segmentation architecturale
n’est pas qualifié.** Le nombre de propositions ne mesure pas leur précision. Les
ouvertures ne sont pas reconnues automatiquement par cette version. Aucun mur ni
aucune échelle n’est approuvé automatiquement. Les coordonnées de la page restent
inchangées ; le trait graphique et l’épaisseur physique sont indépendants.

Le bouton des trois IA devient disponible après configuration du service RunPod.
Il ajoute des observations OCR et de zones sans remplacer les murs corrigés.
RTMDet COCO reste un diagnostic, jamais une détection architecturale de murs.
Le module ne démarre, n’arrête et ne migre aucun Pod. Ne pas activer le contrôleur
historique `ai_service/service.py` pour ce déploiement : l’autre session gère déjà
ce cycle de vie et doit intégrer les tâches de ce module à son contrôle d’inactivité.

## 1. Identifier le site et préparer les sources

Sur OVH, relever le vhost actif, son DocumentRoot et son gestionnaire PHP avec
`apache2ctl -S`. Vérifier que le site utilise `api/_s.php` et la session
`studio_sid`. Le groupe du serveur web attendu est `www-data` ; adapter l’unité
et le script après inventaire si le serveur utilise un autre groupe.

Cloner le dépôt privé avec l’identité GitHub déjà disponible sur le VPS, dans un
répertoire de sources hors du web. Ne pas écraser un checkout avec des modifications.
Branche de livraison : `feat/redessin-ovh-tests` dans `julien547/studio`.

```bash
git clone --branch feat/redessin-ovh-tests --single-branch https://github.com/julien547/studio.git /opt/doemo-redessin-source
cd /opt/doemo-redessin-source
git status --short
git rev-parse HEAD
```

Comparer le SHA avec celui fourni dans la transmission. Le déploiement ne nécessite
pas de fusionner la branche avant l’essai. Conserver ce SHA dans le compte rendu.

Prérequis : Python 3.11 ou ultérieur avec `venv` et pip, PHP 8.2 ou ultérieur avec
cURL et sessions, Apache, systemd, `timeout` et `prlimit` (util-linux). Tesseract
et sa langue anglaise sont facultatifs pour le masquage local des textes. Installer
uniquement les composants manquants avec le gestionnaire de paquets Debian. Aucun
PyTorch, Paddle ou MMDetection n’est nécessaire sur OVH.

## 2. Vérifier les fichiers avant installation

```bash
python3 reconstruction/ovh/build_web.py
php -l api/redessin.php
php -l redessin/index.php
bash -n reconstruction/ovh/install-release.sh
```

Pour exécuter les tests sur le serveur, utiliser un environnement de vérification
séparé ; ne pas les installer dans les environnements existants d’autres modules :

```bash
python3 -m venv /opt/doemo-redessin-check
/opt/doemo-redessin-check/bin/pip install './reconstruction[test,service]'
cd reconstruction
/opt/doemo-redessin-check/bin/python -m pytest -q
cd ..
```

Les tests GPU utilisent des doubles, et la segmentation des masques synthétiques.
Ils vérifient le logiciel ; une recette réelle RunPod et Adobe reste distincte.

## 3. Installer la version et configurer Apache

Pour une mise à jour, attendre la fin des tâches et contrôler leur état dans la
base privée avant d’arrêter le service. Une tâche `running` ou `interrupted` doit
être réconciliée, particulièrement si RunPod peut encore travailler. Le script
refuse de publier une nouvelle version tant que le service est actif.

Exemple **si le DocumentRoot relevé est bien `/var/www/studio`** :

```bash
sudo bash reconstruction/ovh/install-release.sh /opt/doemo-redessin-source /var/www/studio
```

Le script prépare une version isolée `/opt/doemo-redessin/releases/<SHA>` et son
venv, conserve les anciennes versions, sauvegarde les fichiers qu’il remplace,
installe le code public et l’unité systemd. Il crée le compte `doemo-redessin`,
réserve `/var/lib/doemo-redessin` à ses données privées et utilise exclusivement
le socket `/run/doemo-redessin/api.sock` entre PHP et Python. Il n’active pas le service.
La liste exacte des dépendances résolues est conservée dans `installed-requirements.txt`.

Adapter puis insérer l’extrait `apache-redessin.conf.example` dans le vhost existant,
sans remplacer son contenu. `DirectoryIndex index.php` doit s’appliquer au seul
dossier `redessin`. Conserver les protections et la connexion existantes. Le
frontend utilise des scripts externes compatibles avec `script-src 'self'` ; aucun
assouplissement pour du JavaScript inline ou `eval` n’est requis.

Vérifier dans la configuration PHP **de Studio** : `upload_max_filesize=20M`,
`post_max_size=32M`, `memory_limit=256M` et un délai d’exécution d’au moins 35 secondes.
Les longs calculs sont réalisés par systemd, hors requête PHP. Le socket peut
restreindre l’accès au groupe web mais ne doit jamais être publié par un proxy HTTP.

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
sudo systemctl enable --now doemo-redessin.service
sudo systemctl status doemo-redessin.service --no-pager
```

Si PHP-FPM est utilisé, valider puis recharger le pool effectivement identifié après
modification de ses paramètres. Ne pas supposer le nom de son service.

## 4. Recette sans GPU puis activation de RunPod

Premier contrôle interne, depuis OVH :

```bash
sudo -u www-data curl --fail --unix-socket /run/doemo-redessin/api.sock \
  -H 'X-Doemo-User: deployment-check' http://localhost/health
```

`ready: true` confirme uniquement le service OVH. `runpod_configured` est faux tant
que les deux paramètres distants ne sont pas renseignés. Le header utilisateur
ci-dessus appartient exclusivement au canal local : PHP le reconstruit depuis la
session authentifiée et ignore tout header utilisateur envoyé par le navigateur.

Dans le navigateur :

1. Sans connexion, `/redessin/` renvoie vers la connexion et l’API répond 401.
2. Se connecter avec un compte dessinateur ; importer **uniquement la page 1 de `2(2).pdf`** depuis le fichier client privé.
3. Contrôler la référence, les diagonales et les passages. Corriger un axe, puis valider un mur.
4. Cliquer **Enregistrer sur OVH**, recharger le projet et vérifier la persistance.
5. Télécharger le SVG validé et vérifier un trait noir indépendant par portion de mur.
6. Vérifier qu’un second utilisateur ne voit pas le projet du premier. Un rôle non autorisé reçoit 403.

Pour RunPod, l’autre session fournit un transport privé fonctionnel vers le worker
du paquet `reconstruction/runpod/TEST_DEPLOIEMENT.md`. Configurer ensuite
`/etc/doemo-redessin/service.env` avec l’URL réelle et le chemin de la clé privée
Ed25519 PEM de signature côté OVH. Ne pas utiliser la clé SSH pour signer les appels.
La clé publique correspondante est configurée sur le worker RunPod. Aucun secret ne
doit être ajouté à GitHub, au build web ou à un plan.

```text
DOEMO_RUNPOD_URL=http://127.0.0.1:PORT_REEL_DU_TUNNEL
DOEMO_OVH_PRIVATE_KEY=/etc/doemo-redessin/worker-signing-private.pem
```

Une URL privée HTTPS peut remplacer le tunnel. HTTP hors boucle locale est refusé.
Le transport doit supporter jusqu’à 2 800 secondes pour l’essai d’inférence synchrone.
Le navigateur, lui, suit une tâche asynchrone et ne reste pas dans une requête longue.
Ne pas fixer un ancien identifiant de Pod : l’infrastructure gère la redécouverte
et la mise à jour du tunnel ou de l’endpoint après migration.

Rendre la clé lisible par le compte `doemo-redessin`, protégée des autres comptes,
puis redémarrer le seul service du redessin lorsqu’aucune tâche n’est en cours.
Le bouton **Tester les trois IA sur cette page** sauvegarde d’abord les corrections,
puis attend les réponses avec versions et provenance vérifiées. Les observations
sont attachées au dernier dessin sauvegardé ; elles n’approuvent aucun mur.

Après une interruption réseau ou un redémarrage au milieu d’une inférence, une tâche
peut passer à `interrupted`. Ne pas la rejouer automatiquement ni arrêter le GPU.
Comparer son identifiant aux résultats persistants du worker RunPod et réconcilier
l’état avant un nouvel essai. La première livraison bloque une nouvelle analyse sur
ce projet tant que cette vérification n’a pas été faite.

## 5. Vérification et retour arrière

Les journaux du service sont accessibles par :

```bash
sudo journalctl -u doemo-redessin.service -n 100 --no-pager
```

Ne pas copier de PDF client, de contenu OCR ou de clé privée dans un ticket GitHub.
Sauvegarder régulièrement `/var/lib/doemo-redessin` avec une procédure cohérente
pour SQLite et les sources. Aucune purge automatique des projets n’est activée dans
ce prototype : prévoir une durée de conservation et surveiller l’espace disque.

Pour revenir en arrière après vérification des tâches : arrêter le service, rétablir
les liens `current` et `venv` depuis les chemins conservés dans la sauvegarde,
restaurer les seuls fichiers `redessin/`, `api/redessin.php` et l’unité concernés,
puis recharger systemd et relancer la version précédente. Pour une première
installation annulée, désactiver le service et retirer les seules routes ajoutées.
Conserver les données privées pour récupération ; ne supprimer aucun autre module.

Le déploiement n’est réussi qu’après cette recette sur **OVH réel**. La publication
GitHub et les tests locaux ne constituent pas un déploiement du site.
