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


ENCODER_INFO = {
    'resnet34.a1_in1k': {'source': 'https://huggingface.co/timm/resnet34.a1_in1k', 'weights_license': 'apache-2.0',
                         'pretraining_data': 'ImageNet-1k (conditions du jeu de données : recherche non commerciale ; statut juridique des modèles dérivés '
                                             'à usage commercial à valider par le propriétaire)'}}


class PretrainedUNet(nn.Module):
    """U-Net à encodeur pré-entraîné (timm). Même contrat que UNet : entrée RGB [0,1], sortie logits à la résolution d'entrée.
    La normalisation ImageNet fait partie du modèle. `pretrained=False` sert aux tests hors ligne (même architecture, poids aléatoires)."""

    def __init__(self, classes=len(CLASSES), encoder='resnet34.a1_in1k', pretrained=True):
        super().__init__()
        import timm
        self.encoder = timm.create_model(encoder, features_only=True, pretrained=pretrained, out_indices=(0, 1, 2, 3, 4))
        ch = self.encoder.feature_info.channels()          # strides 2, 4, 8, 16, 32
        self.up = nn.ModuleList([nn.ConvTranspose2d(ch[k], ch[k - 1], 2, stride=2) for k in range(len(ch) - 1, 0, -1)])
        self.fuse = nn.ModuleList([block(2 * ch[k - 1], ch[k - 1]) for k in range(len(ch) - 1, 0, -1)])
        self.last = nn.ConvTranspose2d(ch[0], 32, 2, stride=2)
        self.refine = block(32, 32)
        self.head = nn.Conv2d(32, classes, 1)
        self.register_buffer('mean', torch.tensor([.485, .456, .406]).view(1, 3, 1, 1))
        self.register_buffer('std', torch.tensor([.229, .224, .225]).view(1, 3, 1, 1))

    def forward(self, x):
        feats = self.encoder((x - self.mean) / self.std)
        y = feats.pop()
        for up, fuse in zip(self.up, self.fuse):
            y = fuse(torch.cat([up(y), feats.pop()], dim=1))
        return self.head(self.refine(self.last(y)))


def build(encoder=None, base=24, pretrained=True):
    """encoder=None : U-Net maison de zéro (comportement historique) ; sinon U-Net à encodeur timm pré-entraîné."""
    return UNet(base=base) if not encoder else PretrainedUNet(encoder=encoder, pretrained=pretrained)
