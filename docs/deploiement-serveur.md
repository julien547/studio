# Transmission et déploiement — DOEMO Studio

## Périmètre à déployer

URL du module : **https://studio.doemo.fr/app/orientation**.
Pour les contours libres, installer aussi `skia-pathops` depuis le verrou Python,
publier `api/_orientation_levels.php` avec `api/orientation.php` et reconstruire
la page React. Voir [la procédure et le stockage persistant](niveaux-libres.md).
La [mise à jour du parcours par lot](generation-par-lot.md) concerne le moteur,
l'API de ce dépôt et la page React de `doemo-app` sur `feat/studio-host` : déployer
les deux dépôts pour disposer du choix de dossier client et de l'analyse du lot.
Origine et connexion : **https://studio.doemo.fr**. Ne pas modifier `plans.doemo.fr` ni
les autres applications DOEMO. La connexion existante utilise l'API distante
`https://gestion.doemo.fr/api_doemo.php` ; aucune modification de cette API n'est
requise par cette livraison.

La livraison 0.3.0 ajoute la génération Linux des lots de test : tous les VEI
du BAT pris en charge, PDF individuels et ZIP. **Délimitation facultative,
désactivée par défaut.** Déployer le moteur puis les trois fichiers
`api/orientation.php`, `api/_orientation_levels.php`, `api/_orientation_batch.php`,
et enfin le build React de `doemo-app/feat/studio-host`.

La [procédure 0.3.0](generation-linux.md) précise les commandes, chemins et limites.
Le profil courant traite les BAT Illustrator AI24 à une page. Il refuse les
sources non identifiées plutôt que de produire un plan erroné. Les résultats
restent des PDF de test à contrôler visuellement ; le serveur cible n'a pas été
activé depuis cette session. L'ancienne action `compose` reste bloquée et le
diagnostic de page entière n'est jamais appelé par le bouton de génération.

## Chemins actuels dans cette session cloud

| Contenu | Chemin |
| --- | --- |
| Checkout | `/workspace/studio/` |
| Moteur Python | `/workspace/studio/engine/` |
| Code Python | `/workspace/studio/engine/src/doemo_pdf/` |
| Tests Python | `/workspace/studio/engine/tests/` |
| API PHP existante | `/workspace/studio/api/` |
| Rapports et contrat d'export | `/workspace/studio/docs/` |
| Exemple Apache existant | `/workspace/studio/deploy/studio-doemo-fr-le-ssl.conf.example` |
| Environnement Python du cloud | `/workspace/.venvs/studio-pdf/` |
| Données de test et diagnostics privés | `/workspace/studio-audit/` |
| Sources Illustrator reçues | `/workspace/studio-audit/script-1.0.13/DOEMO-Studio-nouveau-moteur-1.0.13/` |
| Nouvelle référence Illustrator 1.0.14 | `/workspace/studio-audit/script-1.0.14/DOEMO-Generateur/` |
| Fichiers originaux joints | `/workspace/attachments/` |
| Archives préparées pour transmission | `/workspace/studio-handoff/` |

Ces chemins sont propres à cette session ; une autre conversation ou le serveur
ne les voit pas automatiquement. La livraison de code se fait maintenant via
`https://github.com/julien547/studio.git`, branche `main`, avec ce guide dans
`docs/deploiement-serveur.md`. Utiliser le commit de publication indiqué dans la
conversation et vérifier sa présence sur le serveur. Les anciennes archives de
code v1/v2 précèdent cette synchronisation : ne pas les recopier par-dessus une
version Git plus récente.

Les deux trames de test sont versionnées dans `resources/templates/doemo/`.
Les BAT clients, fichiers AI, données natives extraites et diagnostics ne font
pas partie de cette livraison Git ; ils restent dans le stockage privé du cloud
et, pour les fichiers d'entrée, dans l'archive privée déjà préparée.

## Chemins proposés sur le serveur

À confirmer après inventaire des chemins et du vhost déjà présents :

