# Reconnaissance et pose des pictogrammes — phase 1

**Déploiement et reprise par une autre session : [procédure complète](docs/PASSATION-PRODUCTION.md).**

## Nouvel atelier Studio — MVP du 28 octobre 2026

Le module comprend maintenant un tableau de bord, une connexion autonome optionnelle,
un éditeur de niveaux et d’annotations fonctionnant sans GPU, une sauvegarde automatique
versionnée, les imports des sorties Qwen/PaddleOCR/RTMDet et une file de travaux persistante.

- [Gestion du GPU RunPod et configuration de la clé sur OVH](docs/runpod-lifecycle.md)
- [Contrat backend d’apprentissage IA](docs/CONTRAT-ENTRAINEMENT-IA.md) et [reprise avec accès SSH](docs/REPRISE-BACKEND-IA.md)
- [Démarrage et parcours utilisateur](docs/mvp-demarrage.md)
- [Audit, fonctionnalités vérifiées et limites](docs/mvp-audit.md)

Le nouvel atelier utilise le backend et la bibliothèque existants. L’atelier avancé
de recalage/Illustrator reste accessible. Aucun déploiement OVH ou RunPod n’a été effectué.

Les sections suivantes documentent l’intégration PHP et le connecteur antérieurs.

Module indépendant de l’orientation et des déclinaisons VEI. Il conserve les originaux,
propose des annotations à partir de pixels réellement analysés et organise une revue
avant export vers **Illustrator 2024+**. Aucun service Linux ne prétend écrire un AI natif.

Le module est développé et testé localement ; il n’est **pas déployé** sur
`studio.doemo.fr`. Les essais réels ne constituent pas une validation de production.
Voir [les résultats et limites](docs/essais-reels.md).

## Installation

Prérequis : Linux, Python 3.11+, Node 20.19+ ou 22.12+, PHP 8.2+ avec curl,
sessions et mbstring, Tesseract 5 dans le PATH. `pypdfium2` fournit le moteur de
rendu PDF ; OpenCV fournit la vision géométrique. Il n’y a pas de dépendance PyMuPDF.

```sh
cd /workspace/studio
bash releves/scripts/install.sh
DOEMO_RELEVES_DATA=/workspace/studio-releves-data bash releves/scripts/dev.sh
```

L’installation du module est séparée du venv PDF existant. Le script de développement
utilise par défaut le PHP local préparé par l’onboarding ; ailleurs, définir
`DOEMO_PHP=/chemin/vers/php`, `DOEMO_RELEVES_VENV`, les chemins de données/run/public
et le port. L’installation système de PHP et de Tesseract dépend du serveur et ne
doit pas être remplacée globalement par le script du module.

Le développement écoute uniquement sur `127.0.0.1:8081`. L’API Python est accessible
exclusivement sur un **socket Unix privé**. La page `/releves/` et le relais
`/api/releves.php` réutilisent les sessions Studio et refusent l’accès aux autres rôles.
Les cookies Secure et le contrôle de l’origine de production sont conservés. Le
parcours authentifié en navigateur requiert donc l’intégration HTTPS Studio ; les
essais cloud utilisent exclusivement des sessions synthétiques locales.

L’API privée fait confiance aux en-têtes d’acteur envoyés par ce relais, protégés par
les permissions du socket. **Ne jamais l’exposer avec `--host 0.0.0.0` ni par un proxy
public direct.** Les projets appartiennent à leur auteur ; les administrateurs peuvent
les reprendre. L’import et l’approbation des ressources SAI sont réservés aux administrateurs.

## Bibliothèque fournie

Les deux parties sont dans `bibliotheque pictogrammes/` à la racine du dépôt.
Les réunir dans cet ordre, hors de la racine publique :

```sh
python3 releves/scripts/reassemble-library.py \
  'bibliotheque pictogrammes/Legende-SAI.cclibs.part-aa' \
  'bibliotheque pictogrammes/Legende-SAI.cclibs.part-ab' \
  --output /workspace/studio-releves-audit/Legende-SAI.cclibs
/workspace/.venvs/studio-releves/bin/doemo-releves \
  --data /workspace/studio-releves-data import-library \
  '/chemin/prive/DOEMO_Studio_inventaire_bibliotheque_SAI.json' \
  --archive /workspace/studio-releves-audit/Legende-SAI.cclibs
```

L’interface accepte également l’inventaire et l’archive `.cclibs` réunie. Les parties
ne sont pas individuellement des archives. Le catalogue distingue les graphiques,
les couleurs, les styles et le texte. Les homonymes restent identifiés par UUID.
Un inventaire seul est provisoire : il ne débloque ni l’approbation ni l’export.

L’importeur vérifie les 290 identifiants, les noms/types du manifeste DCX, les chemins,
les tailles et les empreintes des composants natifs. Il n’extrait que les AI nécessaires,
dans un dossier privé neuf. Il refuse les liens, les traversées, les noms ambigus, les
archives chiffrées et les limites excessives. Limites : 512 Mio compressés, 1 Gio total,
64 Mio par membre, 5 000 membres, ratio maximum 200. Les autres formats de manifeste
inconnus sont refusés explicitement.

## Reconnaissance et OpenAI

