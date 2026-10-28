# Démarrer et vérifier le MVP

Cette procédure concerne le dépôt de développement ou une installation CPU isolée.
Elle ne déploie rien sur `studio.doemo.fr`. Ne pas exécuter le serveur web ou SQLite
sur le volume FUSE RunPod.

## Dans l’environnement Codex déjà préparé

Depuis `/workspace/studio`, conserver le venv existant :

```sh
npm --prefix releves/web ci
npm --prefix releves/web run build
export DOEMO_RELEVES_DATA=/workspace/studio-mvp-data
export DOEMO_RELEVES_PYTHON=/workspace/.venvs/studio-releves/bin/python
export DOEMO_PUBLIC_ORIGIN=http://127.0.0.1:8082
"$DOEMO_RELEVES_PYTHON" -m doemo_releves.auth julien --role admin
bash releves/scripts/standalone.sh
```

La création du compte demande le mot de passe dans le terminal, sans l’afficher.
Aucun compte ou mot de passe par défaut n’est fourni. Elle refuse d’écraser un compte
existant. Le service écoute à `http://127.0.0.1:8082/releves/` **sur la machine qui
exécute la commande**. Cette adresse n’ouvre pas à distance la machine cloud depuis
le Mac du dessinateur ; il faut un accès privé configuré ou le déploiement HTTPS
isolé décrit plus bas. Aucun lien public n’a été publié pendant le développement.

Lancer un seul worker pour le MVP. Le script lance aussi le contrôleur GPU et arrête
ces deux processus avec le serveur. La base et
les documents persistent dans `DOEMO_RELEVES_DATA` après redémarrage.

Sur un serveur CPU neuf : utiliser un environnement dédié sous `/opt`, installer
les dépendances de `backend/requirements.lock`, puis le package backend en mode
éditable sans retélécharger les dépendances (`pip install --no-deps -e releves/backend`).
Le frontend utilise Node 20.19+ et le lockfile npm. Tesseract est nécessaire pour
le moteur OCR local. Chromium et Playwright ne sont nécessaires qu’aux tests.
Ne pas remplacer les installations système utilisées par d’autres applications.

## Vérification par le dessinateur

1. Se connecter, créer le projet **Animalis**, renseigner client et référence.
2. Importer `mon-plan.pdf`. Le PDF original est conservé ; choisir sa page.
3. Saisir **R-1**, cliquer **Découper un niveau**, tracer son rectangle. Répéter pour
   **RDC** depuis **Page entière**. Aucun mur n’est redessiné.
4. Sélectionner R-1, choisir **Annotation**, encadrer le texte PCF. Saisir le texte
   et la catégorie **Porte coupe-feu**.
5. Cliquer **Pointer sur le plan**, puis viser la porte réelle. Le cadre du texte
   et le point de la porte doivent rester distincts. Répéter au RDC.
6. Faire glisser un cadre ou son point, zoomer, tourner le niveau, utiliser
   Annuler/Rétablir. Le cadre déplace la région de texte ; le point déplace l’équipement.
7. Attendre **Enregistré**, recharger et rouvrir le projet : les corrections doivent
   être retrouvées. L’historique permet de relire ou restaurer les anciennes révisions.
8. Choisir la bibliothèque du projet dans le panneau sans sélection. Si elle n’est
   pas encore importée, ouvrir **Illustrator & SAI**, importer et contrôler les
   ressources natives, puis revenir. Sélectionner le pictogramme exact dans les propriétés.
9. Vérifier les six critères puis confirmer chaque placement. Un changement de
   catégorie/position/etc. retire le contrôle correspondant. Un responsable peut
   valider le projet lorsque tous les éléments sont confirmés ou rejetés.
10. **Exporter les données** fournit `doemo.studio-export/1`, les dimensions,
    transformations et annotations. Cet export de travail reste permis même si le
    GPU est arrêté ou certains éléments restent à vérifier.

Raccourcis hors champs de texte : `V` sélection, `H` déplacement, `Échap` annuler
l’outil, `Suppr` supprimer la sélection, `Ctrl/Cmd+Z` annuler,
`Ctrl/Cmd+Maj+Z` rétablir, `Ctrl/Cmd+S` enregistrer.

En cas de conflit avec un autre onglet, la sauvegarde s’arrête et propose de
conserver un JSON local. Recharger la révision serveur puis réconcilier les corrections ;
aucune stratégie « dernier arrivé gagne » ne doit écraser les changements concurrents.

## Vos sorties IA existantes

Dans **Analyses IA → Importer un résultat existant**, choisir le moteur, indiquer
les dimensions exactes de son image d’entrée et choisir le JSON.

- PaddleOCR : accepte les champs `rec_texts`, `rec_scores`, `rec_polys` (ou `dt_polys`),
  à la racine ou dans `res`. Le bouton **Ajouter à la revue** copie les observations,
  sans associer automatiquement la position du texte à un équipement.
- Qwen : format `zones[].elements[]`. Les observations sans coordonnées sont listées ;
  elles ne sont pas placées sur le plan. Les répétitions sont regroupées par zone.
- RTMDet COCO : `labels`, `scores`, `bboxes`. Diagnostic uniquement, aucun équipement
  créé, même si une proposition dépasse le seuil de 40 %.

