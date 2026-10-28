# DOEMO Studio (studio.doemo.fr)

**Déploiement et reprise par une autre session : [procédure complète](releves/docs/PASSATION-PRODUCTION.md).**

Le MVP d’édition des relevés est développé dans `releves/` :
[démarrer l’atelier](releves/docs/mvp-demarrage.md),
[consulter l’audit et les vérifications](releves/docs/mvp-audit.md).
Il fonctionne sans GPU et n’a pas été déployé sur le domaine de production.

Le nouveau module [Relevés & pictogrammes](releves/README.md) fournit l’import SAI,
la revue des annotations, le recalage, l’export contrôlé et le script Illustrator 2024+.
Il reste en validation : voir [les essais réels et leurs limites](releves/docs/essais-reels.md).

Espace interne DOEMO : page de connexion et socle de l'application d'orientation automatique des plans « Vous êtes ici ».

Adresse du module d'orientation : **https://studio.doemo.fr/app/orientation**.

## Fonctionnement
- `index.html`, `style.css`, `login.js`, `logo-studio.png` (logo sur fond transparent) : page de connexion.
- `app/` : application React (menu du haut : Studio Plans, Orientation des plans), générée depuis le dépôt doemo-app (`npx vite build -c vite.studio.config.js`, branche `feat/studio-host`) et copiée dans `/var/www/studio/app`. Non versionnée ici.
- `api/proxy.php` : relais same-origin vers `api_doemo.php` (actions `studio_*` uniquement) ; le jeton de session reste côté serveur.
- `api/login.php` : vérifie le mot de passe auprès de l'API DOEMO (`session_login`, donc Dolibarr, anti-force-brute inclus) et n'accepte que les rôles internes `admin`, `administration`, `dessinateur`, `technicien`, `expedition`. Les comptes clients sont refusés et leur jeton révoqué.
- `api/me.php`, `api/logout.php` : état de session et déconnexion (révocation du jeton côté Dolibarr).
- `api/_s.php` : fonctions communes. Bloqué en accès direct par Apache.
- Session PHP : cookie `studio_sid` HttpOnly, Secure, SameSite=Strict, 12 h.

## Déploiement
Apache + mod_php, racine `/var/www/studio`. Voir `deploy/studio-doemo-fr-le-ssl.conf.example` (en-têtes de sécurité). Certificat Let's Encrypt via `certbot --apache -d studio.doemo.fr`.
Aucun secret n'est stocké dans ce dépôt.

## Moteur PDF Linux — lots de test

Le moteur Python 0.3.5 génère tous les PDF et leur ZIP pour les BAT Illustrator
AI24 à une page dont les objets ont été identifiés. Chaque plan conserve un seul
VEI orienté vers le haut ; les textes et pictogrammes de lecture sont redressés.
La délimitation des niveaux est facultative et désactivée par défaut.
Voir [le fonctionnement, les limites et le déploiement](docs/generation-linux.md).
Les PDF sont destinés au contrôle visuel : aucune conformité universelle n'est
annoncée. Les BAT multipages et les PDF sans métadonnées natives exploitables
ne sont pas encore pris en charge par cette génération.
L'ancien `compose` reste bloqué ; `compose-diagnostic` est distinct du nouveau lot.

- [Cahier des charges](docs/cahier-des-charges.md)
- [Audit du moteur Illustrator 1.0.13 et résultats PDF](docs/audit-moteur-1.0.13.md)
- [Référence Illustrator 1.0.14 : impression des pictogrammes et tests](docs/audit-moteur-1.0.14.md)
- [Préparation de tous les plans et sélection du dossier client](docs/generation-par-lot.md)
- [Contours libres des niveaux et aperçus PDF vectoriels](docs/niveaux-libres.md)
- [Nouvelle référence Illustrator 1.0.16 et lot fourni](docs/audit-moteur-1.0.16.md)
- [Sortie réelle 1.0.14 reçue, correction du logo en cours](docs/reference-sortie-1.0.14.md)
- [Contrat proposé pour l'export structuré](docs/contrat-export-structure.md)

Les rapports initiaux du BAT et des trames sont conservés dans `docs/`. Les
fichiers clients, les scripts de référence reçus et les sorties de diagnostic
restent hors de la racine publique et du dépôt source.
