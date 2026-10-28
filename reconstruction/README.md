# DOEMO Reconstruction architecturale 0.3.6

**Installation et raccordement des trois IA : [procédure complète](../INSTALLATION-CONNEXION-IA.md).**
Lire l’[avertissement de production](../AVERTISSEMENT-MODIFICATIONS-STUDIO.md) avant
tout déploiement. Le redessin reste dans l’iframe sous le menu actuel, sans bandeau.
Cette livraison ne remplace ni `/app/` ni `/releves/`.

Prototype local ajouté à DOEMO Studio. Le modèle indépendant contient des axes, épaisseurs et ouvertures de murs ; les SVG contiennent des axes noirs ouverts, sans remplissage, groupés par mur et interrompus aux ouvertures. Toutes les détections sont des propositions à valider. Il ne s’agit pas encore du module complet de production.

La version courante conserve les [ouvertures lors de la fusion de deux bords en un axe médian](ovh/FUSION_MURS_OUVERTURES.md),
avec contrôle du type et de la position avant validation. Le
[contrôle des doubles axes](ovh/CONTROLE_DOUBLES_AXES.md) protège les exports validés.
Le raccordement signé aux trois IA et la procédure de déploiement sont livrés ; les
inférences réelles RunPod et la qualification du modèle spécialisé restent à faire.
144 tests Python et le parcours navigateur synthétique passent.

La version 0.3.0 ajoute un module web de test derrière la session DOEMO existante : import d’une page, file locale, correction et sauvegarde par utilisateur, SVG validé côté serveur et observations RunPod facultatives. La procédure de la session qui déploie est [Déployer sur OVH](ovh/DEPLOIEMENT_OVH.md). L’URL prévue après installation est `/redessin/` ; les poids et les plans clients sont exclus du dépôt.

Pour commencer les tests sur le serveur GPU, transmettre le [paquet de test d’inférence](runpod/TEST_DEPLOIEMENT.md) à la session responsable de l’image Docker. Cette session gère l’image et le cycle de vie RunPod ; les scripts de restauration restent uniquement un secours. Le paquet de test n’installe ni ne restaure les trois IA.

La version 0.3.1 ajoute le contrôle signé de connexion depuis Studio et une commande
de diagnostic utilisant la configuration du service OVH actif. Suivre la
[transmission OVH–RunPod](ovh/RACCORDEMENT_RUNPOD.md). Le raccordement réel et les
inférences GPU restent à exécuter par la session de déploiement ; une URL configurée
ne suffit pas à activer l’analyse. 64 tests locaux passent, dont un parcours des
appels signés jusqu’aux trois adaptateurs simulés, sans modification des murs.

La version 0.3.2 conserve les portions de bords non utilisées lors d’un appariement,
au lieu d’écarter un segment entier. Elle ajoute « Deux bords → un axe médian » dans
l’éditeur : correction explicite sur deux traces du même mur, portions restantes
conservées, ouvertures protégées, annuler/refaire. Les 88 tests Python passent.
Voir la [recette et les limites de cette correction](ovh/CORRECTION_AXES.md).

## Exécution

Installer dans un environnement séparé du moteur PDF existant :

```bash
python3 -m venv /opt/doemo-reconstruction-venv
/opt/doemo-reconstruction-venv/bin/pip install -e './reconstruction[test,service]'
# Facultatif : tesseract-ocr et tesseract-ocr-eng pour séparer les textes imprimés.
doemo-reconstruction reconstruct source.pdf projet.json --regions niveaux.json
doemo-reconstruction export projet.json svg-revue --preview
doemo-reconstruction export projet.json svg-valides
doemo-reconstruction training projet.json corrections-validees.jsonl
doemo-reconstruction connector projet.json import-illustrator.json
```

`niveaux.json` est une liste de régions `{id, name, source_page, bbox:[x0,y0,x1,y1]}`. Plusieurs niveaux peuvent partager la même page. Le repère reste celui de la page entière : x vers la droite, y vers le bas, dimensions de la page conservées. Les PDF utilisent les points du document ; une image seule utilise les pixels. Ce ne sont pas des dimensions du bâtiment. Aucune valeur métrique n’est ajoutée sans une cote explicitement validée.

`editor/editor.html` est la variante autonome : chargement JSON, correction et
sauvegarde locale ; le nom du valideur y est déclaratif. La variante web livrée
utilise `redessin/editor.js`, généré par `ovh/build_web.py`, les sessions PHP et le
service privé OVH. Elle conserve la CSP, l’identité serveur et les projets hors
du répertoire public. Suivre la procédure de déploiement pour cette variante.