La page fournie en image mesure 2 381 × 1 683 px ; 5 boîtes de votre JSON RTMDet sortent
cependant de ce cadre. Retrouver les dimensions réelles de l’image d’inférence avant
toute future superposition RTMDet. Ne pas remplacer la hauteur par un maximum calculé
à partir des prédictions.

## RunPod : gestion automatique

Le module de cycle de vie remplace la préparation manuelle initiale.
Suivre le [guide RunPod](runpod-lifecycle.md) pour le Pod **41m7oy6qjaj2ji** :
clé fournisseur sur OVH uniquement, gateway authentifié, vérification des trois
moteurs et archives de restauration sur le volume persistant.

Le dashboard propose le démarrage et l’arrêt aux administrateurs. Une analyse GPU
peut démarrer automatiquement le Pod ; aucune tâche n’est transmise avant les trois
sondes réussies. L’arrêt après 30 minutes exige une inactivité réelle des deux côtés
et l’absence de toute tâche en attente. La gestion reste désactivée jusqu’à sa
configuration sur OVH. Les essais de cette session simulent RunPod ; aucun Pod réel
n’a été commandé.

## Apprentissage

Dans l’historique, un administrateur peut autoriser la réutilisation du projet selon
la politique client applicable. Dans les propriétés, le dessinateur peut accepter
un exemple dont la catégorie et la position ont été vérifiées. Ces deux étapes sont
indépendantes de la simple sauvegarde d’une correction.

L’export COCO contient uniquement les exemples acceptés, le point d’équipement en
plus de la boîte d’annotation, les dimensions et le hash du document source. Les
images restent dans le stockage privé ; le JSON ne les publie pas. Grouper les splits
par bâtiment/référence et document, jamais par recadrage. Deux PCF ne constituent
pas un corpus suffisant pour entraîner ni évaluer RTMDet. Pipeline d’entraînement,
registre de modèles et activation contrôlée restent au jalon suivant.

## Illustrator

Ouvrir l’atelier **Illustrator & SAI**, choisir le projet, importer un BAT AI natif
avec compatibilité PDF, associer les niveaux/plans de travail et effectuer le recalage.
Vérifier les correspondances SAI et chaque placement avant **Préparer Illustrator**.
Sur le poste Adobe 2024+, exécuter le JSX du paquet avec le BAT ouvert, enregistrer
une nouvelle copie AI, la rouvrir, vérifier les calques, le nombre et la nature des
objets ainsi que leurs positions, puis importer le rapport.

Le succès antérieur des deux PCF dans `planv4.ai` concerne le correctif direct
Animalis. Il ne remplace pas ce protocole pour l’export générique. La bibliothèque
native peut encore présenter les difficultés de copie interdocuments MRAP observées ;
aucune validation native du connecteur général n’est annoncée depuis Linux.

## Tests reproductibles

```sh
cd releves/backend
/workspace/.venvs/studio-releves/bin/python -m pytest -q
cd ../..
npm --prefix releves/web test
npm --prefix releves/web run build
node releves/tests/illustrator-core.test.cjs
cd releves/web
DOEMO_TEST_PYTHON=/workspace/.venvs/studio-releves/bin/python \
DOEMO_CHROMIUM=/usr/bin/chromium npm run test:e2e
```

`DOEMO_TEST_SURVEY=/chemin/prive/mon-plan.pdf` remplace le fond synthétique du test
navigateur par un relevé réel. Le test crée un compte de test uniquement dans un
répertoire temporaire isolé, puis le supprime. Ne jamais utiliser ses identifiants
en exploitation. Les fichiers clients ne sont pas requis pour les tests du dépôt.

## Préparer OVH, sans toucher aux autres services

Choisir un utilisateur Unix dédié, un dossier privé de données, et un port loopback
libre (8082 proposé, disponibilité à vérifier). Sauvegarder la base existante avant
migration. Construire les assets, créer le compte administrateur, puis superviser
l’API, le worker et le contrôleur GPU dans trois services distincts. Le backend autonome est
`uvicorn doemo_releves.auth:standalone --factory --host 127.0.0.1 --port 8082` ;
le worker est `python -m doemo_releves.queue` et le contrôleur
`python -m doemo_releves.gpu`.

Configurer uniquement le vhost `studio.doemo.fr` décidé pour cette application,
avec HTTPS, une limite d’upload de 64 Mio et le proxy vers le port local. Le Host et
l’Origin doivent correspondre exactement à `DOEMO_PUBLIC_ORIGIN=https://studio.doemo.fr`.
Ne pas copier le dépôt, les données ou le backend dans une racine web publique.
Le mode historique PHP peut aussi être conservé : `api/releves.php` reste le relais
vers le socket Unix privé ; il accepte les nouvelles routes sous `/projects/`.
Ne jamais exposer directement `doemo_releves.api:app_factory` en TCP public.

La sauvegarde `scripts/backup.py /chemin/neuf` utilise l’API SQLite de sauvegarde
et copie documents/bibliothèques. Mettre en pause les imports et approbations SAI
pendant l’opération, chiffrer les sauvegardes externalisées, puis tester la restauration
vers un dossier isolé avant mise en service. Rétention/suppression : décisions et
outillage d’exploitation à finaliser avant production.