| Contenu | Emplacement proposé | Accès |
| --- | --- | --- |
| Source complète et documentation | `/opt/doemo-studio/src/` | Administrateur/déploiement uniquement |
| Venv serveur | `/opt/doemo-studio/venv-pdf/` | Administrateur ; diagnostic en CLI |
| Racine publique du site | `/var/www/studio/` | Apache/PHP, lecture du code |
| Frontend React construit séparément | `/var/www/studio/app/` | Préserver le build existant ; provenance doemo-app |
| BAT, AI et scripts de référence | `/var/lib/doemo-studio/private/` | Privé, hors web |
| Racine privée des collections de trames | `/var/lib/doemo-studio/templates/` | Hors web, sous-dossiers par client |
| **Collection DOEMO par défaut** | **`/var/lib/doemo-studio/templates/doemo/`** | Écriture pour l'administration autorisée, lecture pour le moteur |
| Diagnostics et futurs résultats | `/var/lib/doemo-studio/results/` | Privé, hors web |
| Sauvegardes du site et des configurations | `/var/backups/doemo-studio/` | Administrateur uniquement |
| Vhost Apache | `/etc/apache2/sites-available/studio-doemo-fr-le-ssl.conf` | Administrateur |

Ne jamais cloner tout le dépôt dans le DocumentRoot. Depuis ce dépôt, publier
uniquement `index.html`, `style.css`, `login.js`, `favicon.svg` et `api/`.
Le répertoire `app/` vient du build séparé : le préserver lors de la mise à jour.
Ne pas réintroduire les anciens `app.html` et `app.js`, supprimés de `main`.
Ne pas publier `.git`, `docs`, `engine`, `resources`, les archives, les BAT ou les résultats.

### Dossier fixe des trames

Chemin serveur retenu pour les trames DOEMO : **`/var/lib/doemo-studio/templates/doemo/`**.
Les trames personnalisées des clients sont dans des sous-dossiers voisins de
`doemo`, sous la même racine privée ; ne pas les ranger dans le dossier DOEMO.
Les deux premiers fichiers sont :

```text
/var/lib/doemo-studio/templates/doemo/PE-A3-V.pdf
/var/lib/doemo-studio/templates/doemo/PI-A3-V.pdf
/var/lib/doemo-studio/templates/client-a/...
/var/lib/doemo-studio/templates/client-b/...
```

Le moteur expose cette racine et la collection `doemo` par défaut dans
`engine/src/doemo_pdf/settings.py`. Python accepte `DOEMO_TEMPLATES_ROOT`,
documentée dans `deploy/studio.env.example`. L'API PHP utilise actuellement la
constante `TPL_BASE` dans `api/templates.php`, fixée à
`/var/lib/doemo-studio/templates` : elle ne lit pas cette variable d'environnement.
Les défauts concordent ; aucune modification de chemin n'est nécessaire.
Si la racine change ultérieurement, adapter explicitement les deux composants.

L'API expose list, download, mkdir, upload et delete. La lecture est réservée aux
utilisateurs internes, l'écriture aux rôles admin/administration. `doemo` est
protégé contre la suppression. Les fichiers remplacés ou supprimés sont déplacés
vers `.corbeille` et un journal est tenu dans `.journal.log` ; les sauvegarder aussi.

L'API accepte des noms avec espaces, accents et des sous-dossiers. Le résolveur
CLI Python accepte aussi les espaces et accents sur un niveau de collection ;
les séquences `..` et les traversées sont refusées. Les contrôles d’accès par
client/équipe distincts des droits de projet restent à définir.

Créer cette arborescence avec un groupe dédié partagé par le compte PHP Studio et le
futur worker, ou des ACL équivalentes : le compte d'administration doit pouvoir
y écrire, le moteur doit pouvoir lire. Adapter les utilisateurs à ceux constatés
sur le serveur ; ne pas supposer `www-data` et ne pas utiliser `chmod 777`.
Conserver les sources applicatives non modifiables par le compte web.

L'API vérifie l'en-tête PDF et limite un fichier à 50 Mio ; ce contrôle ne valide
pas la structure vectorielle ou la conformité métier. Adapter les limites PHP
`upload_max_filesize`, `post_max_size` et celles du proxy aux imports autorisés,
sans modifier les autres applications. Le remplacement met l'ancien fichier à
la corbeille : ce n'est pas encore un versionnement lié aux productions passées.
Le catalogue (type PE/PI, format, H/V, client, zone, validation) reste à intégrer.
Les aperçus et téléchargements passent par l'API authentifiée, jamais par un Alias
Apache vers ce dossier privé.

## 1. Examiner le serveur et préserver l'existant

Sur Debian/Ubuntu avec Apache, adapter si le serveur utilise une autre pile :

```sh
sudo apache2ctl -S
php -v
php -m
python3 --version
df -h
free -h
```

