# Plan unifié — structure du bâtiment et relevé intelligent

Cette extension ajoute un atelier commun au projet Relevés existant. Les murs et les annotations partagent la même source, la même page et la même révision. Elle ne crée pas de deuxième dossier de commande et ne remplace pas les moteurs de reconnaissance.

## Emplacement et dépôts

- Interface complète après déploiement coordonné : `https://studio.doemo.fr/app/plan-unifie`.
- Éditeur seul : `https://studio.doemo.fr/releves/?workspace=unified`.
- Backend, éditeur et export : dépôt `julien547/studio`, branche `feat/document-unifie`, dossier `releves/`.
- Menu Studio : dépôt `julien547/doemo-app`, branche `feat/studio-document-unifie`, dossier `studio-host/` ; lire `docs/PLAN-UNIFIE.md` dans ce dépôt.

Liens GitHub : [guide de l'hôte](https://github.com/julien547/doemo-app/blob/feat/studio-document-unifie/docs/PLAN-UNIFIE.md), [code du module](https://github.com/julien547/studio/tree/feat/document-unifie/releves), [modèles de déploiement](https://github.com/julien547/studio/tree/feat/document-unifie/releves/deploy), [règles de préservation du serveur](https://github.com/julien547/studio/blob/feat/document-unifie/AVERTISSEMENT-MODIFICATIONS-STUDIO.md).

Cette branche part de `f287365ccc62b7a4fdde61cbb0c726a406f723dd` (`feat/releves-sans-tableau-de-bord`). Son différentiel porte sur le module Relevés et son relais PHP. Il doit être intégré à la release serveur en conservant les travaux parallèles de reconstruction, et non utilisé pour remplacer ces derniers.

Les pages Structure bâtiment et Relevé intelligent restent disponibles. Le nouveau parcours garde le menu supérieur, l'ouverture directe du dernier projet et la création sans fenêtre intermédiaire. Les corrections d'interface décrites dans `AVERTISSEMENT-MODIFICATIONS-STUDIO.md` doivent être conservées.

## Utilisation

1. Ouvrir Plan unifié et importer une source PDF, PNG ou JPEG, ou reprendre un projet existant.
2. Choisir la page. Les niveaux peuvent recadrer/faire tourner la vue sans changer les coordonnées enregistrées.
3. Lancer l'analyse des murs et du relevé. Deux tâches distinctes utilisent la même page ; leur avancement et leurs erreurs viennent des traitements réels. Les équipements utilisent le moteur sélectionné dans le relevé.
4. Intégrer les propositions souhaitées au projet. Une analyse ne remplace pas les corrections déjà enregistrées.
5. Dessiner, déplacer ou corriger les murs et les ancrages. Les calques permettent de comparer avec la source ; annuler/rétablir et sauvegarde automatique restent communs.
6. Télécharger le PDF de travail, sans validation finale obligatoire. La largeur de page en millimètres est un format d'impression : elle ne calibre pas le bâtiment. Les pictogrammes conservent leur taille imprimée configurée.

Une annotation textuelle et l'emplacement physique d'un équipement sont deux objets distincts. Sans ancrage connu, aucun équipement n'est placé au centre de sa boîte de texte par défaut. Les annotations et ressources manquantes restent explicites dans la sortie de travail. Une bibliothèque SAI réellement importée et approuvée est nécessaire pour exporter ses vrais composants.

## Coordonnées et persistance

`ProjectState` conserve le schéma `doemo.review/1` et ajoute le champ optionnel `structure_pages`. Chaque structure appartient à un document source et à une page, avec l'empreinte de l'original, les dimensions et l'unité du repère. Les murs, leurs ouvertures et les identifiants des analyses intégrées restent dans cette révision JSON.

Les annotations restent en coordonnées normalisées dans la page source redressée. Le dessin convertit explicitement les axes de structure vers ce repère. Le zoom, le recadrage et la rotation sont des transformations de vue, sans réécriture des positions. L'export utilise la page source complète ; le recadrage de navigation n'est pas un choix de page d'impression.

La première intégration analyse le PNG redressé déjà produit lors de l'import, y compris pour les pages PDF. Cela évite une divergence de rotation EXIF ou de recadrage entre deux moteurs. L'extraction native des tracés PDF dans ce parcours commun reste à ajouter avec une transformation vérifiée ; elle reste disponible dans le parcours de redessin séparé.

Les anciens projets sont lisibles sans migration destructive. Les sauvegardes d'anciens clients qui omettent `structure_pages` doivent préserver les structures existantes. Les conflits de révision interrompent la sauvegarde plutôt que d'écraser les changements d'un autre utilisateur. Les analyses intégrées sont identifiées pour éviter qu'une seconde application du même résultat duplique les murs.

Supprimer un mur dans l'atelier le conserve comme rejeté dans l'historique : une nouvelle analyse identique ne doit pas le faire réapparaître. Restaurer une ancienne révision restaure la géométrie tout en conservant le registre actuel des analyses et les refus des murs absents de cette révision. Le serveur refuse de changer le repère d'une page existante ou d'effacer son registre d'analyses.

## Moteur de structure : configuration serveur

Le worker Relevés appelle le moteur `doemo_reconstruction` déjà installé, dans un processus séparé. Aucun téléchargement de poids ni accès GPU n'est déclenché par cette configuration. L'interface et les outils manuels restent utilisables si le raccordement n'est pas configuré.

Variables à définir côté serveur, dans la configuration privée de l'API et du worker Relevés :

```dotenv
# Chemins indicatifs à vérifier sur le serveur, jamais fournis par le navigateur.
DOEMO_STRUCTURE_PYTHON=/opt/doemo-redessin/venv/bin/python
DOEMO_STRUCTURE_MODULE_PATH=/opt/doemo-redessin/current/reconstruction
```

Le second dossier doit contenir le package `doemo_reconstruction`. L'exécutable doit pouvoir importer ses dépendances. Vérifier les permissions du compte système du worker Relevés sur ce code, ce Python et les fichiers de modèle ; ne pas ouvrir les permissions des documents à tous les utilisateurs.

Pour utiliser le modèle de murs déjà qualifié par l'autre service, le processus Relevés doit recevoir explicitement les mêmes variables privées `DOEMO_WALLS_MODEL_DIR`, `DOEMO_WALLS_PYTHON`, et, si nécessaire, `DOEMO_WALLS_WORKER`, `DOEMO_WALLS_MODE`, `DOEMO_WALLS_TIMEOUT`. Le service existant ne transmet pas automatiquement son environnement au worker Relevés. Les recopier/configurer sans publier les fichiers privés ni modifier la version du modèle actif. Sans modèle configuré, le moteur géométrique de référence ne doit pas être présenté comme une inférence ResNet.

Les avertissements du raccordement et les échecs sont conservés pour la revue. Le résultat de tâche enregistre les empreintes du raster analysé et du modèle lorsqu'il a été utilisé. Une largeur issue du masque d'axes n'est pas une épaisseur physique : son rendu conventionnel doit rester distingué d'une mesure du bâtiment.

## Export commun

Le nouveau PDF de travail rassemble, sur une même page source, la structure, les annotations et les équipements ancrés. Il conserve les composants graphiques des ressources Illustrator compatibles PDF, sans les remplacer par leurs aperçus PNG. Une ressource absente ou non compatible reste un repère explicitement signalé, pas un pictogramme inventé.

Trois calques PDF sont fournis : MURS, ANNOTATIONS À VÉRIFIER et PICTOGRAMMES INCENDIE. Le PDF contient tous ces calques et la page complète, même si la vue de travail en masque certains. Un rapport JSON joint conserve la révision, les coordonnées, les transformations et les placements incomplets. La taille des symboles correspond au plus grand côté du cadre PDF recadré, comme dans l'aperçu ; des marges blanches internes à une ressource peuvent réduire sa taille visible. Ce n'est pas une mesure Illustrator `visibleBounds`.

Le PDF est une sortie de travail non validée. Il ne constitue pas un fichier AI natif, une certification incendie ou un recalage sur un BAT externe. Le parcours avancé de recalage BAT et son export Illustrator restent distincts. La fidélité d'un import dans Illustrator nécessite encore une recette sur ce logiciel.

## Déploiement coordonné, à effectuer dans une session serveur autorisée

1. Lire les règles [PASSATION-PRODUCTION.md](PASSATION-PRODUCTION.md) et l'avertissement de racine. Faire l'inventaire des releases réellement installées et sauvegarder hors de la racine web. Les chemins et anciens identifiants RunPod des comptes rendus historiques ne sont pas des valeurs à rétablir.
2. Intégrer les modifications de la branche `feat/document-unifie` dans une release conservant les correctifs serveur plus récents. Ne pas remplacer l'ensemble de `julien547/studio` par cette branche : elle ne contient pas les travaux parallèles du moteur de reconstruction.
3. Installer l'API/worker Relevés depuis `releves/backend`, avec ses dépendances ; construire `releves/web`. Cette extension n'ajoute pas de base de données ni de migration destructive.
4. Publier ensemble backend, worker, bundle Relevés et `api/releves.php` (qui relaie maintenant aussi les PDF). Préserver la session PHP, le socket privé et les contrôles d'accès existants. Ne pas exposer l'API Python directement sur Internet.
5. Renseigner les variables du raccordement et redémarrer uniquement les services Relevés concernés après la fin des tâches en cours. Vérifier l'analyse d'un document synthétique avant toute analyse client.
6. Construire le dépôt `doemo-app`, branche `feat/studio-document-unifie`, avec `npx vite build -c vite.studio.config.js`, puis publier son bundle `/app` selon les règles de ce dépôt. Le menu ne devient visible qu'après ce build coordonné.
7. Vérifier la session, un projet existant, une nouvelle source, les deux analyses, le déplacement/correction, annuler/rétablir, sauvegarde/réouverture, le PDF commun et les deux anciennes pages. Vérifier aussi le refus d'un projet appartenant à un autre utilisateur.

La préparation de cette branche n'effectue aucun déploiement. Le retour arrière conserve la base et les documents ; privilégier un correctif ou une release compatible avec `structure_pages`, car un ancien serveur ne connaît pas cette extension. Ne jamais supprimer des structures ou restaurer une ancienne base pour masquer une incompatibilité d'interface.

## Vérifications de cette livraison

Recette locale du 2 novembre 2026 : **110 tests backend passent**, les tests JavaScript de géométrie et de restauration passent, ainsi que **deux parcours Chromium de l'éditeur** et **deux parcours Chromium du menu hôte**. Les deux builds passent ; la syntaxe du relais PHP et les différences Git ont été contrôlées.

Le parcours commun utilise une vraie session locale, un import PNG synthétique, les sauvegardes et téléchargements HTTP. Il vérifie l'alignement après rotation/recadrage, les déplacements, annuler/rétablir, la réouverture, un PDF à trois calques avec une ressource vectorielle synthétique, la taille imprimée, les rôles et l'isolation par propriétaire. Le bouton commun crée bien deux tâches sur la même source ; leurs résultats sont intégrés sans écraser les corrections ni dupliquer les objets à la réapplication. Ce parcours utilise des doubles de reconnaissance identifiés : il ne mesure pas la qualité IA.

Un essai distinct de l'adaptateur avec le moteur géométrique existant a produit deux propositions depuis une image synthétique, dans le repère 600 × 400 attendu. Aucun modèle ONNX privé ni serveur GPU réel n'a été exécuté dans cette session.

Commandes depuis ce dépôt, avec son environnement Python de test :

```bash
PYTHONPATH=releves/backend python -m pytest -q releves/backend/tests
npm --prefix releves/web ci
npm --prefix releves/web test
npm --prefix releves/web run build
# DOEMO_TEST_PYTHON désigne le Python contenant les dépendances backend.
# PYTHONPATH doit être absolu lorsque npm change de répertoire.
DOEMO_TEST_PYTHON=/chemin/venv/bin/python PYTHONPATH=/chemin/studio/releves/backend \
  npm --prefix releves/web run test:e2e -- e2e/unified.spec.ts e2e/studio.spec.ts
php -l api/releves.php
```

Les commandes du menu hôte sont dans `doemo-app/docs/PLAN-UNIFIE.md`. Aucun compte, mot de passe de test, fichier source client ou résultat privé n'est à installer en production.

## Limites actuelles

- La reconnaissance reste celle des moteurs raccordés ; réunir les pages n'améliore pas à lui seul la précision de l'IA.
- Le parcours commun ne fusionne pas automatiquement les projets déjà créés dans l'application Redessin séparée. Reprendre leur source dans le projet commun, sans remplacer les fichiers originaux.
- Les équipements sans ancrage ou sans ressource native doivent être complétés ; les conditions de validation métier restent inchangées.
- L'analyse commune porte sur la page sélectionnée. Les vues de niveau peuvent limiter l'affichage, pas transformer silencieusement l'analyse en traitement régional.
- Le PDF commun utilise la page complète et le format d'impression choisi. Aucun facteur de dimension réelle du bâtiment n'est déduit du format de papier.
- Les tests automatisés utilisent des documents et bibliothèques synthétiques. Ils ne prouvent ni le raccordement du modèle privé sur le serveur ni le comportement d'Illustrator.
