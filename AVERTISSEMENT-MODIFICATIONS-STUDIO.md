# ⚠️ Avertissement — modifications faites sur studio.doemo.fr (28/10/2026)

À lire **avant tout déploiement** de `/releves/`, `/redessin/` ou de l'application `studio-host`.
Ces changements ont été demandés par Julien et sont **en production**. Les redéploiements
précédents les ont déjà écrasés à deux reprises : merci de **ne pas les remettre**.

## 1. Relevé intelligent : pas de tableau de bord, pas de fenêtre de création

- L'application arrive **directement sur « Importer un relevé »** : elle ouvre le dernier projet
  de l'utilisateur, ou en crée un tout de suite (« Relevé du jj/mm/aaaa ») s'il n'en a aucun.
- Le bouton « ＋ Nouveau projet » crée le projet **sans fenêtre**.
- **Ne pas réintroduire** la page principale (`dashboard`) ni la fenêtre « Nouveau projet »
  (`showCreate`). Le code est dans `releves/web/src/studio.tsx`.
- Branche : `feat/releves-sans-tableau-de-bord` — **à fusionner** dans `codex/studio-mvp-editor`
  et `main`. Le test `releves/web/e2e/studio.spec.ts` clique encore sur « Créer le projet » :
  **à adapter**.

## 2. Bandeaux supprimés dans les pages cadrées

Julien ne veut plus de ces bandeaux, qui font doublon avec le menu du haut :

- **Structure bâtiment** (`/redessin/`) : bandeau « DOEMO Studio · Essai du redessin
  architectural · Validation humaine requise ». La balise `<header>` de `redessin/index.php`
  a été retirée. **Ne pas la remettre** dans votre source.
- **Relevé intelligent** (`/releves/`) : bandeau « DOEMO STUDIO · Production graphique ·
  Votre espace de travail » (`.studio-header`). Seul le bouton **Référentiel** est conservé.

Filet de sécurité côté site : `studio-host/FramedApp.jsx` (dépôt `doemo-app`, branche
`feat/studio-host`) injecte du CSS dans le cadre pour masquer ces bandeaux, même si le serveur
est redéployé avec l'ancien fichier.

## 3. Ces pages s'affichent dans un cadre sous le menu — plus de redirection

« Structure bâtiment » et « Relevé intelligent » sont affichées dans un `iframe` sous le menu du
haut (`studio-host/StructureBatiment.jsx`, `ReleveIntelligent.jsx`). **Ne pas revenir à
`window.location.href = '/redessin/'` ni `'/releves/'`** : cela masque le menu en plein écran.

Pour permettre le cadrage, sur le serveur (`51.75.250.104`) :

- `/etc/apache2/conf-available/doemo-redessin.conf` : `X-Frame-Options SAMEORIGIN` et CSP avec
  `frame-ancestors 'self'`, **uniquement** pour `/redessin/`.
- `/etc/apache2/conf-available/doemo-releves.conf` : `X-Frame-Options SAMEORIGIN` pour `/releves/`.
- Le reste du site reste en `X-Frame-Options: DENY` / `frame-ancestors 'none'`. **Ne pas retirer
  ces blocs, ne pas élargir le cadrage au reste du site.**
- `/var/www/studio/releves/index.php` injecte un `<style>` qui masque le bandeau de l'atelier
  (voir §2). Ne pas le remplacer par l'ancienne version sans reprendre cette injection.

## 4. Avant de déployer

1. Récupérer `doemo-app` / `feat/studio-host` (dernier commit connu : `372a31b`) **avant**
   de reconstruire et publier `/var/www/studio/app/`, sinon l'ancien menu (avec redirections
   plein écran) revient.
2. Fusionner `studio` / `feat/releves-sans-tableau-de-bord`.
3. Faire les sauvegardes dans `/var/backups/doemo-studio/`, **jamais dans `/var/www/studio/`**
   (des dossiers `app-backup-*` y ont été laissés : accessibles depuis le web, à déplacer).
4. Après déploiement, vérifier que `/redessin/index.php` ne contient plus `<header>` :
   `grep -c "<header>" /var/www/studio/redessin/index.php` doit afficher `0`.