Identifier le vhost effectif de `studio.doemo.fr`, sa racine, son gestionnaire
PHP (mod_php ou FPM), ses certificats et son propriétaire. Sauvegarder le vhost,
la racine publique existante et leurs permissions **avant** toute modification.
Si les répertoires proposés existent déjà, ne pas les écraser : préparer une
nouvelle livraison à côté et comparer les différences.

Prérequis : Python 3.11 minimum (3.12 testé), module `venv`, PHP pris en charge
par le serveur avec `curl`, `json` et sessions, Apache avec HTTPS et en-têtes de
sécurité. Réutiliser le gestionnaire PHP existant ; ne pas basculer globalement
de FPM à mod_php ou changer le MPM pour cette application.

Installer les paquets manquants selon l'OS et la version PHP en place. Aucun
Node/npm n'est nécessaire pour installer le moteur Python et les fichiers PHP.
La reconstruction du frontend séparé nécessite les outils et versions indiqués
dans `doemo-app` ; conserver son build existant si cette étape n'est pas requise.

Pour un poste de diagnostic initial, prévoir provisoirement 2 vCPU, 4 Gio de RAM
et de l'espace privé pour les sources, sorties et sauvegardes. Ce n'est pas un
dimensionnement de production ; la concurrence et la charge n'ont pas été mesurées.

## 2. Récupérer le code depuis GitHub

Pour une première installation, si `/opt/doemo-studio/src/` n'existe pas encore,
créer son parent avec les droits du compte de déploiement, puis :

```sh
git clone --branch main https://github.com/julien547/studio.git /opt/doemo-studio/src
cd /opt/doemo-studio/src
git rev-parse HEAD
```

Pour une installation existante, vérifier l'identité du dépôt, la branche et
les modifications locales avant la mise à jour. Si le checkout est propre et
sur `main` :

```sh
set -eu
cd /opt/doemo-studio/src
git status --short
git pull --ff-only origin main
git rev-parse HEAD
```

Si le serveur possède des modifications ou commits locaux, les préserver et
résoudre leur intégration ; ne pas faire de reset forcé ou de nettoyage aveugle.
Vérifier que le commit de publication annoncé est présent dans l'historique.

Les trames initiales sont dans `resources/templates/doemo/`. Vérifier leurs
empreintes avec `resources/templates/catalogue-test.json`, puis copier les deux
PDF dans `/var/lib/doemo-studio/templates/doemo/` sans écraser de version
existante. Elles restent des trames **SPECIMEN non activées pour production**.

### Données de test privées, facultatives pour l'installation

Si des essais sur les BAT réels sont nécessaires, recevoir
`DOEMO-Studio-fichiers-prives-v2.zip` séparément dans un répertoire privé et
vérifier ses empreintes. Ce paquet n'est pas publié sur GitHub. Contrôler les
chemins à l'extraction ; ne jamais extraire une archive dans la racine publique.

L'archive privée contient les BAT dans `private/`, les deux trames dans
`templates/doemo/` et le ZIP Illustrator dans `private/reference-illustrator/`.
Après extraction et vérification dans un dossier temporaire privé, copier les
contenus vers `/var/lib/doemo-studio/private/` et le dossier fixe
`/var/lib/doemo-studio/templates/`, en préservant tout fichier déjà présent.
Ne pas exécuter les JSX sur le serveur et ne pas installer Illustrator.

## 3. Installer le moteur de diagnostic

Les commandes suivantes supposent que la source vérifiée se trouve dans
`/opt/doemo-studio/src/`. Les exécuter avec le compte de déploiement disposant
des permissions nécessaires sur ces répertoires ; ne pas rendre le code
modifiable par le compte du serveur web.

```sh
set -eu
cd /opt/doemo-studio/src
python3 -m venv /opt/doemo-studio/venv-pdf
/opt/doemo-studio/venv-pdf/bin/python -m pip install -r engine/requirements.lock
/opt/doemo-studio/venv-pdf/bin/python -m pip install --no-deps ./engine
/opt/doemo-studio/venv-pdf/bin/python -m pytest -q engine/tests
/opt/doemo-studio/venv-pdf/bin/doemo-pdf --help
/opt/doemo-studio/venv-pdf/bin/doemo-pdf templates-dir
/opt/doemo-studio/venv-pdf/bin/doemo-pdf templates-dir --client client-a
```

