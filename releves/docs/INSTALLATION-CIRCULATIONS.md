# Installation — circulations vectorielles

Livraison de développement sur `codex/ai-training-backend`. Cette session n’a
effectué aucun déploiement OVH/RunPod ni aucune exécution Adobe Illustrator.

## Session de déploiement

1. Examiner le diff et sauvegarder la base SQLite et les documents existants.
2. Installer les dépendances du backend dans son venv dédié. Ajout :
   `shapely>=2.1,<2.2` (géométrie CPU). Aucun changement des modèles RunPod.
3. Livrer le backend avec la migration `006_circulations.sql`. Le mécanisme
   existant applique les migrations transactionnellement au démarrage. Cette
   migration crée les états, historiques et corrections des circulations.
4. Compiler `releves/web` avec `npm ci && npm run build`, livrer `releves/dist`
   et le point d’entrée `circulations/index.php`. Vérifier que le serveur web
   résout `/circulations/` comme les autres dossiers PHP de l’application.
5. Conserver la protection PHP existante devant `/api/releves.php`. Les routes
   commencent par `/projects/…` ; le backend reste sur son socket privé.
6. Vérifier un projet de recette avec un dessinateur et un administrateur.
   Un dessinateur ne doit pas accéder aux projets d’un autre propriétaire.
7. Distribuer ensemble les cinq scripts/fichiers listés dans la
   [notice utilisateur](NOTICE-CIRCULATIONS.md). Réaliser la recette native Adobe
   avant activation de cette fonctionnalité en production.

## Tests et périmètre

```sh
cd releves/backend
python -m pytest -q
```

```sh
npm --prefix releves/web run build
cd releves/web
npx playwright test
```

```sh
node releves/tests/circulations-core.test.cjs
node releves/tests/illustrator-core.test.cjs
```

Les tests de calcul couvrent rectangles, L/T/U, diagonales, seuils vers un bureau,
passages ouverts, obstacles avec trous, vert existant, halls, courbes, emprises,
murs incomplets, corrections, conflits de version et contrôle d’accès.
Le navigateur vérifie la revue, l’historique, la nuance et le téléchargement du
contrat. Ces tests ne simulent pas une réussite d’Illustrator.

Pour l’audit local du véritable aperçu PDF embarqué d’un AI, installer PyMuPDF
dans un environnement de développement séparé et lancer :

```sh
python releves/scripts/audit-circulations-ai.py /chemin/plan.ai --output /chemin/audit
```

PyMuPDF n’est pas requis pour le backend de production. Cet audit est en lecture
seule ; il produit un rapport et des images d’inspection, pas un AI natif.

## Contrat et conservation

- Source : `doemo.circulations-source/1`, coordonnées document Illustrator en
  points, axe Y vers le haut. La géométrie des différents niveaux ne doit pas
  se chevaucher. Les poignées de Bézier sont subdivisées avec erreur configurable.
- État : `doemo.circulations/1`, version de source SHA-256, régions et trous,
  catégories, confiance, revue humaine, nuance, timings et révision.
- Export : `doemo.circulations-export/1`, seulement les circulations validées,
  sans seuil visible, avec la nuance approuvée. Une source `pdf_audit` est refusée
  à l’export natif : seule une extraction `illustrator` est admissible.
- Les corrections sont dans `circulation_corrections`, avec historique append-only.
  L’exemple Qwen créé à partir d’une correction reste en brouillon et nécessite
  l’autorisation du projet et un fichier source identique.
- La source native n’est jamais écrasée. Aucun calque architectural verrouillé
  n’est déverrouillé ni supprimé par le connecteur.

Le cache réutilise un résultat dont source et règles sont identiques. Recalculer
après une correction humaine exige une confirmation et conserve l’ancien état
dans l’historique. Les opérations de géométrie n’utilisent pas le GPU.

## Recette Adobe à effectuer

Utiliser un des AI DOEMO véritables audités, une copie préparée et un poste équipé
d’Illustrator 2024+. Conserver les SHA-256 de l’original, de la copie de préparation,
de l’extraction et du résultat. Tester au moins : coordonnées décalées, plusieurs
niveaux, évidement, nuance CMJN et ton direct, liens, polices, fonds opaques,
calques verrouillés, reprise après retouche manuelle, enregistrement et réouverture.

Joindre la copie `.ai`, son rapport natif et les captures avant/après au dossier
de recette. Un rapport d’audit PDF ou un test Node ne remplace aucune de ces preuves.