Le mode local combine OCR, composantes colorées, géométrie des marques et contexte
textuel. **Il ne distingue pas fiablement toutes les annotations manuscrites du dessin
coloré imprimé.** Aucun code couleur universel ni équipement n’est déduit d’un point
rouge. Les pointes de flèche non établies ont un ancrage nul.

Le mode multimodal utilise une API Chat Completions avec vision et réponse JSON
contrôlée. Configurer dans le service Python :

- `DOEMO_VISION_ENDPOINT=https://api.openai.com/v1/chat/completions`
- `DOEMO_VISION_MODEL=gpt-4.1` (modifiable selon les modèles autorisés du compte)
- `DOEMO_VISION_API_KEY`, renseignée dans un stockage sécurisé, jamais dans le dépôt.

La destination HTTPS `api.openai.com` doit être autorisée. La clé et ces exigences
ont été ajoutées au nouveau brouillon cloud ; **aucune valeur de clé ni publication
n’a été effectuée**. Les scripts d’onboarding précédents n’ont pas été réappliqués.
L’activation du brouillon, avec sa clé et les changements réseau, puis le redémarrage
du service seront nécessaires avant un essai réel. Aucun appel IA n’est présenté
comme vérifié avant cela. Le mode est choisi explicitement avant l’envoi de l’image.

Les originaux ne sont pas envoyés par l’import : seule la page de reconnaissance
rendue est transmise lors d’une analyse multimodale demandée. Les consignes présentes
dans les images sont traitées comme des données. Toutes les propositions IA restent
non validées. Les améliorations ultérieures (deskew automatisé, déplis et segmentation
manuscrite spécialisée) ne sont pas annoncées comme réalisées.

## Exploitation et déploiement à préparer

Voir [le guide utilisateur](docs/utilisation.md) et [le contrat d’échange](docs/contrat.md).
Le build React est dans `releves/dist/` après `npm run build`. Pour une activation
HTTPS Studio, publier uniquement le point d’entrée `releves/index.php` et les assets
compilés ; définir `DOEMO_RELEVES_DIST` pour que PHP lise le HTML construit depuis
son emplacement privé. Publier aussi `api/releves.php` et le faire pointer vers le
socket privé du service. Ne pas copier `backend`, `illustrator`, les bibliothèques,
Git, les BAT ou les relevés dans le DocumentRoot. Aucune règle SPA sur les anciennes
routes n’est modifiée. Le service doit s’exécuter avec un compte dédié et un groupe
commun avec PHP ; adapter le socket à `0660` en production, son répertoire à `0750`,
et préserver les fichiers de données en privé. L’environnement de développement
utilise `0600` car PHP et Python y partagent le même compte.

Les décodeurs et l’OCR tournent dans un processus séparé : 3 Gio d’espace d’adressage,
150 s CPU, 180 s de délai et 128 Mio par fichier de sortie ; une seule opération à la
fois par processus API. Ce n’est pas un conteneur de sécurité complet. Avant exposition
de fichiers non fiables en production, exécuter ce service avec un confinement système,
un stockage dédié, des quotas et une politique réseau limitée aux destinations requises.
Prévoir sauvegarde SQLite + documents + bibliothèques et rétention des exports ZIP.

## Vérification

```sh
cd /workspace/studio/releves/backend
/workspace/.venvs/studio-releves/bin/python -m pytest -q
cd /workspace/studio
node releves/tests/illustrator-core.test.cjs
npm --prefix releves/web test
npm --prefix releves/web run build
/workspace/.local/bin/php -l api/releves.php
```

Les tests du cœur JSX vérifient les calculs, l’échange, SHA-256 et la comparaison des
placements. Ils **n’exécutent pas le DOM Adobe**. Le test natif E (import réel, calques,
sauvegarde puis réouverture AI) reste à effectuer dans Illustrator sous licence.

### Page Entraînement IA

Page administrative `/entrainement` avec quatre moteurs et quatre onglets,
raccordée au backend existant. [Livraison et installation](docs/PAGE-ENTRAINEMENT.md).
Les capacités GPU indisponibles restent explicites ; la sauvegarde des corrections
et les datasets fonctionnent sans GPU.

Le [raccordement asynchrone RTMDet](docs/ENTRAINEMENT-RTMDET.md) ajoute la file OVH,
les contrôles du gateway et la migration `004`. Activation uniquement après recette
GPU réelle par la session de déploiement ; aucune activation de poids en production.

La [comparaison Qwen sur plan](docs/COMPARAISON-QWEN.md) permet de confronter les
sorties avec/sans un référentiel versionné. Elle conserve un avis humain et ne
publie aucun modèle. Installer la migration `005` et le gateway compatible ensemble.

Le [pilote de reconnaissance PaddleOCR](docs/ENTRAINEMENT-PADDLEOCR.md) réutilise
la file commune, avec profil accepté indépendant, checkpoints poids/optimiseur
et métriques CER/WER. Recette GPU requise ; aucun poids actif n’est remplacé.

### Pose des pictogrammes

Le [parcours reconnaissance → SAI → Illustrator](docs/POSE-PICTOGRAMMES.md) relie
l’analyse multimodale à des propositions d’implantation, aux aperçus SAI déplaçables
et au paquet d’export Illustrator. Les positions ambiguës et les correspondances
restent à contrôler ; les ressources vectorielles doivent être importées et approuvées.
