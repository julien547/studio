"""Mesure vectorielle : mêmes règles que mesurer_moteur.py (longueur couverte, tolérance 12 px dans le repère du relevé).

Référence AVANT entraînement (moteur géométrique de la page « Redessin des murs », 29/10/2026, 73 plans vérifiés) :
F1 0,40 / F1 strict 0,29 / longueur prédite = 3,1 x la vraie ; sur les 11 plans de test : F1 0,38 / strict 0,25 / x4,6."""
import cv2
import numpy as np

BASELINE = {'all': {'f1': .40, 'f1_strict': .29, 'recall': .65, 'precision': .33, 'length_ratio': 3.1},
            'test': {'f1': .38, 'f1_strict': .25, 'recall': .75, 'precision': .27, 'length_ratio': 4.6}}
# Le moteur actuel propose 3 à 4,6 fois plus de longueur de mur qu'il n'y en a : son F1 est lui-même gonflé par cet excès.


def _points(segments, step=4.):
    """Points d'échantillonnage PONDÉRÉS PAR LA LONGUEUR : un segment de longueur L pèse L, quel que soit son découpage
    (l'ancienne version donnait au moins 2 points même à un segment minuscule : un mur fragmenté pesait plus qu'un mur entier)."""
    pts, wts = [], []
    for x1, y1, x2, y2 in segments:
        length = float(np.hypot(x2 - x1, y2 - y1))
        if length <= 0:
            continue
        n = max(1, int(np.ceil(length / step)))
        t = ((np.arange(n) + .5) / n)[:, None]
        pts.append(np.hstack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t])); wts.append(np.full(n, length / n))
    if not pts:
        return np.zeros((0, 2)), np.zeros(0)
    return np.vstack(pts), np.concatenate(wts)


def _distance_map(segments, width, height):
    canvas = np.zeros((height, width), np.uint8)
    for x1, y1, x2, y2 in segments:
        cv2.line(canvas, (int(round(x1)), int(round(y1))), (int(round(x2)), int(round(y2))), 255, 1)
    return cv2.distanceTransform(255 - canvas, cv2.DIST_L2, 3)


def _covered(points, distance, tolerance):
    pts, wts = points
    if not len(pts) or wts.sum() <= 0:
        return 0.
    h, w = distance.shape
    x, y = np.clip(pts[:, 0].astype(int), 0, w - 1), np.clip(pts[:, 1].astype(int), 0, h - 1)
    return float((wts * (distance[y, x] <= tolerance)).sum() / wts.sum())


def _length(segments):
    return float(sum(np.hypot(x2 - x1, y2 - y1) for x1, y1, x2, y2 in segments))


def length_scores(predicted, truth, width, height, tolerance=12., strict=6.):
    """rappel = part de la longueur vraie couverte ; précision = part de la longueur prédite qui est vraie.

    GARDE-FOUS contre un modèle qui « gagne » en noircissant le plan : `length_ratio` (longueur prédite / longueur vraie,
    1 = idéal) et `f1_strict` (même mesure à 6 px). Un score n'est une amélioration que si le ratio reste raisonnable."""
    recall = _covered(_points(truth), _distance_map(predicted, width, height), tolerance)
    precision = _covered(_points(predicted), _distance_map(truth, width, height), tolerance)
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.
    r6 = _covered(_points(truth), _distance_map(predicted, width, height), strict)
    p6 = _covered(_points(predicted), _distance_map(truth, width, height), strict)
    f1s = 2 * r6 * p6 / (r6 + p6) if r6 + p6 else 0.
    true_length = _length(truth)
    return {'recall': recall, 'precision': precision, 'f1': f1, 'f1_strict': f1s,
            'length_ratio': _length(predicted) / true_length if true_length else 0.}


def mean_scores(rows):
    keys = ('recall', 'precision', 'f1', 'f1_strict', 'length_ratio')
    return {k: float(np.mean([r[k] for r in rows])) for k in keys} if rows else {}


def honest(scores, baseline_f1, max_ratio=2.0):
    """Amélioration crédible : F1 supérieur à la référence ET longueur prédite proche de la longueur vraie."""
    return scores.get('f1', 0.) > baseline_f1 and 0.5 <= scores.get('length_ratio', 0.) <= max_ratio
