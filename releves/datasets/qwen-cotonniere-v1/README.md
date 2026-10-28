# Qwen — Bureaux de la Cotonnière

**12 propositions à relire, issues des deux PDF fournis le 28 octobre 2026.**
Site : Bureaux de la Cotonnière, 18 rue de la Cotonnière, 14000 Caen.

- `sources/333333.pdf` : relevé annoté, 2 pages ; RDC puis R+1, bâtiments A et B.
- `sources/CO26100349-1.pdf` : plan mis au propre, 1 page avec les niveaux 1 et 0,
  daté du 27 octobre 2026. Il porte **SPÉCIMEN** : confirmation utilisateur demandée,
  pas encore enregistrée dans ce lot.
- `revue.html` : détails et interprétations proposés, consultables localement.
- `images/` : rendu des pages et 12 recadrages des annotations, sans redessin.
- `draft-examples.json` : provenance, géométrie de recadrage, empreintes, champs API.
- `qwen-draft.jsonl` : conversations proposées ; `split=validation` provisoire.
- `propositions.json` : lectures de l’assistant, indications de référence et centres
  de recadrage normalisés. Elles ne sont pas des annotations humaines validées.
- `manifest.json` : empreintes de tous les fichiers.

Répartition : 3 commandes de désenfumage (DF), 3 coupures électriques (BT),
2 repères PI représentés par VEI dans ce dossier, poubelles, local ménage,
armoire pharmacie et sanitaires PMR. Les désignations DF/BT sont appuyées par la
légende du PDF de référence ; ce n’est pas une reconnaissance de pictogrammes COCO.
Le local ménage est une désignation de local, pas un identifiant de ressource SAI.
L’association aux fichiers SAI précis reste une étape séparée.

Les deux plans sont orientés différemment. Aucun transfert de coordonnées entre
le scan et le PDF mis au propre n’est prétendu validé. Les boîtes sont des recadrages
d’annotations, jamais des ancrages d’équipements. Toutes les réponses portent sur
la désignation et conservent `anchor=null`, `quantity=null`.

## Un seul groupe indépendant

Les bâtiments A et B et leurs niveaux restent dans **un seul groupe**, puisqu’ils
partagent le site et les mêmes PDF. Ils ne servent pas à remplir artificiellement
les trois lots. Avec Animalis, on dispose de **deux groupes** ; il manque encore un
troisième site corrigé et validé pour le test.

La réservation de ce dossier à la validation est une proposition. L’export actuel
DOEMO attribue les groupes selon son ordre déterministe : contrôler les lots réellement
obtenus avant la recette. Ne jamais répartir les recadrages de ce site entre plusieurs
lots, quelle que soit l’affectation finale retenue.

## Import et validation

Même procédure que le [lot Animalis](../qwen-animalis-v1/README.md) : importer les
PNG `images/cotonniere-*.png` comme documents d’un seul projet Cotonnière, reprendre
`example_fields` avec les bons `project_id`/`document_id`, créer en brouillon,
puis faire relire chaque image et chaque réponse avant validation. Les autres PNG
du dossier sont des aperçus des pages entières, pas les sources de ces exemples.
Conserver l’adresse du site et l’autorisation d’entraînement dans le projet.
Les conventions PI → VEI restent spécifiques au dossier.

Il n’y a aucun dataset figé accepté, aucun consentement enregistré automatiquement,
aucun entraînement lancé et aucune écriture distante. Ne pas transformer ce brouillon
en export d’entraînement en renommant les fichiers.

Reproduction locale avec les dépendances backend (Pillow/pypdfium2), depuis la racine :

```sh
python releves/scripts/prepare-qwen-cotonniere.py
```
