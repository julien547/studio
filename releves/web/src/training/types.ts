import type { Box, Point } from "../types";
export const prefix = "/projects/training";
export const engines = {
  qwen: "Qwen3.5-9B",
  paddleocr: "PaddleOCR",
  rtmdet: "RTMDet",
  architecture: "IA architecturale",
} as const;
export type Engine = keyof typeof engines;
export type Category = {
  code: string;
  name: string;
  kind: "wall" | "door" | "opening" | "equipment" | "text" | "other";
  active: boolean;
};
export type Label = {
  id: string;
  category: string;
  bbox: Box;
  anchor: Point | null;
  segments: [Point, Point][];
  mask_polygons: Point[][];
  text: string;
  origin: string;
  checked: boolean;
};
export type ExampleData = {
  revision: number;
  engine: Engine;
  project_id: string;
  document_id: string;
  page: number;
  floor_id: string | null;
  region: Box;
  rotation: 0 | 90 | 180 | 270;
  labels: Label[];
  interpretation: string;
  observed: string;
  convention: string;
  notes: string;
  junctions: Point[];
};
export type Example = {
  id: string;
  revision: number;
  status: "draft" | "validated" | "rejected";
  project_id: string;
  document_id: string;
  page: number;
  data: ExampleData;
  author: string;
  updated: string;
};
export type Dataset = {
  id: string;
  engine: Engine;
  name: string;
  version: number;
  sha256: string;
  created: string;
  snapshot?: {
    examples: (Example & { split: string })[];
    groups: number;
    warnings: string[];
  };
};
export type Capability = {
  name: string;
  function: string;
  training: boolean;
  evaluation: boolean;
  deployment: boolean;
  reference_versions: boolean;
  reason: string;
  minimum_recommended_examples: number;
};
export type Version = {
  id: string;
  name: string;
  status: string;
  method: string;
  dataset_id: string;
  run_id: string | null;
  manifest: Record<string, unknown>;
  evaluation: Record<string, unknown> | null;
  author: string;
  created: string;
};
export type Registry = {
  deployment: { version_id: string | null; previous_id: string | null };
  versions: Version[];
  base_status: string;
};
export type Run = {
  id: string;
  dataset_id: string;
  status: string;
  progress: number | null;
  result: unknown;
  error: string | null;
  created: string;
  parameters: unknown;
};
export type ProjectSummary = { id: string; name: string };
export const statusNames: Record<string, string> = {
  draft: "Brouillon",
  validated: "Validé",
  rejected: "Rejeté",
  development: "Développement",
  candidate: "Candidat",
  approved: "Approuvé",
  production: "Production",
  archived: "Archivé",
  queued: "En attente",
  waiting_gpu: "Attente du GPU",
  running: "En cours",
  checkpointing: "Sauvegarde",
  paused: "En pause",
  cancel_requested: "Annulation demandée",
  cancelled: "Annulé",
  failed: "Échec",
  completed: "Terminé",
  interrupted: "Interrompu",
};
export const message = (e: unknown) =>
  e instanceof Error ? e.message : String(e);
export type Perform = (
  fn: () => Promise<void>,
  notice?: string,
) => Promise<void>;
export const compatible = (engine: Engine, kind: Category["kind"]) =>
  engine === "qwen" ||
  (engine === "paddleocr"
    ? kind === "text"
    : engine === "architecture"
      ? ["wall", "door", "opening"].includes(kind)
      : ["equipment", "door", "opening", "other"].includes(kind));
