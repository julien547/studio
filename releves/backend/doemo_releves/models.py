from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Model):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Box(Model):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside(self):
        if self.x + self.w > 1.000001 or self.y + self.h > 1.000001:
            raise ValueError("Boîte hors page")
        return self


class Review(Model):
    equipment: bool = False
    asset: bool = False
    floor: bool = False
    position: bool = False
    orientation: bool = False
    size: bool = False


class Annotation(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    source_document_id: str
    source_page: int = Field(ge=1)
    bbox: Box
    anchor: Point | None = None
    anchor_kind: Literal["unknown", "direct", "arrow_tip", "leader_tip", "manual"] = "unknown"
    text: str = Field(default="", max_length=2000)
    color: str = Field(default="unknown", max_length=40)
    shape: str = Field(default="unknown", max_length=100)
    confidence: float = Field(default=0, ge=0, le=1)
    method: str = Field(default="manual", max_length=100)
    equipment_type: str = Field(default="", max_length=200)
    asset_id: str | None = None
    floor_id: str | None = None
    rotation_deg: float = Field(default=0, ge=-360, le=360)
    size_mm: float = Field(default=7, gt=0, le=200)
    target: Point | None = None
    status: Literal["review", "confirmed", "rejected", "missing_asset", "uncertain_position"] = "review"
    review: Review = Field(default_factory=Review)
    evidence: str = Field(default="", max_length=2000)
    comment: str = Field(default="", max_length=4000)
    training_accepted: bool = False


class Floor(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=100)
    target_page: int = Field(ge=1)
    # PDF preview page -> Illustrator artboard, explicit human-confirmed association.
    artboard_index: int = Field(ge=0, le=999)
    target_group: str = Field(default="", max_length=200)
    confirmed: bool = False
    source_document_id: str | None = None
    source_page: int = Field(default=1, ge=1)
    source_region: Box | None = None
    rotation_deg: Literal[0, 90, 180, 270] = 0


class Registration(Model):
    source_document_id: str
    source_page: int = Field(ge=1)
    floor_id: str
    model: Literal["affine", "homography"]
    matrix: list[list[float]]
    source_points: list[Point]
    target_points: list[Point]
    check_source_points: list[Point] = Field(min_length=1)
    check_target_points: list[Point] = Field(min_length=1)
    fit_error_px: float = Field(ge=0)
    check_error_px: float = Field(ge=0)
    max_error_px: float = Field(gt=0, le=30)
    confirmed: bool = False
    architecture_confirmed: bool = False

    @model_validator(mode="after")
    def matrix_shape(self):
        if len(self.matrix) != 3 or any(len(row) != 3 for row in self.matrix):
            raise ValueError("Matrice 3×3 attendue")
        if not all(math.isfinite(v) for row in self.matrix for v in row):
            raise ValueError("Matrice non finie")
        return self


class LegendEntry(Model):
    color: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=200)
    equipment_type: str = Field(min_length=1, max_length=200)
    confirmed: bool = False


class Legend(Model):
    source_document_id: str
    source_page: int = Field(ge=1)
    bbox: Box | None = None
    entries: list[LegendEntry] = Field(default_factory=list, max_length=100)


class Mapping(Model):
    annotation: str = Field(min_length=1, max_length=200)
    equipment_type: str = Field(min_length=1, max_length=200)
    asset_id: str
    confirmed: bool = False


class StructureOpening(Model):
    start: float = Field(ge=0, le=1)
    end: float = Field(ge=0, le=1)
    kind: Literal['door', 'window', 'passage']
    status: Literal['pending', 'approved'] = 'pending'

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Ouverture de longueur positive requise')
        return self


class StructureWall(Model):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    a: tuple[float, float]
    b: tuple[float, float]
    thickness: float | None = Field(default=None, gt=0, le=100000)
    openings: list[StructureOpening] = Field(default_factory=list, max_length=100)
    status: Literal['pending', 'approved', 'rejected'] = 'pending'
    method: str = Field(default='manual', max_length=100)
    confidence: float = Field(default=0, ge=0, le=1)

    @model_validator(mode='after')
    def geometry(self):
        if math.dist(self.a, self.b) < 1e-6:
            raise ValueError('Mur de longueur positive requis')
        previous = 0.
        for opening in sorted(self.openings, key=lambda o: o.start):
            if opening.start < previous - 1e-9:
                raise ValueError('Les ouvertures ne peuvent pas se superposer')
            previous = opening.end
        return self


class StructurePage(Model):
    source_document_id: str = Field(min_length=1, max_length=100)
    source_page: int = Field(ge=1, le=10000)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    width: float = Field(gt=0, le=100000)
    height: float = Field(gt=0, le=100000)
    unit: Literal['px', 'pt']
    walls: list[StructureWall] = Field(default_factory=list, max_length=10000)
    analysis_ids: list[str] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def geometry(self):
        if len({w.id for w in self.walls}) != len(self.walls):
            raise ValueError('Identifiants de murs dupliqués')
        if len(set(self.analysis_ids)) != len(self.analysis_ids) or any(
                not ident or len(ident) > 100 for ident in self.analysis_ids):
            raise ValueError('Identifiants d’analyse invalides')
        if any(len(warning) > 1000 for warning in self.warnings):
            raise ValueError('Avertissement de structure trop long')
        for wall in self.walls:
            if any(not 0 <= x <= self.width or not 0 <= y <= self.height for x, y in (wall.a, wall.b)):
                raise ValueError('Mur hors de la page source')
            if wall.thickness is not None and wall.thickness > max(self.width, self.height):
                raise ValueError('Épaisseur de mur excessive')
        return self


class ProjectState(Model):
    schema_version: Literal["doemo.review/1"] = "doemo.review/1"
    revision: int = Field(ge=0)
    annotations: list[Annotation] = Field(default_factory=list, max_length=10000)
    floors: list[Floor] = Field(default_factory=list, max_length=100)
    registrations: list[Registration] = Field(default_factory=list, max_length=200)
    legends: list[Legend] = Field(default_factory=list, max_length=200)
    mappings: list[Mapping] = Field(default_factory=list, max_length=1000)
    mapping_version: int = Field(default=1, ge=1)
    library_id: str | None = None
    workflow: Literal["draft", "review", "corrected", "validated"] = "draft"
    structure_pages: list[StructurePage] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        for items in [self.annotations, self.floors]:
            if len({x.id for x in items}) != len(items):
                raise ValueError("Identifiants dupliqués")
        keys = [(r.source_document_id, r.source_page, r.floor_id) for r in self.registrations]
        if len(keys) != len(set(keys)):
            raise ValueError("Recalages dupliqués")
        keys = [(p.source_document_id, p.source_page) for p in self.structure_pages]
        if len(keys) != len(set(keys)) or sum(len(p.walls) for p in self.structure_pages) > 20000:
            raise ValueError('Pages de structure dupliquées ou trop de murs')
        return self
