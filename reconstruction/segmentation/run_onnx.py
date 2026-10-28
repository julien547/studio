"""Optional isolated ONNX worker. No weights or third-party model code included.

Contract: one RGB NCHW float32 input scaled to [0,1]; one NCHW class logits output.
Run in its own venv with onnxruntime, numpy and Pillow. No network dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path


def checked_manifest(model, manifest):
    metadata=json.loads(Path(manifest).read_text())
    for component in ('code','weights','training_data'):
        rights=metadata['rights'][component]
        if rights.get('commercial_use') is not True or not rights.get('evidence_url') or not rights.get('reviewed_by'):
            raise ValueError('Droits commerciaux non validés : '+component)
    if hashlib.sha256(Path(model).read_bytes()).hexdigest()!=metadata['sha256']:
        raise ValueError('Empreinte du modèle incorrecte')
    if metadata['input_contract']!='rgb_nchw_0_1' or metadata['output_contract']!='nchw_logits':
        raise ValueError('Contrat ONNX incompatible')
    if metadata['classes']!=['background','wall','partition','door','window','stairs','text','annotation','furniture','symbol','room']:
        raise ValueError('Classes incompatibles')
    return metadata


def main():
    p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('manifest');p.add_argument('image');p.add_argument('output');args=p.parse_args()
    metadata=checked_manifest(args.model,args.manifest)
    import numpy as np
    import onnxruntime as ort
    from PIL import Image
    size=metadata['input_size']
    if not all(type(v) is int and 32<=v<=4096 for v in size) or len(size)!=2:
        raise ValueError('Taille d’entrée invalide')
    image=Image.open(args.image).convert('RGB');original=image.size
    tensor=np.asarray(image.resize(tuple(size)),dtype=np.float32).transpose(2,0,1)[None]/255
    options=ort.SessionOptions();options.intra_op_num_threads=2
    session=ort.InferenceSession(args.model,sess_options=options,providers=['CPUExecutionProvider'])
    outputs=session.run(None,{session.get_inputs()[0].name:tensor})
    logits=outputs[0]
    if logits.ndim!=4 or logits.shape[0]!=1 or logits.shape[1]!=len(metadata['classes']) or not np.isfinite(logits).all():
        raise ValueError('Sortie de segmentation invalide')
    labels=logits[0].argmax(axis=0).astype(np.uint8)
    labels=np.asarray(Image.fromarray(labels).resize(original,Image.Resampling.NEAREST))
    # This is semantic evidence only, never approved drawing geometry.
    np.savez_compressed(args.output,labels=labels,model_sha256=metadata['sha256'],
                        classes=np.array(metadata['classes']),status='pending')


if __name__=='__main__':main()
