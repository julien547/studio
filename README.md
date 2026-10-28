# DOEMO Studio (studio.doemo.fr)

Espace interne DOEMO : page de connexion et socle de l'application d'orientation automatique des plans « Vous êtes ici ».

Adresse du module d'orientation : **https://studio.doemo.fr/app/orientation**.

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

## Moteur PDF indépendant — faisabilité en cours

Le module Python [engine](engine/README.md) inspecte les PDF et les métadonnées
natives AI24, et réalise des compositions vectorielles de diagnostic. Ses tests
sont exécutables indépendamment de PHP. `api/orientation.php` le raccorde à
l'espace connecté pour les diagnostics ; il ne produit pas de déclinaison
certifiée pour la production.
Après le retour du PDF incorrect, l'action web `compose` refuse la génération
avant toute création de fichier. Le banc d'essai exige `compose-diagnostic` :
voir le [constat et le correctif](docs/incident-generation-20261028.md).

- [Cahier des charges](docs/cahier-des-charges.md)
- [Audit du moteur Illustrator 1.0.13 et résultats PDF](docs/audit-moteur-1.0.13.md)
- [Référence Illustrator 1.0.14 : impression des pictogrammes et tests](docs/audit-moteur-1.0.14.md)
- [Contrat proposé pour l'export structuré](docs/contrat-export-structure.md)

Les rapports initiaux du BAT et des trames sont conservés dans `docs/`. Les
fichiers clients, les scripts de référence reçus et les sorties de diagnostic
restent hors de la racine publique et du dépôt source.