Le répertoire `venv-pdf` est dédié au moteur PDF ; le venv déjà utilisé par
une autre application doit être conservé. Le module est installé ici en mode
normal, pas comme un service HTTP. Les tests
doivent réussir ; une installation des dépendances seule ne valide pas le moteur.
Ne pas lancer `engine/setup-cloud.sh` sur le serveur : il contient volontairement
les chemins `/workspace` spécifiques au cloud.

Essais privés après extraction dans le chemin proposé :

```sh
/opt/doemo-studio/venv-pdf/bin/doemo-pdf inspect \
  /var/lib/doemo-studio/private/CO26100364-1.pdf
/opt/doemo-studio/venv-pdf/bin/doemo-pdf inspect-ai \
  /var/lib/doemo-studio/private/CO26100364-1.ai
```

Le CLI retourne le statut de diagnostic et ne crée aucun serveur persistant.
Il n'y a donc ni unité systemd de worker ni proxy Python à configurer pour cette
version. Ne pas exposer une commande shell de génération à travers PHP.

## 4. Préparer et publier seulement le socle web

Après sauvegarde et examen des différences, préparer dans un nouveau répertoire
de livraison publique `index.html`, `style.css`, `login.js`, `favicon.svg` et
`api/` provenant de la source. Préserver `/var/www/studio/app/` et les éventuels
autres fichiers serveur non versionnés ; ne pas les supprimer lors de la copie.
Vérifier la syntaxe de chaque fichier PHP avant activation :

```sh
set -eu
cd /opt/doemo-studio/src
for file in api/*.php; do php -l "$file"; done
```

Le code doit appartenir au compte de déploiement ou à root et rester lisible par
Apache. Le compte PHP doit pouvoir écrire dans son stockage de sessions et dans
`/var/lib/doemo-studio/templates/` pour l'administration des trames, y compris les
sous-dossiers, `.corbeille` et `.journal.log`. Aucun upload public n'est nécessaire.

Remplacer uniquement les fichiers de cette application avec la procédure de
livraison habituelle du serveur, en conservant la possibilité de restaurer la
sauvegarde. Ne pas utiliser `rsync --delete` sur une racine non inventoriée.

Le frontend séparé est décrit dans le README : branche `feat/studio-host` de
`julien547/doemo-app`, commande de build annoncée `npx vite build -c vite.studio.config.js`.
La présence de cette branche a été vérifiée, mais pas son build dans cette session.
Si le frontend doit être construit, suivre les instructions et le lockfile de ce
dépôt dans un checkout séparé, vérifier le répertoire de sortie réel, puis publier
uniquement ce build dans `/var/www/studio/app/`. Ne pas déployer l'application
principale doemo-app à la place de Studio et ne pas modifier son hébergement.

Le module doit être enregistré dans le routeur React à `/app/orientation` (route
`/orientation` si le routeur utilise déjà le préfixe `/app`). L'URL ne désigne pas
un sous-dossier PHP à créer : l'entrée physique reste le build
`/var/www/studio/app/index.html`. Vérifier la route et le préfixe dans le frontend
séparé ; ce dépôt ne contient pas son code React.

## 5. Configurer le vhost et HTTPS

Le fichier `deploy/studio-doemo-fr-le-ssl.conf.example` est un **exemple incomplet
de TLS** : il n'indique pas les chemins du certificat et de sa clé. Ne pas le
copier tel quel en pensant que HTTPS sera opérationnel.

Dans le vhost dédié à `studio.doemo.fr`, garder le DocumentRoot public convenu,
la configuration PHP effective du serveur et les en-têtes fournis dans l'exemple.
Ajouter ou préserver les directives TLS utilisant les certificats réellement
présents. Avec un certificat Certbot dédié existant, les chemins habituels sont :

```apache
SSLEngine on
SSLCertificateFile /etc/letsencrypt/live/studio.doemo.fr/fullchain.pem
SSLCertificateKeyFile /etc/letsencrypt/live/studio.doemo.fr/privkey.pem
```

Ces chemins ne sont qu'un exemple : vérifier le certificat installé avant de les
utiliser. Conserver le refus HTTP d'accès direct à `_s.php` et les protections
de l'exemple. S'assurer qu'aucun Alias ne publie les dossiers privés ou sources.

Pour qu'un accès direct ou un rafraîchissement sur `/app/orientation` charge le
routeur React, préserver la règle SPA existante. Si elle manque, intégrer dans le
vhost Studio une règle limitée au répertoire du build, par exemple :

