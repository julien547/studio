# Moteur PDF — étape de faisabilité

Outils serveur indépendants d'Illustrator pour `https://studio.doemo.fr`.
Adresse du module web cible : `https://studio.doemo.fr/app/orientation`.
Le frontend et l'authentification PHP existants sont conservés. Aucun endpoint de
production n'est branché sur ce banc d'essai.
L'API `api/orientation.php` expose l'inspection et un diagnostic explicite ;
son action `compose` refuse la génération, encore non implémentée. Voir le
[retour sur le PDF incorrect](../docs/incident-generation-20261028.md).

## Installation et tests

Depuis `/workspace/studio` :

```sh
python3 -m venv /workspace/.venvs/studio-pdf
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip -r engine/requirements.lock
/workspace/.venvs/studio-pdf/bin/python -m pip install --cache-dir /workspace/.cache/pip --no-deps -e ./engine
/workspace/.venvs/studio-pdf/bin/python -m pytest -q engine/tests
```

Les versions des dépendances installées sont figées. Le backend de construction
setuptools est choisi par pip selon `pyproject.toml` ; ce fichier n'est donc pas
encore un verrouillage reproductible de toute la chaîne de construction.

## Commandes

```sh
doemo-pdf templates-dir
doemo-pdf templates-dir --client client-a
doemo-pdf inspect /chemin/prive/BAT.pdf
doemo-pdf inspect-ai /chemin/prive/BAT.ai
doemo-pdf plan-batch /chemin/prive/BAT.ai --client doemo
doemo-pdf compose-diagnostic /chemin/prive/BAT.ai /chemin/prive/PI-A3-V.pdf \
  /chemin/prive/DIAGNOSTIC-PI.pdf \
  --zone 28.578 126.004 813.775 974.702 --direction 0 -1 --margin 12
```

Utiliser le chemin absolu `/workspace/.venvs/studio-pdf/bin/doemo-pdf` si le venv
n'est pas activé. `--page` commence à 1. Les coordonnées sont en points PDF,
origine en bas à gauche, Y vers le haut. Les angles positifs sont antihoraires.
`--reduce-only` interdit l'agrandissement. Les sorties et leurs rapports ne sont
jamais écrasés : choisir un nouveau nom pour chaque essai.

Le dossier fixe des trames DOEMO est `/var/lib/doemo-studio/templates/doemo/`.
Les collections personnalisées sont des sous-dossiers voisins, par exemple
`/var/lib/doemo-studio/templates/client-a/`. Le module `doemo_pdf.settings`
utilise la racine `/var/lib/doemo-studio/templates` par défaut et accepte la
variable `DOEMO_TEMPLATES_ROOT` pour une configuration explicite. La collection
par défaut est `doemo`. La future page Réglages PHP et le futur worker doivent
partager cette racine et sélectionner le client autorisé, sans mélanger les trames.
`deploy/studio.env.example` documente la variable ; ce fichier n'est pas chargé
automatiquement. La commande de diagnostic conserve son argument de fichier
explicite ; il n'y a pas encore de catalogue ni de page d'import branchée au CLI.

`inspect` retourne des **étiquettes candidates**, pas des VEI automatiquement
validés. `inspect-ai` lit les données natives AI24 compressées avec Zstandard,
sans exécuter le code PostScript ni les JSX. Il inventorie les noms et matrices
de symboles, mais ne prétend pas reconstruire le DOM Illustrator.
Il distingue `native_printable`, réglage propre du calque dans le profil AI24
observé, de `visible_in_default_pdf`. Un profil de calque inconnu donne `null` ;
l'inspection ne modifie aucun réglage d'impression ou de visibilité. Voir
l'[audit 1.0.14](../docs/audit-moteur-1.0.14.md) pour le cas des neuf extincteurs EXT.

`compose-diagnostic` place **la page BAT complète** dans la trame. Elle conserve
tous les VEI, textes, légendes et habillages source. Elle ne fait aucune
contre-rotation individuelle et ne représente pas une déclinaison métier.
Son seul objet est de vérifier les matrices, l'insertion vectorielle, les
ressources et la visibilité des calques. Le rapport porte toujours
`production_ready: false` et liste les défauts restants. Un code de sortie zéro
signifie que la commande de diagnostic a réussi, jamais que le plan est conforme.

`plan-batch` prépare toutes les étiquettes candidates du BAT et sélectionne les
trames par dossier client, type, format et orientation. Il ne crée aucun PDF et
ne certifie pas encore les associations VEI. Voir le
[parcours par lot](../docs/generation-par-lot.md) et son raccordement à la page.

La contre-rotation est implémentée et testée au niveau géométrique dans
`component_transform`. Son utilisation sur le BAT est bloquée tant que les
tracés exacts de chaque composant ne sont pas liés de façon vérifiable à son
identité. Faire tourner tout `Pictos` comme un bloc ne satisfait pas cette règle.

## Vérifications et limites

La composition incorpore le BAT sous forme d'un Form XObject et vérifie après
réouverture les empreintes de son flux et de ses ressources embarquées. Elle
préserve les groupes de transparence et transfère les paramètres de visibilité
des calques. Les originaux restent inchangés. Elle ne rasterise pas le dessin.
Ces contrôles sont nécessaires mais ne constituent pas une certification visuelle.

La version courante refuse notamment les fichiers chiffrés, les annotations et
actions de page, les fichiers sans représentation PDF, les unités personnalisées,
les pages ayant une rotation préexistante, les profils OutputIntents à harmoniser
et les trames multipages. Une page source d'un BAT multipage peut être choisie
explicitement. Aucun découpage de niveau automatique n'est effectué.

Les plafonds de taille et de décompression ne constituent pas un sandbox PDF.
Avant toute exposition aux uploads web, exécuter les traitements dans un worker
isolé avec limites CPU/mémoire/temps, stockage privé, contrôle d'accès et file
persistante. Ces services ne sont pas encore implémentés. Ne pas servir les
fichiers clients depuis la racine publique Apache.

## Licences retenues

- pikepdf : MPL-2.0, basé sur qpdf ; conserver les notices et examiner les
  obligations applicables aux modifications et à la redistribution.
- pypdf : BSD-3-Clause.
- fontTools : MIT.
- python-zstandard : BSD ; conserver également les notices de sa bibliothèque.
- PyMuPDF a servi à l'audit visuel dans l'environnement existant. Il n'est pas une
  dépendance du projet ; son régime AGPL/commercial doit être évalué avant ajout.

Les métadonnées natives extraites ne sont pas une nouvelle représentation
graphique. Pour une transformation individuelle fidèle, voir le
[contrat d'export structuré](../docs/contrat-export-structure.md).
