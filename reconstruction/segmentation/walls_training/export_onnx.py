"""Export ONNX + manifeste conformes à segmentation/run_onnx.py (RGB NCHW float32 [0,1] -> logits NCHW, 11 classes).

Les droits (code, poids, données d'entraînement) restent À FAUX : aucune revue n'est simulée. Julien doit renseigner
`commercial_use`, `evidence_url` et `reviewed_by` pour chaque composant avant tout usage (checked_manifest refuse sinon)."""
import hashlib
import json
import torch
from . import CLASSES


def export(model, path, size=1024):
    model.eval().to('cpu')
    dummy = torch.rand(1, 3, size, size)
    torch.onnx.export(model, dummy, str(path), input_names=['image'], output_names=['logits'], opset_version=17,
                      dynamo=False, do_constant_folding=True)
    return path


def verify(path, model, size=1024, tolerance=1e-3):
    """L'ONNX doit redonner les mêmes logits que PyTorch (sinon l'export est invalide)."""
    import numpy as np
    import onnxruntime as ort
    x = torch.rand(1, 3, size, size)
    with torch.no_grad():
        expected = model.eval().to('cpu')(x).numpy()
    session = ort.InferenceSession(str(path), providers=['CPUExecutionProvider'])
    got = session.run(None, {session.get_inputs()[0].name: x.numpy()})[0]
    if got.shape != expected.shape or not np.isfinite(got).all():
        raise ValueError('Sortie ONNX invalide')
    diff = float(np.abs(got - expected).max())
    if diff > tolerance:
        raise ValueError('ONNX différent de PyTorch : %g' % diff)
    return diff


def manifest(onnx_path, manifest_path, size=1024, training=None):
    sha = hashlib.sha256(open(onnx_path, 'rb').read()).hexdigest()
    pending = {'commercial_use': False, 'evidence_url': '', 'reviewed_by': ''}
    data = {'sha256': sha, 'input_contract': 'rgb_nchw_0_1', 'output_contract': 'nchw_logits',
            'input_size': [size, size], 'classes': CLASSES,
            'rights': {'code': dict(pending), 'weights': dict(pending), 'training_data': dict(pending)},
            'trained_classes': ['background', 'wall'], 'training': training or {}}
    with open(manifest_path, 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return sha
