export type Point = { x: number; y: number };
export type Box = Point & { w: number; h: number };
export type Review = {
  equipment: boolean;
  asset: boolean;
  floor: boolean;
  position: boolean;
  orientation: boolean;
  size: boolean;
};
export type Annotation = {
  id: string;
  source_document_id: string;
  source_page: number;
  bbox: Box;
  anchor: Point | null;
  anchor_kind: string;
  text: string;
  color: string;
  shape: string;
  confidence: number;
  method: string;
  equipment_type: string;
  asset_id: string | null;
  floor_id: string | null;
  rotation_deg: number;
  size_mm: number;
  target: Point | null;
  status: string;
  review: Review;
  evidence: string;
};
export type Floor = {
  id: string;
  name: string;
  target_page: number;
  artboard_index: number;
  target_group: string;
  confirmed: boolean;
};
export type Registration = {
  source_document_id: string;
  source_page: number;
  floor_id: string;
  model: "affine" | "homography";
  matrix: number[][];
  source_points: Point[];
  target_points: Point[];
  check_source_points: Point[];
  check_target_points: Point[];
  fit_error_px: number;
  check_error_px: number;
  max_error_px: number;
  confirmed: boolean;
  architecture_confirmed: boolean;
};
export type Mapping = {
  annotation: string;
  equipment_type: string;
  asset_id: string;
  confirmed: boolean;
};
export type Legend = {
  source_document_id: string;
  source_page: number;
  bbox: Box | null;
  entries: { color: string; label: string; equipment_type: string; confirmed: boolean }[];
};
export type State = {
  schema_version: "doemo.review/1";
  revision: number;
  annotations: Annotation[];
  floors: Floor[];
  registrations: Registration[];
  legends: Legend[];
  mappings: Mapping[];
  mapping_version: number;
  library_id: string | null;
};
export type Doc = {
  id: string;
  name: string;
  role: "survey" | "target";
  sha256: string;
  pages: { number: number; width: number; height: number; pdf_size_pt: [number, number] | null }[];
};
export type Project = { id: string; owner: string; name: string; state: State; documents: Doc[] };
export type Asset = {
  id: string;
  name: string;
  type: string;
  groups: string[];
  pictogram_candidate: boolean;
  verified: boolean;
  approved: boolean;
  preview: boolean;
};
export type Library = {
  id: string;
  name: string;
  archive_verified: boolean;
  assets: Asset[];
  warnings: string[];
};
