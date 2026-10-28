"""PDF coordinates: points, bottom-left origin, Y upwards, CCW degrees."""

from dataclasses import dataclass
import math


def finite(values):
    values = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Coordonnée non finie.")
    return values


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        finite(self.values)
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("Rectangle vide ou inversé.")

    @property
    def values(self):
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def corners(self):
        return ((self.x0, self.y0), (self.x1, self.y0),
                (self.x1, self.y1), (self.x0, self.y1))

    def inset(self, margin):
        margin, = finite([margin])
        if margin < 0:
            raise ValueError("Marge négative.")
        return Rect(self.x0 + margin, self.y0 + margin,
                    self.x1 - margin, self.y1 - margin)

    def contains(self, other, tolerance=1e-7):
        return (self.x0 - tolerance <= other.x0 and self.y0 - tolerance <= other.y0
                and self.x1 + tolerance >= other.x1 and self.y1 + tolerance >= other.y1)


@dataclass(frozen=True)
class Matrix:
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @property
    def values(self):
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    def point(self, point):
        x, y = point
        return (self.a*x + self.c*y + self.e, self.b*x + self.d*y + self.f)

    def vector(self, vector):
        x, y = vector
        return (self.a*x + self.c*y, self.b*x + self.d*y)

    def bounds(self, rect):
        points = [self.point(p) for p in rect.corners]
        return Rect(min(p[0] for p in points), min(p[1] for p in points),
                    max(p[0] for p in points), max(p[1] for p in points))

    def inverse(self):
        det = self.a*self.d - self.b*self.c
        if not math.isfinite(det) or det <= 0:
            raise ValueError("Matrice non inversible ou avec réflexion.")
        return Matrix(self.d/det, -self.b/det, -self.c/det, self.a/det,
                      (self.c*self.f-self.d*self.e)/det,
                      (self.b*self.e-self.a*self.f)/det)

    def then(self, after):
        """Apply this matrix first, then `after`. Preserve the local resource."""
        return Matrix(after.a*self.a+after.c*self.b, after.b*self.a+after.d*self.b,
                      after.a*self.c+after.c*self.d, after.b*self.c+after.d*self.d,
                      after.a*self.e+after.c*self.f+after.e,
                      after.b*self.e+after.d*self.f+after.f)


def component_transform(global_matrix, angle, source_anchor, directional):
    """Counter-rotate an *already isolated* component, keeping its anchor fixed.

    This computes a matrix only. It does not infer which PDF operators belong
    to a symbol and must not be applied to an entire mixed Pictos layer.
    Its source reference orientation is preserved (not blindly set to zero).
    """
    finite(global_matrix.values)
    finite(source_anchor)
    finite([angle])
    if directional:
        return global_matrix
    center = global_matrix.point(source_anchor)
    radians = math.radians(-angle)
    co, si = math.cos(radians), math.sin(radians)
    x, y = center
    compensation = Matrix(co, si, -si, co, x-co*x+si*y, y-si*x-co*y)
    return global_matrix.then(compensation)


def rotation_to_up(direction):
    dx, dy = finite(direction)
    if math.hypot(dx, dy) < 1e-12:
        raise ValueError("Direction de flèche nulle.")
    angle = (90 - math.degrees(math.atan2(dy, dx))) % 360
    return angle - 360 if angle > 180 else angle


def fit(source, zone, direction, allow_upscale=True):
    angle = rotation_to_up(direction)
    radians = math.radians(angle)
    co, si = math.cos(radians), math.sin(radians)
    rotated = Matrix(co, si, -si, co, 0, 0).bounds(source)
    scale = min((zone.x1-zone.x0)/(rotated.x1-rotated.x0),
                (zone.y1-zone.y0)/(rotated.y1-rotated.y0))
    if not allow_upscale:
        scale = min(1.0, scale)
    sx, sy = source.center
    tx, ty = zone.center
    matrix = Matrix(scale*co, scale*si, -scale*si, scale*co,
                    tx-scale*co*sx+scale*si*sy,
                    ty-scale*si*sx-scale*co*sy)
    finite(matrix.values)
    result = matrix.bounds(source)
    if not zone.contains(result):
        raise ValueError("Débordement de la zone utile.")
    dx, dy = matrix.vector(direction)
    if dy <= 0 or abs(dx) > max(1e-9, abs(dy)*1e-9):
        raise ValueError("La direction déclarée ne pointe pas vers le haut.")
    return matrix, scale, angle
