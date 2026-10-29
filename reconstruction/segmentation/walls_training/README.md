# Adaptateur d'entraînement des murs

Entraîne un modèle de **segmentation** (relevé client -> raster de murs) au contrat attendu par le moteur
`doemo_reconstruction` : `segmentation/run_onnx.py` (RGB NCHW float32 [0,1] -> logits NCHW, 11 classes) puis
`wall_module.reconstruct_mask` (axe médian). Aucune boîte RTMDet n'est un mur.

## Ce qui est appris, et ce qui ne l'est pas
- Classes apprises : `background`, `wall`. Les 9 autres classes du contrat ne sont pas étiquetées (le modèle les voit toujours à zéro).
- Vérité terrain : murs du dessinateur (BAT 1), alignés sur le relevé, **vérifiés un à un par Julien** (voir `jeu-releve-bat/`).
- Tout ce qui est hors du périmètre dessiné par le dessinateur est appris comme « pas un mur » : c'est voulu (le moteur géométrique
  actuel propose les murs des pièces voisines, des cadres, des cotes, du mobilier).

## Utilisation
```bash
# 1. archive (images PNG + walls.jsonl), mêmes splits par document que l'export de détection
python -c "from segmentation.walls_training import bundle; bundle.build('doemo-releves-v3-verifiees.zip','jeu_murs.jsonl','doemo-murs-v1-verifiees.zip')"
# 2. entraînement (poste : --device mps|cpu ; pod : --device cuda)
python -m segmentation.walls_training.train --bundle doemo-murs-v1-verifiees.zip --out sortie/ --size 1024 --epochs 60 --batch 4 --device cuda
#    courbe d'apprentissage : --train-fraction 0.25 / 0.5 / 1.0 (validation et test inchangés)
```
Sorties : `best.pt`, `walls.onnx` (vérifié contre PyTorch), `manifest.json`, `report.json` (historique, mesures, verdict).
Tests : `python -m pytest tests/test_walls_training.py` (9 tests, CPU, données synthétiques).

## Mesure (ne pas se faire gonfler par un modèle qui noircit le plan)
`metrics.length_scores` : rappel/précision/F1 en LONGUEUR couverte (12 px dans le repère 2048 px), **F1 strict à 6 px**, et
**`length_ratio`** = longueur prédite / longueur vraie (1 = idéal). Référence AVANT entraînement, moteur de la page « Redessin des murs »
(29/10/2026, 73 plans vérifiés) :

| | F1 | F1 strict | longueur prédite / vraie |
|---|---|---|---|
| 73 plans | 0,40 | 0,29 | x 3,1 |
| 11 plans de TEST | 0,38 | 0,25 | x 4,6 |

Le moteur actuel propose 3 à 4,6 fois trop de murs. `report.json > verdict.credible_improvement` n'est vrai que si le F1 ET le F1 strict
dépassent la référence ET si `length_ratio` est entre 0,5 et 2. Le split **test** n'est évalué qu'une fois, à la fin, sur le meilleur modèle
(choisi sur le F1 vectoriel de **validation**).

⚠️ Un essai de contrôle (3 passes, modèle minuscule, 256 px, CPU) donne F1 0,38 / strict 0,25 / x3,2 sur le test : il n'améliore RIEN, et le
verdict le dit. Les chiffres ne valent qu'avec un vrai entraînement (1024 px, GPU).

## Avant de brancher le modèle dans la page — NON FAIT
1. **Revue des droits** : `manifest.json > rights` (code, weights, training_data) reste à `commercial_use: false`. Aucune revue n'est simulée ;
   `run_onnx.checked_manifest` refuse tant que Julien n'a pas renseigné `commercial_use`, `evidence_url`, `reviewed_by`. Les données
   d'entraînement sont des relevés de CLIENTS de DOEMO : l'autorisation de réutilisation est à confirmer.
2. Brancher la sortie dans `extract.reconstruct` / le workbench (méthode `semantic_mask_medial_axis`) : aujourd'hui `models.segmentation` vaut `not_configured`.
3. Qualifier sur des plans jamais vus, hors des 73.

## Limites connues
73 plans (51 entraînement). Étiquettes de portes/fenêtres absentes (déduites des trous de murs, trop faibles). Le raster est calculé en 1024x1024 sans
conserver le rapport de l'image (contrat de `run_onnx.py`). Fragments : l'axe médian d'un masque bruité produit beaucoup de segments ; le nettoyage
`merge_collinear_fragments` (branche fix/redessin-nettoyage-murs) peut être appliqué après.
