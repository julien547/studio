# Simulation de l'ordonnanceur (28/10/2026)

**Ce n'est pas une mesure du GPU.** C'est le vrai code de l'orchestrateur, piloté par une horloge
simulée, avec des durées de calcul **supposées** (Qwen 20 s, OCR 6 s, détection 4 s par page).
Chaque dessinateur lance toutes les ~60 s une analyse (3 tâches) ; une autre application dépose en
plus un lot de 20 tâches au début. Reproduire : `python bench/simulate.py`.

Le scénario « concurrence » suppose que 4 tâches en parallèle tiennent en VRAM et que chacune est
2× plus lente : **hypothèse à vérifier sur le pod** (étape 7), pas une promesse.


### État actuel : 1 GPU, 1 tâche à la fois
| dessinateurs | tâches interactives | attente médiane (s) | attente p95 (s) | attente max (s) | lot terminé après (s) |
|---|---|---|---|---|---|
| 1 | 48 | 19.8 | 88.0 | 125.0 | 406.0 |
| 3 | 135 | 455.0 | 671.5 | 718.5 | 520.0 |
| 5 | 154 | 725.5 | 1164.0 | 1196.5 | 606.0 |
| 10 | 160 | 835.0 | 1430.5 | 1489.0 | 600.0 |

### Concurrence : 1 GPU, 4 tâches en parallèle, chacune 2× plus lente (HYPOTHÈSE)
| dessinateurs | tâches interactives | attente médiane (s) | attente p95 (s) | attente max (s) | lot terminé après (s) |
|---|---|---|---|---|---|
| 1 | 48 | 0.0 | 7.5 | 12.0 | 242.0 |
| 3 | 135 | 7.0 | 40.0 | 62.0 | 363.0 |
| 5 | 219 | 257.0 | 366.5 | 397.5 | 531.0 |
| 10 | 339 | 625.0 | 1097.0 | 1162.5 | 554.0 |

## Ce qu'on peut conclure — et ce qu'on ne peut pas

* **Ordonnancement : correct.** Dans tous les cas, le lot d'arrière-plan se termine (400 à 600 s) :
  l'ancienneté empêche la famine, même quand les dessinateurs saturent le GPU.
* **Capacité : c'est le débit du GPU qui limite, pas la file.** Avec ces durées, un GPU qui traite
  une tâche à la fois sature dès ~2 dessinateurs actifs ; l'attente grandit alors sans limite.
  Gagner du débit (concurrence vLLM, moteurs plus légers) ou ajouter un GPU est la seule solution.
* **Limite du banc :** au-delà de la saturation, seules les tâches terminées dans la fenêtre sont
  comptées ; les attentes réelles y sont donc **sous-estimées**.
* **Non mesuré :** vraies durées, VRAM, gain réel de la concurrence, latence réseau, coût par tâche.
