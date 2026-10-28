# DOEMO Studio — audit et premier jalon, 28 octobre 2026

## État du dépôt et choix

Branche de travail : `codex/studio-mvp-editor`. Le dépôt contenait déjà un module
`releves/` exploitable : React 19.1.0, TypeScript 5.8.3, Vite 6.4.1, FastAPI,
SQLite, rendu PDFium, import de bibliothèque SAI, recalage et export JSX. Il n’était
pas nécessaire de recréer plusieurs applications, ni de changer de base de données
pour ce MVP. Les travaux précédents de reconnaissance et les scripts Animalis ont
été conservés. Les autres applications DOEMO n’ont pas été modifiées.

L’éditeur utilise SVG et les transformations DOM natives : les cadres et les points
restent des objets interactifs, sur un fond raster de référence. Cette solution ne
rajoute pas une dépendance graphique et reste adaptée au relevé fourni (87 objets
OCR). Un benchmark de milliers d’objets reste nécessaire avant industrialisation.

La base SQLite existante reste sur le serveur CPU, **jamais sur le volume FUSE du
Pod**. La migration `001_studio.sql` ajoute les révisions, comptes locaux, sessions,
travaux persistants et référentiel. Les originaux et bibliothèques restent privés.
Une migration PostgreSQL n’est pas réalisée à ce jalon ; elle pourra être justifiée
par le volume et la concurrence réels.

## Accès effectivement disponibles

- Dépôt local `julien547/studio`, dépendances et bibliothèque SAI déjà présentes.
- Environnement cloud CPU et Chromium local, sans Illustrator.
- Configuration OpenAI existante observée prête ; aucun appel OpenAI nécessaire ici.
- Aucun accès OVH ou RunPod configuré dans cette session. Les chemins `/opt/doemo-…`
  décrits par le client concernent son Pod, pas cet environnement Codex.
- Aucun modèle réinstallé, aucun démarrage GPU, aucune publication ni modification
  de reverse proxy de production.

## Fonctionnalités réalisées

- Authentification autonome optionnelle par cookie HttpOnly/SameSite, hachage scrypt,
  expiration, contrôle d’origine, limitation persistante des tentatives. Le mode
  PHP existant conserve les sessions Studio. La confiance dans les en-têtes d’acteur
  reste limitée à l’API privée ; le serveur autonome les remplace après connexion.
- Tableau de bord et création de projet : référence, client, adresse, bâtiment,
  type d’établissement, dessinateur renseigné. Ce dernier champ est descriptif ;
  les droits restent ceux du propriétaire et des administrateurs.
- Import multiple PDF/PNG/JPEG, glisser-déposer, originaux conservés, pages rendues.
  TIFF n’est pas accepté. Le rendu de travail est limité à 2 400 px sur le grand côté.
- Découpage manuel des niveaux sans BAT obligatoire, zoom, déplacement de vue,
  rotations par quarts de tour, cadres d’annotation, sélection multiple, déplacement
  des cadres et points, suppression, duplication, annuler/refaire et raccourcis.
- Annotation textuelle et position physique séparées (`bbox` / `anchor`). Aucun
  centre de texte n’est utilisé comme position implicite d’équipement.
- Sauvegarde automatique, révisions complètes, conflits de révision explicites,
  historique, restauration dans une nouvelle révision, export JSON des transformations.
- Référentiel administrable, association SAI et aperçu, six contrôles humains avant
  confirmation. La validation globale est réservée au responsable/administrateur.
- File de travaux persistante et worker séparé, états réels, GPU indisponible,
  relance explicite et récupération des travaux interrompus après expiration du bail.
- Import des trois formats réellement fournis. Les résultats IA restent archivés
  indépendamment des corrections ; leur intégration dans l’éditeur est explicite.
- Acceptation séparée des exemples pour apprentissage, autorisation de projet par
  administrateur, export COCO des seuls exemples admissibles. Aucun entraînement
  automatique, aucun modèle spécialisé déclaré prêt.
- Connecteur et atelier avancé Illustrator existants conservés, accessibles depuis
  le nouvel éditeur ; un BAT natif et des associations validées restent nécessaires.

## Contrat géométrique

La page rendue, redressée selon son orientation, est la référence canonique. Les
coordonnées persistées sont normalisées, origine haut-gauche. Un niveau stocke sa
région dans cette page et une rotation d’affichage. Les changements de zoom et de
rotation ne réécrivent jamais les coordonnées des annotations.

`coordinates.frames()` exporte les matrices page↔vue, page→raster, page→PDF (avec
CropBox et rotation intrinsèque) et page→repère Illustrator haut-gauche. Ce dernier
repère doit ensuite être associé à un plan de travail réellement validé. Il ne
remplace pas le recalage entre le relevé et un autre BAT.