## Géométrie et ouvertures

- PDF : récupération des tracés et matrices des Form XObjects avant analyse d’image. Les courbes restent dans les tracés bruts ; elles ne sont pas converties artificiellement en murs rectilignes. Les clips restent visibles dans la référence PDF rendue et doivent être contrôlés sur les candidats.
- Raster : suppression des pixels colorés, masquage OCR facultatif, détection de segments, recherche de paires de bords parallèles et épaisseur observée. Le scan couleur original reste intégralement disponible.
- Aucun comblement automatique d’un espace entre deux segments. Les portes et fenêtres sont des intervalles soustraits à un mur. Les axes gardent leur orientation, y compris diagonale. L’épaisseur graphique `stroke_width` ne modifie ni l’axe ni l’épaisseur détectée `thickness` ; cette dernière peut rester inconnue. Les raccordements demandent une vérification humaine.
- L’édition exige un auteur, journalise avant/après et annule la validation des objets modifiés. Les ouvertures doivent être revérifiées avant de modifier la longueur d’un mur. Un déplacement conserve les fractions de ses ouvertures.
- Pour deux traces parallèles représentant les faces d’un même mur, sélectionner la
  première, cliquer « Deux bords → un axe médian », puis sélectionner la seconde.
  La portion commune devient un axe à valider ; les portions non communes restent
  disponibles. Les ouvertures sont projetées et conservées sur les objets
  résultants, puis repassent en attente de validation. La commande refuse les traces
  sans recouvrement ou dont toute la portion commune est exclue par les ouvertures.
  Elle n’est jamais lancée automatiquement sur des murs voisins.
- Les SVG de revue incluent les propositions en traits noirs, marquées `data-status="pending"`. Le halo orange est réservé au contrôle dans l’éditeur et au PNG de comparaison. Les SVG validés incluent uniquement les murs approuvés. Le calque Référence est présent mais masqué. Les autres calques sont préparés ; les portes sont actuellement des réservations de passages, sans vantail inventé. Les escaliers, fenêtres détaillées et pièces ne sont pas encore reconstruits automatiquement.

## Modèles et droits

`vision.py` réutilise le modèle vision DOEMO configuré via les variables existantes, uniquement si son appel est autorisé pour le document. Les réponses sont des observations sans pouvoir d’approbation. Sur Animalis, des boîtes proposées se sont révélées mal localisées : elles sont conservées comme résultat diagnostic et exclues de la construction géométrique. Les zones de contrôle affichées viennent de la lecture visuelle du scan.

Le worker `segmentation/run_onnx.py` se lance dans son propre environnement avec ses dépendances. Il exige un manifeste vérifiant l’empreinte SHA-256, les contrats de tenseurs et les droits commerciaux séparés du code, des poids et des données. Il produit un masque sémantique sans validation automatique. **Aucun modèle spécialisé n’est installé et ce worker n’a pas été testé avec des poids réels.** Le post-traitement de masques `wall_module.reconstruct_mask` est maintenant disponible et testé sur masques synthétiques ; la chaîne avec un modèle réel reste à qualifier.

CubiCasa5K est sous CC BY-NC 4.0. Le code FloorplanTransformation est sous MIT ; vérifier séparément poids et données. Voir la [feuille de route](../docs/feuille-de-route.md).

## Illustrator

`connector` refuse les niveaux non confirmés et les niveaux sans mur approuvé. Il produit un contrat versionné, sans contacter de service local inconnu. `illustrator/import-architecture.jsx` importe ce contrat dans des documents Illustrator distincts par niveau, avec les coordonnées originales, groupes de murs, calques et référence embarquée masquée. Aucun fichier AI existant n’est écrasé. Le script exige un parseur JSON natif ou fourni par le connecteur et ne fait aucun `eval` du contenu du fichier.

Le connecteur réel n’est pas présent dans ce checkout : le transport et le pilotage de ce JSX restent à adapter, puis à tester dans Illustrator. Les tests Linux ne prouvent pas le comportement d’Adobe. Un SVG peut être ouvert pour contrôle dans Illustrator, mais cela ne constitue pas une recette du connecteur.

## Vérification

Les tests de comparaison géométrique utilisent aussi **Node.js 22 ou supérieur**.
Les dépendances Python de recette sont celles des extras `test,service` ci-dessus.

```bash
cd reconstruction
python -m pytest -q
```

