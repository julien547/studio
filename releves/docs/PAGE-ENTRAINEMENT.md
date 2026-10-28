# Livraison — page Entraînement IA

Cette session développe l’interface **et** le backend. La session de déploiement
est seule responsable des interventions sur OVH et RunPod. Aucun déploiement,
démarrage GPU ou entraînement facturable n’a été effectué pour cette livraison.

## Fichiers à reprendre ensemble

Branche : `codex/ai-training-backend` du dépôt `julien547/studio`.

| Fichier / dossier | Rôle |
| --- | --- |
| `releves/web/src/training/` | Page React, formulaires, éditeur de corrections et styles |
| `releves/web/src/PlanCanvas.tsx` | Éditeur partagé : axes médians, extrémités déplaçables et propositions IA |
| `releves/web/src/studio.tsx` | Accès administrateur depuis l’atelier et entrée `/entrainement` |
| `entrainement/index.php` | Point d’entrée PHP avec session et rôle administrateur |
| `releves/backend/doemo_releves/auth.py` | Même route en mode autonome |
| `releves/backend/doemo_releves/training.py` | API d’apprentissage persistante |
| `releves/backend/doemo_releves/migrations/003_training.sql` | Tables d’exemples, datasets, registre et audit |
| `releves/backend/doemo_releves/ai_contracts.py` | Propositions RTMDet neutres, jamais des équipements validés |
| `releves/backend/doemo_releves/studio_api.py` | Historique des analyses identifiable par moteur, document et page |
| `releves/web/e2e/training.spec.ts` | Parcours sur navigateur et backend local réel |

## Installer avec la session de déploiement

1. Récupérer la branche et examiner les changements par rapport à la version déjà
   déployée. Conserver les chemins, secrets et services existants. La passation
   générale contient des exemples de chemins, pas une invitation à les remplacer.
2. Sauvegarder SQLite et les documents avant le premier démarrage du backend qui
   applique `003`. Les migrations sont automatiques au démarrage du Store ; ne pas
   les exécuter une seconde fois manuellement. Aucune nouvelle migration n’est
   ajoutée par l’interface elle-même.
3. Construire le frontend avec les dépendances verrouillées :

   ```sh
   cd releves/web
   npm ci
   npm run build
   ```

4. Livrer le backend et le build `releves/dist` de la même révision.
   - Mode autonome : `/entrainement` et `/entrainement/` utilisent ce build,
     l’authentification `/session` et les API `/api/projects/...`.
   - Mode PHP : publier uniquement `entrainement/index.php` dans le dossier public
     `entrainement/`, à côté des dossiers publics `api/` et `releves/`. Le fichier
     lit le build indiqué par `DOEMO_RELEVES_DIST`, ou `releves/dist` à défaut.
     Garder les assets existants sous `/releves/assets` et le relais
     `/api/releves.php`. Apache peut rediriger `/entrainement` vers `/entrainement/`.
   - Si un proxy frontal réserve les routes `/app`, ajouter explicitement la route
     publique `/entrainement` vers le même service. Ne pas remplacer les routes
     existantes ni exposer directement l’API interne qui fait confiance aux en-têtes.
5. Le bouton **Entraînement IA** est présent dans l’atelier pour les administrateurs.
   Si un autre portail `/app` sert de menu principal, y ajouter un lien vers
   `/entrainement` ; son code n’est pas contenu dans ce module React.
6. Vérifier la page avec un administrateur, puis le refus avec un dessinateur.
   Faire la recette suivante avec un document autorisé, sans lancer de GPU.

## Parcours disponible

- Choisir Qwen, PaddleOCR, RTMDet ou l’espace architectural dans le menu latéral.
- Dans **Annotations**, sélectionner/créer un projet et importer PDF, PNG ou JPEG.
  Choisir document/page/niveau, rotation, zoom et éventuellement zone libre.
- Dessiner des boîtes ou un axe médian noir. Les extrémités des axes sont déplaçables.
  Les ouvertures coupent les axes à l’enregistrement. Corriger la catégorie,
  la transcription exacte et, pour un équipement, pointer séparément l’implantation.
- Cocher chaque annotation vérifiée. L’autorisation de réutilisation du projet
  est indispensable avant validation. Une modification remet l’exemple en brouillon.
- Enregistrer, valider ou rejeter avec motif. Les conflits conservent les corrections
  locales et proposent leur export JSON ; ils n’écrasent pas la révision concurrente.
- Dans **Datasets**, filtrer projet/catégorie/statut/date, rouvrir les exemples,
  sélectionner les validés, figer une version et télécharger son ZIP réel.
- Dans **Modèles IA / Qwen**, enregistrer un référentiel de conventions à partir
  du lot train. Son test demande un lot test distinct. Aucun poids n’est modifié.

Les analyses utilisent réellement `POST /projects/{id}/jobs`. Le lancement exige
une action explicite ; le contrôleur existant reste responsable du démarrage GPU.
Leurs résultats persistants se retrouvent dans **Analyses enregistrées**. Les boîtes
OCR/RTMDet apparaissent en surimpression ; les observations Qwen restent textuelles.
La copie vers les corrections est explicite et crée des annotations non vérifiées.
Les classes COCO RTMDet ne sont jamais automatiquement assimilées aux catégories DOEMO.

## Ce qui reste indisponible

Le frontend appelle les routes existantes et lit `/projects/training/capabilities`.
Le backend livré expose toujours `training=false`, `evaluation=false` pour les
poids et `deployment=false` : l’ordonnanceur d’entraînement web, les pilotes
PaddleOCR/Qwen compatibles et l’activation de versions GPU restent à implémenter
et à recetter. Le pilote RTMDet en ligne de commande n’est pas une file web.

Les formulaires et commandes de lancement, sauvegarde des poids, évaluation,
approbation, publication et rollback sont raccordés à leurs routes, mais restent
inactifs lorsque leur capacité manque. Ne pas forcer leurs flags pour les activer.
Un serveur GPU allumé ne suffit pas à rendre l’entraînement disponible.

La disponibilité réelle des inférences Qwen/PaddleOCR/RTMDet sur vos serveurs n’a
pas été vérifiée par cette livraison locale. La session de déploiement doit confirmer
les inférences et la santé du gateway avec la configuration privée existante.

## Vérifications locales exécutées

- `npm run build` : TypeScript et bundle validés.
- `npm test` : 8 tests de géométrie.
- Backend `python -m pytest -q` : 98 tests.
- `npm run test:e2e` : 5 parcours, dont l’atelier existant, avec authentification
  et une base temporaire réelle ; aucun remplacement des API d’apprentissage.
- Redémarrage du processus backend pendant le test OCR : données retrouvées.
- Test RTMDet : sortie de détection **rejouée dans la base de test**, sans GPU,
  pour vérifier superposition et copie explicite. Cela ne prouve pas l’inférence GPU.
- Syntaxe des deux entrées PHP vérifiée.
