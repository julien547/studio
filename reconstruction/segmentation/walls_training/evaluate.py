"""Évaluation : image -> logits -> raster 11 classes -> wall_module.reconstruct_mask (axe médian) -> segments -> mesure."""
import hashlib
import cv2
import numpy as np
import torch
from doemo_reconstruction.wall_module import reconstruct_mask
from . import CLASSES
from .data import load
from .metrics import length_scores, mean_scores


@torch.no_grad()
def predict_labels(model, record, size, device):
    """Même chaîne que run_onnx.py : redimensionnement sans rapport, argmax, retour à la taille d'origine en plus proche voisin."""
    image, _ = load(record, size)
    x = torch.from_numpy(np.ascontiguousarray(image.transpose(2, 0, 1), dtype=np.float32) / 255.)[None].to(device)
    labels = model(x)[0].argmax(0).to('cpu').numpy().astype(np.uint8)
    return cv2.resize(labels, (record['width'], record['height']), interpolation=cv2.INTER_NEAREST)


def labels_to_segments(labels, record, model_sha):
    image_sha = hashlib.sha256(open(record['path'], 'rb').read()).hexdigest()
    result = reconstruct_mask(labels, classes=CLASSES, source_sha256=image_sha, model_sha256=model_sha,
                              document_size=(record['width'], record['height']), image_to_document=[1, 0, 0, 1, 0, 0])
    return [(w['a'][0], w['a'][1], w['b'][0], w['b'][1]) for w in result['walls']]


def evaluate(model, records, size, device, model_sha, vector=True):
    """Dice pixel (classe mur) toujours ; mesures vectorielles (rappel/précision/F1) si vector=True."""
    model.eval()
    dice, rows, counts = [], [], []
    for r in records:
        labels = predict_labels(model, r, size, device)
        truth = np.zeros((r['height'], r['width']), np.uint8)
        for x1, y1, x2, y2 in r['segments']:
            cv2.line(truth, (int(round(x1)), int(round(y1))), (int(round(x2)), int(round(y2))), 1, int(round(10)))
        p, t = labels == 1, truth == 1
        dice.append(2 * (p & t).sum() / max(1, p.sum() + t.sum()))
        if vector:
            seg = labels_to_segments(labels, r, model_sha) if p.any() else []
            counts.append(len(seg))
            rows.append(length_scores(seg, r['segments'], r['width'], r['height']))
    out = {'dice': float(np.mean(dice)), 'plans': len(records)}
    if vector:
        out.update(mean_scores(rows))
        out['proposed_walls_median'] = int(np.median(counts)) if counts else 0
    return out