```apache
<Directory /var/www/studio/app>
    FallbackResource /app/index.html
</Directory>
```

Le fichier `app/index.html` doit exister. Ne pas appliquer ce fallback à `/api/`
ou à l'ensemble du site. Conserver `STUDIO_ORIGIN=https://studio.doemo.fr` pour
les contrôles d'origine : une origine HTTP ne contient pas `/app/orientation`.

Si le DNS et le certificat existent déjà, les réutiliser. Sinon, obtenir la
validation de l'utilisateur **avant** toute modification DNS ou configuration
serveur non déjà autorisée. Créer uniquement les entrées nécessaires à
`studio.doemo.fr`, jamais celles de `plans.doemo.fr`. L'émission de certificat
et la configuration de redirection HTTP→HTTPS doivent respecter la configuration
du serveur et de son éventuel reverse proxy/CDN.

Les cookies sont `Secure` et l'origine autorisée est fixée à
`https://studio.doemo.fr` : tester sur ce domaine en HTTPS. Ne pas changer ces
protections pour faire fonctionner un test sur une adresse IP en HTTP.

Valider la configuration puis recharger, sans redémarrer tous les services :

```sh
set -eu
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Le `set -e` évite le rechargement si la validation échoue. Ne recharger qu'après
une sortie `Syntax OK` et avec un plan de retour arrière disponible.

## 6. Vérifier après activation

- `https://studio.doemo.fr/` affiche la connexion, sans erreur PHP/JS.
- `/api/me.php` sans session retourne HTTP 401 et du JSON, pas le source PHP.
- `/api/login.php` en GET retourne HTTP 405.
- `/api/proxy.php` sans session retourne HTTP 401.
- `/api/templates.php?action=list` sans session retourne HTTP 401. Avec un compte
  de test autorisé, vérifier la liste de `doemo`, le téléchargement et les droits
  d'import dans un dossier d'essai, sans remplacer une trame utilisée.
- `/api/_s.php` est refusé en HTTP (403).
- Les chemins `/.git/HEAD`, `/engine/README.md` et `/docs/cahier-des-charges.md`
  ne sont pas accessibles (403/404). Aucun BAT ni archive n'est servi publiquement.
- L'origine de production peut joindre `https://gestion.doemo.fr` avec validation
  TLS active. Vérifier les permissions réseau sans désactiver les certificats.
- Un utilisateur interne autorisé peut se connecter et se déconnecter. Faire
  entrer ses identifiants dans le navigateur ; ne pas les demander dans le chat,
  les scripts ou les journaux. Ne pas réutiliser une session d'un autre utilisateur.
- Après connexion, `/app/` charge le build React et ses ressources sans erreur
  404 ; les requêtes au relais `api/proxy.php` respectent les droits de session.
- `https://studio.doemo.fr/app/orientation` affiche le module attendu, y compris
  après ouverture directe et rafraîchissement ; la route inconnue ne doit pas
  simplement afficher une page d'accueil à sa place.
- Vérifier les cookies `Secure`, `HttpOnly`, `SameSite=Strict`, les réponses non
  mises en cache et la révocation après déconnexion.
- Les autres vhosts et `plans.doemo.fr` continuent de fonctionner.

Les contrôles d'authentification doivent utiliser un compte de test autorisé.
La réponse de l'API Dolibarr et l'isolation des rôles n'ont pas été vérifiées dans
le cloud ; les rôles acceptés sont ceux définis dans `api/_s.php`.

## Sauvegarde, journaux et retour arrière

Conserver une copie de chaque livraison, les configurations Apache modifiées,
les certificats selon la politique du serveur et les données privées. Ne pas
copier les mots de passe, jetons ou fichiers de secrets dans l'archive du code.
Les logs Apache proposés sont `studio.doemo.fr_access.log` et
`studio.doemo.fr_error.log` sous le répertoire habituel d'Apache. Ne pas ajouter
de journalisation des mots de passe ou du jeton Dolibarr.

En cas d'échec, restaurer uniquement la livraison et le vhost de Studio concernés,
relancer `apache2ctl configtest`, puis recharger Apache. Ne pas toucher aux données
privées ni aux applications voisines lors d'un retour arrière.

La génération de lots de test est décrite dans [generation-linux.md](generation-linux.md).
La validation de production, la génération native multipage et les profils de
PDF non structurés restent à étendre. Le moteur ne nécessite pas de machine Illustrator.