Tests : paires diagonales, respect des coupures, intervalles d’ouvertures, raccords géométriques à épaisseurs différentes, séparation revue/validé, validation de cotes, rejet des données invalides, conservation des coordonnées des niveaux, extraction d’un PDF vectoriel réel généré pour le test. Les corrections sauvegardées par l’éditeur peuvent être rechargées par le moteur Python.

Le parcours navigateur livré utilise uniquement des géométries synthétiques.
Depuis la racine du dépôt, dans un environnement de recette séparé :

```bash
python3 reconstruction/ovh/build_web.py
npm install --prefix /tmp/doemo-redessin-ui-tests --no-audit --no-fund playwright@1.62.1
/tmp/doemo-redessin-ui-tests/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/doemo-redessin-ui-tests/node_modules node reconstruction/tests/browser/median-openings.cjs
```

Si Chromium est déjà installé, son exécutable peut être fourni via
`DOEMO_TEST_CHROMIUM` à la place du téléchargement. Le test démarre un serveur
local temporaire sur un port libre, affiche son rapport JSON puis ferme le
navigateur et le serveur. Il n’utilise aucun compte Studio, plan client ni GPU.

Le plan Animalis, les projets générés et les captures ne sont pas stockés dans le dépôt source. Leur SHA-256 figure dans le projet JSON pour rattacher les corrections au bon document.

## Compatibilité avec Studio Plans existant

La branche `feat/studio-host` de `julien547/doemo-app` contient déjà Studio Plans et un moteur déterministe v0.24. Le prototype de ce répertoire est un banc distinct ; il ne remplace ni cet éditeur ni ses contrôles de qualité, ses ouvertures, ses révisions et ses validations serveur.

L’adaptateur `studio_adapter.py` relit son contrat d’analyse v3, transforme explicitement les coordonnées du canevas image vers les points de page et conserve les ouvertures et les épaisseurs. Il refuse d’écraser un niveau contenant déjà des murs et ne fabrique pas d’épaisseur pour les propositions sans épaisseur connue. Il ne transfère aucune approbation.

Un essai séparé sur Animalis avec le moteur existant v0.24 a produit 264 propositions sur R−1 et 133 sur RDC, aucune ouverture automatiquement reconnue. Les sorties et une vue dans le même éditeur sont livrées pour comparaison. Le comptage ne mesure pas la précision ; aucun classement n’en est déduit. Les 113 et 114 propositions du banc simple restent un jeu distinct.

## Module spécialisé et RunPod

Les spécifications RunPod remplacent les anciennes hypothèses OVH GPU/Ollama. Le redessin des murs constitue un module spécialisé indépendant de RTMDet. Qwen3.5-9B et PaddleOCR apportent de l’interprétation et des zones textuelles ; le checkpoint RTMDet COCO ne détecte pas les murs. Voir [raccordement, restauration et exploitation](runpod/README.md).

L’éditeur ajoute coupe, correction/suppression d’ouverture, annuler/refaire avec révisions croissantes, réglage du trait graphique et épaisseur détectée facultative. Le contrat Illustrator passe à `/2` ; ne pas envoyer les anciens polygones `/1` au nouveau JSX.

Essai initial : exclusivement page 1 de `2(2).pdf`, PDF cinq pages dont la première est un scan, sans tracé vectoriel récupérable. Le moteur v0.24 produit 400 candidats bruts. Le regroupement expérimental des contours propose 101 axes, dont 37 diagonaux ; 221 traces isolées restent non interprétées. Zéro ouverture automatiquement reconnue et zéro mur validé. Les coordonnées du document sont préservées ; seul le PNG de comparaison est tourné pour la lecture. Ces chiffres décrivent les sorties, pas leur exactitude. Les murs manquants, faux murs, passages et raccords nécessitent une revue. Aucun appel RunPod n’a été effectué.

Vérifications initiales (0.3.0) : 50 tests Python et parcours Chromium de l’éditeur (style indépendant, coupe, annuler/refaire, correction d’ouverture, sauvegarde et export SVG). Les tests de service utilisent des doubles ; ils ne prouvent pas un déploiement GPU.

Le correctif 0.2.1 ajoute un inventaire de l’hôte et du volume persistant avant restauration, distingue les liens Python cassés des venvs absents, contrôle l’espace disque et vérifie l’identité du worker après migration. Les trois environnements sont maintenant restaurés selon le dernier rapport du propriétaire ; les inférences restent à vérifier depuis le raccordement réel.
