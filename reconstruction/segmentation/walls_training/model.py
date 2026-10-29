"""U-Net compacte en PyTorch pur (aucune dépendance exotique). La normalisation fait partie du modèle : l'entrée ONNX
reste « RGB NCHW float32 dans [0,1] » comme l'exige le contrat de run_onnx.py."""
import torch
from torch import nn
from . import CLASSES


def block(i, o):
    return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                         nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))


class UNet(nn.Module):
    def __init__(self, classes=len(CLASSES), base=24, depth=5):
        super().__init__()
        widths = [base * 2 ** k for k in range(depth)]
        self.down = nn.ModuleList([block(3 if k == 0 else widths[k - 1], widths[k]) for k in range(depth)])
        self.up = nn.ModuleList([nn.ConvTranspose2d(widths[k], widths[k - 1], 2, stride=2) for k in range(depth - 1, 0, -1)])
        self.fuse = nn.ModuleList([block(2 * widths[k - 1], widths[k - 1]) for k in range(depth - 1, 0, -1)])
        self.head = nn.Conv2d(widths[0], classes, 1)
        self.pool = nn.MaxPool2d(2)

    def forward(self, x):
        x = (x - .5) / .25
        skips = []
        for k, d in enumerate(self.down):
            x = d(x if k == 0 else self.pool(x))
            skips.append(x)
        x = skips.pop()
        for up, fuse in zip(self.up, self.fuse):
            x = fuse(torch.cat([up(x), skips.pop()], dim=1))
        return self.head(x)
