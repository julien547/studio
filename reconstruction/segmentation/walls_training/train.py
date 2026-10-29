"""Entraînement des murs.  python -m segmentation.walls_training.train --bundle doemo-murs-v1.zip --out sortie/ [--device cuda]

Sélection du meilleur point sur le F1 VECTORIEL de validation (pas sur la perte), export ONNX vérifié, manifeste, rapport
avec les mesures de départ. Le split TEST n'est évalué qu'UNE fois, à la fin, sur le meilleur modèle."""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from . import CLASSES, bundle
from .data import WallDataset
from .evaluate import evaluate
from .export_onnx import export, manifest, verify
from .metrics import BASELINE, honest
from .model import UNet


def dice_loss(logits, target, cls=1):
    p = torch.softmax(logits, 1)[:, cls]
    t = (target == cls).float()
    return 1 - (2 * (p * t).sum() + 1) / (p.sum() + t.sum() + 1)


def pick_device(name):
    if name != 'auto':
        return torch.device(name)
    return torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--bundle', required=True); a.add_argument('--out', required=True)
    a.add_argument('--size', type=int, default=1024); a.add_argument('--epochs', type=int, default=60)
    a.add_argument('--batch', type=int, default=4); a.add_argument('--lr', type=float, default=1e-3)
    a.add_argument('--base', type=int, default=24); a.add_argument('--repeat', type=int, default=4)
    a.add_argument('--wall-weight', type=float, default=6.); a.add_argument('--eval-every', type=int, default=5)
    a.add_argument('--device', default='auto'); a.add_argument('--workers', type=int, default=2)
    a.add_argument('--seed', type=int, default=0); a.add_argument('--train-fraction', type=float, default=1.)
    args = a.parse_args(argv)
    torch.manual_seed(args.seed); np.random.seed(args.seed)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    records = bundle.unpack(args.bundle, Path(tempfile.mkdtemp(prefix='murs_')) / 'b')
    train = records['train']
    if args.train_fraction < 1:     # courbe d'apprentissage : sous-ensemble déterministe, validation/test inchangés
        train = sorted(train, key=lambda r: hashlib.sha256(r['ref'].encode()).hexdigest())[:max(1, int(len(train) * args.train_fraction))]
    device = pick_device(args.device)
    model = UNet(base=args.base).to(device)
    loader = torch.utils.data.DataLoader(WallDataset(train, args.size, train=True, seed=args.seed, repeat=args.repeat),
                                         batch_size=args.batch, shuffle=True, num_workers=args.workers, drop_last=len(train) * args.repeat >= args.batch)
    weights = torch.ones(len(CLASSES)); weights[1] = args.wall_weight
    ce = nn.CrossEntropyLoss(weight=weights.to(device))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * len(loader))
    amp = device.type == 'cuda'
    scaler = torch.amp.GradScaler(enabled=amp)
    best, history, started = -1., [], time.time()
    for epoch in range(1, args.epochs + 1):
        model.train(); total = 0.
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            with torch.autocast(device_type=device.type, enabled=amp):
                logits = model(x)
                loss = ce(logits.float(), y) + dice_loss(logits.float(), y)
            opt.zero_grad(set_to_none=True); scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step()
            total += loss.item()
        row = {'epoch': epoch, 'loss': total / max(1, len(loader)), 'seconds': round(time.time() - started)}
        if epoch % args.eval_every == 0 or epoch == args.epochs:
            m = evaluate(model, records['validation'], args.size, device, '0' * 64, vector=True)
            row['validation'] = m; score = m.get('f1', 0.)
            if score > best:
                best = score; torch.save(model.state_dict(), out / 'best.pt'); row['best'] = True
        history.append(row); print(json.dumps(row), flush=True)
    model.load_state_dict(torch.load(out / 'best.pt', map_location=device))
    model.to('cpu'); onnx_path = out / 'walls.onnx'
    export(model, onnx_path, args.size); diff = verify(onnx_path, model, args.size)
    final = {'validation': evaluate(model, records['validation'], args.size, torch.device('cpu'), '0' * 64),
             'test': evaluate(model, records['test'], args.size, torch.device('cpu'), '0' * 64)}
    sha = manifest(onnx_path, out / 'manifest.json', args.size,
                   training={'plans': {k: len(v) for k, v in records.items()}, 'train_used': len(train), 'epochs': args.epochs,
                             'bundle_sha256': hashlib.sha256(open(args.bundle, 'rb').read()).hexdigest(), 'onnx_max_abs_diff': diff,
                             'metrics': final, 'baseline_engine_before_training': BASELINE})
    test, base = final['test'], BASELINE['test']
    verdict = {'f1_above_baseline': test['f1'] > base['f1'], 'f1_strict_above_baseline': test['f1_strict'] > base['f1_strict'],
               'length_ratio': test['length_ratio'], 'length_ratio_better_than_baseline': abs(test['length_ratio'] - 1) < abs(base['length_ratio'] - 1),
               'credible_improvement': honest(test, base['f1']) and test['f1_strict'] > base['f1_strict']}
    report = {'model_sha256': sha, 'metrics': final, 'baseline_before_training': BASELINE, 'verdict': verdict, 'history': history, 'args': vars(args)}
    (out / 'report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps({'test': final['test'], 'baseline_test': BASELINE['test'], 'verdict': verdict, 'onnx': str(onnx_path)}), flush=True)
    return report


if __name__ == '__main__':
    main()
