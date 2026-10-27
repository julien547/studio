# DOEMO Studio (studio.doemo.fr)

Espace interne DOEMO : page de connexion et socle de l'application d'orientation automatique des plans « Vous êtes ici ».

## Fonctionnement
- `index.html`, `style.css`, `login.js` : page de connexion.
- `app/` : application React (menu du haut : Studio Plans, Orientation des plans), générée depuis le dépôt doemo-app (`npx vite build -c vite.studio.config.js`, branche `feat/studio-host`) et copiée dans `/var/www/studio/app`. Non versionnée ici.
- `api/proxy.php` : relais same-origin vers `api_doemo.php` (actions `studio_*` uniquement) ; le jeton de session reste côté serveur.
- `api/login.php` : vérifie le mot de passe auprès de l'API DOEMO (`session_login`, donc Dolibarr, anti-force-brute inclus) et n'accepte que les rôles internes `admin`, `administration`, `dessinateur`, `technicien`, `expedition`. Les comptes clients sont refusés et leur jeton révoqué.
- `api/me.php`, `api/logout.php` : état de session et déconnexion (révocation du jeton côté Dolibarr).
- `api/_s.php` : fonctions communes. Bloqué en accès direct par Apache.
- Session PHP : cookie `studio_sid` HttpOnly, Secure, SameSite=Strict, 12 h.

## Déploiement
Apache + mod_php, racine `/var/www/studio`. Voir `deploy/studio-doemo-fr-le-ssl.conf.example` (en-têtes de sécurité). Certificat Let's Encrypt via `certbot --apache -d studio.doemo.fr`.
Aucun secret n'est stocké dans ce dépôt.