Les dimensions de sortie IA doivent être explicites. Elles ne sont jamais déduites
du maximum des coordonnées d’une prédiction. L’import actuel concerne une image de
page entière ; un JSON obtenu sur un recadrage doit être remis dans la page d’origine
avant import. Les adaptateurs RunPod doivent retourner les coordonnées dans l’image
exactement transmise, ce que le worker vérifie.

## Résultats sur les fichiers fournis

Les PDF `mon-plan.pdf` et `mon-plan (1).pdf` et les JSON clients restent hors Git.
L’audit reproductible `scripts/audit-fixtures.py` a traité les fichiers fournis :

| Sortie | Résultat constaté |
|---|---|
| PaddleOCR | 87 textes avec polygones et scores ; ancres d’équipement nulles |
| Qwen quatre zones | 30 observations textuelles après regroupement par zone ; aucune position inventée |
| RTMDet COCO | 300 propositions ; score maximum 0,132414 ; aucune ≥ 0,40 ; zéro équipement créé |
| Référence RTMDet | 5 boîtes dépassent le cadre déclaré 2 381 × 1 683 ; superposition non autorisée |

Les dimensions 2 381 × 1 683 proviennent de l’image transmise dans cette conversation.
Les JSON RTMDet/PaddleOCR ne contiennent pas eux-mêmes de largeur/hauteur explicites.
La dimension originale exacte de l’inférence RTMDet reste à confirmer ; le programme
ne choisit pas une hauteur à partir de ses boîtes.

L’essai navigateur utilise le véritable PDF et des gestes de test pour vérifier
les mécanismes. **Les cadres et points de cet essai ne constituent pas des positions
PCF approuvées pour la production.** Les deux PCF du fichier Illustrator `planv4.ai`
avaient été visuellement vérifiées dans un travail antérieur ; cela ne certifie pas
l’export générique de tous les futurs projets.

## Tests et limites des phases suivantes

Les tests Python couvrent l’API historique et les nouveaux parcours : authentification,
autorisations, migration, versions, conservation des corrections, file de traitements,
formats IA, moteur indisponible, erreurs de référence et géométrie aller-retour.
Les tests navigateur utilisent un serveur authentifié réel, SQLite temporaire et
Chromium : connexion, projet, import, deux niveaux, annotation/position indépendantes,
déplacement, autosauvegarde, rotation, annuler/refaire, suppression, rechargement,
historique et téléchargement JSON. Le build TypeScript/Vite est vérifié.

Les adaptateurs RunPod sont du code d’intégration **non exécuté sur le Pod**. Leur
compatibilité avec les versions réellement installées de Transformers/PaddleOCR doit
être testée avant activation. Aucune inférence GPU ni qualité de reconnaissance
spécialisée n’est déclarée validée. Le module de fusion multimoteur, les passes OCR
avancées, l’apprentissage RTMDet, son évaluation et le registre des modèles restent
à développer après validation des contrats et constitution d’un corpus suffisant.

L’export natif général nécessite un test sur le poste Illustrator ; Linux ne crée
pas un AI natif. Les exports de revue JSON restent disponibles sans GPU, sans BAT
et sans SAI. Le paquet Illustrator reste soumis aux contrôles existants.

L’industrialisation reste à faire : installation OVH, HTTPS, exploitation supervisée,
politique de rétention/suppression, sauvegardes externalisées et restauration testée,
audit de sécurité, volumes/concurrence, gestion des utilisateurs en interface et
attribution fine des projets. Aucun de ces points n’est présenté comme déployé.

## Arborescence des ajouts

```text
releves/
  backend/doemo_releves/
    auth.py                # serveur autonome et sessions
    coordinates.py         # repères et matrices explicites
    ai_contracts.py        # formats des trois sorties IA fournies
    studio_api.py          # historique, catalogue, imports, export COCO
    queue.py               # file persistante et worker CPU
    migrations/001_studio.sql
  backend/tests/test_studio.py
  web/src/
    studio.tsx             # tableau de bord et atelier
    PlanCanvas.tsx         # interactions graphiques
    useEditor.ts           # sauvegarde, conflits, annuler/refaire
    editorGeometry.js      # transformations de la vue
    studio.css
    main.tsx               # atelier avancé antérieur conservé
  web/e2e/studio.spec.ts
  services/runpod/
    gateway.py             # API authentifiée, interpréteurs séparés
    infer.py               # adaptateurs des modèles existants
    check-existing.py      # vérification sans réinstallation
    requirements.txt       # dépendances du gateway uniquement
  scripts/
    standalone.sh
    backup.py
    audit-fixtures.py
  docs/mvp-audit.md
  docs/mvp-demarrage.md
```

Les dépendances d’exécution existantes sont conservées. Le frontend ajoute
`@playwright/test 1.56.1` et `prettier 3.6.2` en dépendances de développement, avec
lockfile. Le gateway utilise les versions FastAPI/Uvicorn/Pillow déjà déclarées
par le backend, dans un environnement distinct des modèles.
