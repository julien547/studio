"""Rastérisation des murs vérifiés + augmentation. Image et masque subissent EXACTEMENT les mêmes transformations.

Contrat d'entrée du moteur : l'image est redimensionnée en size x size SANS conserver le rapport (run_onnx.py) ;
le masque est donc rastérisé dans le même repère déformé."""
import cv2
import numpy as np

WALL = 1
IGNORE = 255      # pixel hors de la zone dessinée par le dessinateur : ni mur ni fond (ignoré par la perte)
# Épaisseur de l'axe de mur dans le repère 2048 px du jeu ; réduite proportionnellement à la taille d'entrée.
THICKNESS_2048 = 10.


def rasterize(segments, width, height, size, thickness=THICKNESS_2048, ignore_outside=False, margin=.06):
    """`ignore_outside` : la vérité ne couvre que la zone dessinée par le dessinateur ; hors de l'enveloppe convexe de ses murs
    (+ marge, en fraction de la taille) les pixels reçoivent IGNORE au lieu de « fond », sinon le modèle apprend à effacer de vrais murs."""
    mask = np.zeros((size, size), np.uint8)
    kx, ky = size / width, size / height
    t = max(1, int(round(thickness * size / 2048.)))
    for x1, y1, x2, y2 in segments:
        cv2.line(mask, (int(round(x1 * kx)), int(round(y1 * ky))), (int(round(x2 * kx)), int(round(y2 * ky))), WALL, t)
    if ignore_outside and len(segments):
        pts = np.array([[x * kx, y * ky] for x1, y1, x2, y2 in segments for x, y in ((x1, y1), (x2, y2))], np.float32)
        zone = np.zeros((size, size), np.uint8)
        cv2.fillConvexPoly(zone, cv2.convexHull(pts).astype(np.int32), 1)
        k = max(1, int(round(margin * size)))
        zone = cv2.dilate(zone, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
        mask[(zone == 0) & (mask == 0)] = IGNORE
    return mask


def load(record, size, ignore_outside=False):
    image = cv2.imread(record['path'], cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Image illisible : ' + record['path'])
    image = cv2.cvtColor(cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    return image, rasterize(record['segments'], record['width'], record['height'], size, ignore_outside=ignore_outside)


def augment(image, mask, rng):
    """Retournements, rotations de 90°, zoom/rotation légers, lumière, flou, bruit."""
    k = int(rng.integers(0, 4))
    image, mask = np.rot90(image, k), np.rot90(mask, k)
    if rng.random() < .5:
        image, mask = image[:, ::-1], mask[:, ::-1]
    image, mask = np.ascontiguousarray(image), np.ascontiguousarray(mask)
    h, w = mask.shape
    angle, scale = float(rng.uniform(-8, 8)), float(rng.uniform(.8, 1.25))
    m = cv2.getRotationMatrix2D((w / 2 + rng.uniform(-.1, .1) * w, h / 2 + rng.uniform(-.1, .1) * h), angle, scale)
    image = cv2.warpAffine(image, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    mask = cv2.warpAffine(mask, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    img = image.astype(np.float32) / 255.
    img = np.clip((img - .5) * rng.uniform(.7, 1.3) + .5 + rng.uniform(-.15, .15), 0, 1)
    img = np.power(img, rng.uniform(.8, 1.25))
    if rng.random() < .3:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(.5, 1.6))
    if rng.random() < .3:
        img = np.clip(img + rng.normal(0, rng.uniform(.005, .03), img.shape).astype(np.float32), 0, 1)
    if rng.random() < .15:
        img = np.repeat(img.mean(axis=2, keepdims=True), 3, axis=2)
    return (img * 255).astype(np.uint8), mask


class WallDataset:
    """Compatible torch.utils.data.Dataset sans importer torch ici (testable sans GPU)."""

    def __init__(self, records, size=1024, train=False, seed=0, repeat=1, ignore_outside=False):
        self.records, self.size, self.train, self.seed, self.repeat = records, size, train, seed, repeat
        self.ignore_outside = ignore_outside
        self._cache = {}

    def __len__(self):
        return len(self.records) * self.repeat

    def __getitem__(self, i):
        record = self.records[i % len(self.records)]
        key = record['ref']
        if key not in self._cache:
            self._cache[key] = load(record, self.size, self.ignore_outside)
        image, mask = self._cache[key]
        if self.train:
            image, mask = augment(image, mask, np.random.default_rng((self.seed, i, np.random.randint(1 << 30))))
        x = np.ascontiguousarray(image.transpose(2, 0, 1), dtype=np.float32) / 255.
        return x, np.ascontiguousarray(mask, dtype=np.int64)
