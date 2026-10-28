# Moteur PDF Linux 0.3.0

Génération de lots de test, identification native Illustrator et découpage vectoriel
pour `https://studio.doemo.fr/app/orientation`. Aucun runtime Adobe n'est requis.
Voir [le guide de génération et déploiement](../docs/generation-linux.md).

Le profil courant génère tous les VEI des BAT Illustrator AI24 **à une page**
identifiés sans ambiguïté. Chaque PDF contient un seul VEI, sa flèche orientée
vers le haut, et les textes/pictogrammes de lecture redressés. Les opérateurs,
polices et images source sont conservés. Le ZIP n'est publié qu'après réussite
de tous les PDF. Les sorties restent marquées comme tests à contrôler visuellement.

## Installation et vérification

Depuis le checkout :

```sh
python3 -m venv /workspace/.venvs/studio-pdf
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip -r engine/requirements.lock
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip --no-deps -e ./engine
/workspace/.venvs/studio-pdf/bin/python -m pytest -q engine/tests
```

Les dépendances sont figées dans `requirements.lock`. Le backend de construction
setuptools est choisi par pip selon `pyproject.toml` ; le verrou ne couvre pas
encore toute la chaîne de construction. Le serveur utilise exclusivement
`/opt/doemo-studio/venv-pdf/`, pas le venv historique `/opt/doemo-studio/venv/`.

## Commandes

```sh
doemo-pdf templates-dir --client doemo
doemo-pdf inspect BAT.ai
doemo-pdf inspect-ai BAT.ai
doemo-pdf plan-batch BAT.ai --client doemo
doemo-pdf inspect-generation BAT.ai --client doemo
doemo-pdf generate-test-batch BAT.ai /chemin/prive/nouveau-lot --client doemo
# Uniquement si les niveaux doivent être délimités :
doemo-pdf generate-test-batch BAT.ai /chemin/prive/autre-lot --client doemo --levels niveaux.json
doemo-pdf levels-init BAT.ai
doemo-pdf levels-validate BAT.ai niveaux.json
doemo-pdf levels-preview BAT.ai niveaux.json selection.pdf --mode PE --level IDENTIFIANT
```

`generate-test-batch` crée les PDF, `rapport.json` et `plans.zip`. La destination
doit être nouvelle. Sans `--levels`, le dessin entier est utilisé, même si des
sélections ont été sauvegardées ailleurs. Avec cette option, chaque VEI PE doit
être associé à un niveau ; le PI ne reçoit jamais le clip d'un niveau isolé.

Les coordonnées sont en points PDF, origine en bas à gauche, Y vers le haut.
Les angles positifs sont antihoraires. Les trames sont dans
`/var/lib/doemo-studio/templates/<client>/`, collection `doemo` par défaut.
`DOEMO_TEMPLATES_ROOT` permet un emplacement explicite pour les tests.
La recherche utilise uniquement la collection choisie ; absence et ambiguïté
sont des erreurs. Le serveur PHP conserve les mêmes chemins privés.

`inspect` et `plan-batch` n'identifient que des étiquettes candidates, sur toutes
les pages. `inspect-ai` inventorie les identités natives sans interpréter du
PostScript ni lancer de JSX. `inspect-generation` vérifie ensuite les associations
entre identités natives et tracés PDF, les VEI complets et les zones de trames.

`levels-preview` reste un aperçu du découpage, sans orientation ni composition.
Il prend en charge plusieurs pages. La génération native multipage n'est pas
encore disponible. Les textes multilignes/fragmentés non associés et les formats
PDF hors du profil pris en charge sont refusés ; voir le guide pour les limites.

## Diagnostic historique

`compose-diagnostic` insère la page BAT entière dans une trame sans isoler les
VEI. Cet outil n'est pas appelé par le bouton de génération. L'ancienne action
HTTP `compose` reste bloquée pour éviter toute confusion avec ce diagnostic.
Les rapports et incidents antérieurs restent dans `docs/` à titre historique.

## Conservation et exécution

`scene.py` conserve chaque opération de dessin avec ses états graphiques,
masques et ressources. `bindings.py` compare les contours natifs aux tracés PDF ;
son échantillonnage n'est jamais utilisé pour dessiner le PDF de sortie.
`generate.py` applique les matrices, compose la trame, place les informations
fixes et produit le lot. Les glyphes architecturaux sont conservés ; fontTools
sert à mesurer leurs bornes pour leur ancre, pas à les redessiner.

Les groupes de transparence de page sont conservés. Les fichiers originaux et
ressources incorporées sont contrôlés par empreinte. Les clips de niveaux
restent vectoriels, y compris Bézier et chemins composés avec exclusions.
Un objet traversant un contour peut être coupé : contrôle visuel obligatoire.

L'API PHP authentifiée ajoute les droits de projet, le contrôle d'origine, un
verrou par BAT et les limites de processus. Elle exécute le lot de façon synchrone
avec un délai de 240 s ; une file persistante n'est pas encore implémentée.
Les BAT, résultats et archives restent hors du DocumentRoot.

## Licences

pikepdf : MPL-2.0 (qpdf) ; pypdf : BSD-3-Clause ; fontTools : MIT ; zstandard : BSD ;
skia-pathops : BSD-3-Clause. Conserver les notices des dépendances.
PyMuPDF sert uniquement aux audits indépendants dans le cloud ; il n'est pas
une dépendance du moteur livré.
