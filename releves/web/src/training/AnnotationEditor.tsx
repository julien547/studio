import { useEffect, useRef, useState } from "react";
import { api, download, url } from "../api";
import { PlanCanvas, type Tool } from "../PlanCanvas";
import type { Annotation, Box, Point, Project } from "../types";
import { wholePage } from "../editorGeometry";
import {
  compatible,
  prefix,
  statusNames,
  type Category,
  type Engine,
  type Example,
  type ExampleData,
  type Label,
  type Perform,
  type ProjectSummary,
} from "./types";

const boxFor = (segments: [Point, Point][]): Box => {
  const points = segments.flat(),
    xs = points.map((p) => p.x),
    ys = points.map((p) => p.y);
  const x = Math.max(0, Math.min(...xs) - 0.00001),
    y = Math.max(0, Math.min(...ys) - 0.00001);
  return {
    x,
    y,
    w: Math.min(1 - x, Math.max(...xs) - x + 0.00001),
    h: Math.min(1 - y, Math.max(...ys) - y + 0.00001),
  };
};
const empty = (
  engine: Engine,
  p: Project,
  document = p.documents.find((d) => d.role === "survey")?.id || "",
  page = 1,
): ExampleData => ({
  engine,
  project_id: p.id,
  document_id: document,
  page,
  revision: 0,
  floor_id: null,
  region: { ...wholePage },
  rotation: 0,
  labels: [],
  observed: "",
  interpretation: "",
  convention: "",
  notes: "",
  junctions: [],
});
type Job = {
  id: string;
  status: string;
  stage: string;
  error: string | null;
  payload?: { engine: string; document_id: string; page: number };
  result?: {
    annotations: Annotation[];
    observations: unknown[];
    warnings: string[];
    proposals?: {
      bbox: Box;
      source_class: number;
      score: number;
      document_id: string;
      page: number;
    }[];
  };
};
export function AnnotationEditor({
  engine,
  categories,
  projects,
  initial,
  perform,
  onSaved,
  onDirty,
  refreshProjects,
}: {
  engine: Engine;
  categories: Category[];
  projects: ProjectSummary[];
  initial: Example | null;
  perform: Perform;
  onSaved: () => Promise<void>;
  onDirty: (dirty: boolean) => void;
  refreshProjects: () => Promise<void>;
}) {
  const [project, setProject] = useState<Project | null>(null),
    [data, setData] = useState<ExampleData | null>(null),
    [record, setRecord] = useState<Example | null>(null);
  const [dirty, setDirty] = useState(false),
    [selected, setSelected] = useState<string[]>([]),
    [tool, setTool] = useState<Tool>("select"),
    [zoom, setZoom] = useState(100),
    [showImage, setShowImage] = useState(true);
  const [category, setCategory] = useState(
      (
        {
          qwen: "OTHER",
          paddleocr: "HANDWRITING",
          rtmdet: "FIRE",
          architecture: "WALL",
        } as const
      )[engine] as string,
    ),
    [reason, setReason] = useState(""),
    [projectName, setProjectName] = useState("");
  const [job, setJob] = useState<Job | null>(null),
    [previousJobs, setPreviousJobs] = useState<Job[]>([]),
    [showProposals, setShowProposals] = useState(true),
    [jobError, setJobError] = useState(""),
    [applied, setApplied] = useState(false),
    [aiAvailable, setAiAvailable] = useState(false);
  const history = useRef<ExampleData[]>([]),
    future = useRef<ExampleData[]>([]);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    const fn = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", fn);
    return () => window.removeEventListener("beforeunload", fn);
  }, [dirty]);
  useEffect(() => {
    let live = true;
    if (initial)
      void perform(async () => {
        const p = await api<Project>("/projects/" + initial.project_id);
        if (live) {
          setProject(p);
          install(initial.data, initial);
        }
      });
    return () => {
      live = false;
    };
  }, [initial?.id]);
  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          engines: Record<string, boolean>;
          automatic_start: boolean;
        }>("/projects/ai-status");
        if (live)
          setAiAvailable(
            engine !== "architecture" &&
              (r.engines?.[engine] === true || r.automatic_start === true),
          );
      } catch {
        if (live) setAiAvailable(false);
      }
    };
    void poll();
    const timer = setInterval(poll, 15000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [engine]);
  useEffect(() => {
    if (!project || !data?.document_id) return;
    let live = true;
    const poll = async () => {
      try {
        const jobs = await api<Job[]>(`/projects/${project.id}/jobs`);
        if (live) {
          setPreviousJobs(
            jobs.filter(
              (j) =>
                j.payload?.engine === engine &&
                j.payload.document_id === data.document_id &&
                j.payload.page === data.page,
            ),
          );
          const next = jobs.find((j) => j.id === job?.id);
          if (next) setJob(next);
          setJobError("");
        }
      } catch {
        if (live)
          setJobError(
            "Suivi de l’analyse indisponible. Les corrections sont conservées.",
          );
      }
    };
    void poll();
    const timer = setInterval(poll, 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [job?.id, project?.id, data?.document_id, data?.page, engine]);
  function install(value: ExampleData, example: Example | null = null) {
    setData(structuredClone(value));
    setRecord(example);
    setDirty(false);
    setSelected([]);
    history.current = [];
    future.current = [];
    setTool("select");
    setJob(null);
    setPreviousJobs([]);
    setApplied(false);
  }
  function change(value: ExampleData) {
    if (data) history.current = [...history.current.slice(-49), data];
    future.current = [];
    setData(value);
    setDirty(true);
  }
  function undo(redo = false) {
    if (!data) return;
    const from = redo ? future : history,
      to = redo ? history : future;
    const value = from.current.pop();
    if (value) {
      to.current.push(data);
      setData(value);
      setDirty(true);
    }
  }
  function discard() {
    return (
      !dirty || window.confirm("Abandonner les corrections non enregistrées ?")
    );
  }
  async function openProject(id: string) {
    if (!id || !discard()) return;
    const p = await api<Project>("/projects/" + id);
    setProject(p);
    install(empty(engine, p));
  }
  function updateLabel(id: string, patch: Partial<Label>) {
    if (!data) return;
    change({
      ...data,
      labels: data.labels.map((l) =>
        l.id === id ? { ...l, checked: false, ...patch } : l,
      ),
    });
  }
  function add(box: Box, segments: [Point, Point][] = []) {
    if (!data) return;
    const c = categories.find((c) => c.code === category);
    if (!c) return;
    const id = crypto.randomUUID();
    change({
      ...data,
      labels: [
        ...data.labels,
        {
          id,
          category,
          bbox: box,
          anchor: null,
          segments,
          mask_polygons: [],
          text: "",
          origin: "manual",
          checked: false,
        },
      ],
    });
    setSelected([id]);
    setTool("select");
  }
  async function save() {
    if (!data?.document_id) throw Error("Importer ou sélectionner un relevé.");
    const saved = await api<Example>(
      prefix + "/examples" + (record ? "/" + record.id : ""),
      record ? "PUT" : "POST",
      data,
    );
    setData(saved.data);
    setRecord(saved);
    setDirty(false);
    history.current = [];
    future.current = [];
    await onSaved();
    return saved;
  }
  async function decision(status: "validated" | "rejected") {
    if (!data) return;
    const saved = dirty || !record ? await save() : record;
    const next = await api<Example>(
      `${prefix}/examples/${saved.id}/decision`,
      "POST",
      { revision: saved.revision, status, reason },
    );
    setData(next.data);
    setRecord(next);
    await onSaved();
  }
  const source = project?.documents.find((d) => d.id === data?.document_id),
    page = source?.pages[(data?.page || 1) - 1];
  const chosen = data?.labels.find((l) => l.id === selected[0]),
    kind = categories.find((c) => c.code === chosen?.category)?.kind;
  const annotations: Annotation[] = (data?.labels || []).map((l) => ({
    id: l.id,
    source_document_id: data!.document_id,
    source_page: data!.page,
    bbox: l.bbox,
    anchor: l.anchor,
    anchor_kind: "manual",
    text:
      l.text ||
      categories.find((c) => c.code === l.category)?.name ||
      l.category,
    color: "",
    shape: "",
    confidence: 1,
    method: l.origin,
    equipment_type: l.category,
    asset_id: null,
    floor_id: data!.floor_id,
    rotation_deg: 0,
    size_mm: 6,
    target: null,
    status: l.checked ? "confirmed" : "review",
    review: {
      equipment: false,
      asset: false,
      floor: false,
      position: false,
      orientation: false,
      size: false,
    },
    evidence: "",
  }));
  const centerlines = Object.fromEntries(
    (data?.labels || [])
      .filter((l) => l.segments.length)
      .map((l) => [l.id, l.segments]),
  );
  const proposed = [
    ...(job?.result?.annotations || [])
      .filter(
        (a) =>
          a.source_document_id === data?.document_id &&
          a.source_page === data?.page,
      )
      .map((a) => ({ bbox: a.bbox, text: a.text })),
    ...(job?.result?.proposals || [])
      .filter(
        (a) => a.document_id === data?.document_id && a.page === data?.page,
      )
      .map((a) => ({
        bbox: a.bbox,
        text: `Classe source ${a.source_class} · ${Math.round(a.score * 100)} %`,
      })),
  ];
  return (
    <div>
      <div className="training-toolbar">
        <label>
          Projet d’apprentissage
          <select
            aria-label="Projet d’apprentissage"
            value={project?.id || ""}
            onChange={(e) => void perform(() => openProject(e.target.value))}
          >
            <option value="">Choisir un projet</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!discard()) return;
            void perform(async () => {
              const p = await api<Project>("/projects", "POST", {
                name: projectName,
              });
              setProject(p);
              install(empty(engine, p));
              setProjectName("");
              await refreshProjects();
            });
          }}
          className="training-inline"
        >
          <label>
            Nouveau projet
            <input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              required
              maxLength={120}
            />
          </label>
          <button>Créer le projet</button>
        </form>
      </div>
      {!project && (
        <div className="training-empty">
          <h3>Commencez par un relevé.</h3>
          <p>
            Choisissez un projet ou créez-en un, puis importez votre PDF ou
            votre image.
          </p>
        </div>
      )}
      {project && data && (
        <>
          <div className="training-toolbar">
            <label>
              Importer un plan
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file || !discard()) return;
                  void perform(async () => {
                    const form = new FormData();
                    form.append("role", "survey");
                    form.append("file", file);
                    await api(
                      `/projects/${project.id}/documents`,
                      "POST",
                      form,
                    );
                    const next = await api<Project>("/projects/" + project.id);
                    setProject(next);
                    install(
                      empty(
                        engine,
                        next,
                        next.documents.filter((d) => d.role === "survey").at(-1)
                          ?.id,
                      ),
                    );
                  });
                }}
              />
            </label>
            <label>
              Document
              <select
                aria-label="Document"
                value={data.document_id}
                onChange={(e) => {
                  if (discard())
                    install(empty(engine, project, e.target.value));
                }}
              >
                <option value="">Choisir un relevé</option>
                {project.documents
                  .filter((d) => d.role === "survey")
                  .map((d) => (
                    <option value={d.id} key={d.id}>
                      {d.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Page
              <select
                aria-label="Page"
                value={data.page}
                onChange={(e) => {
                  if (discard())
                    install(
                      empty(
                        engine,
                        project,
                        data.document_id,
                        Number(e.target.value),
                      ),
                    );
                }}
              >
                {source?.pages.map((p) => (
                  <option key={p.number}>{p.number}</option>
                ))}
              </select>
            </label>
            <label>
              Niveau
              <select
                aria-label="Niveau"
                value={data.floor_id || ""}
                onChange={(e) => {
                  const f = project.state.floors.find(
                    (f) => f.id === e.target.value,
                  );
                  change({
                    ...data,
                    floor_id: f?.id || null,
                    region: f?.source_region || { ...wholePage },
                    rotation: f?.rotation_deg || 0,
                  });
                }}
              >
                <option value="">Page entière / zone libre</option>
                {project.state.floors
                  .filter(
                    (f) =>
                      f.source_document_id === data.document_id &&
                      f.source_page === data.page,
                  )
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Rotation
              <select
                aria-label="Rotation"
                value={data.rotation}
                onChange={(e) =>
                  change({
                    ...data,
                    rotation: Number(e.target.value) as ExampleData["rotation"],
                  })
                }
              >
                {[0, 90, 180, 270].map((r) => (
                  <option key={r} value={r}>
                    {r}°
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="training-check">
            <input
              type="checkbox"
              checked={project.metadata?.training_authorized === true}
              onChange={(e) => {
                const value = e.target.checked;
                void perform(async () => {
                  await api(`/projects/${project.id}/metadata`, "PUT", {
                    ...project.metadata,
                    training_authorized: value,
                  });
                  setProject(await api("/projects/" + project.id));
                });
              }}
            />
            J’autorise la réutilisation de ce projet pour l’apprentissage.
          </label>
          {page && (
            <div className="training-editor">
              <div className="training-canvas">
                <div className="training-toolbar compact">
                  <button
                    type="button"
                    className={tool === "select" ? "active" : ""}
                    onClick={() => setTool("select")}
                  >
                    Sélectionner
                  </button>
                  <button type="button" onClick={() => setTool("pan")}>
                    Déplacer la vue
                  </button>
                  <label>
                    Catégorie à ajouter
                    <select
                      aria-label="Catégorie à ajouter"
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                    >
                      {categories
                        .filter((c) => c.active && compatible(engine, c.kind))
                        .map((c) => (
                          <option key={c.code} value={c.code}>
                            {c.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setTool(
                        categories.find((c) => c.code === category)?.kind ===
                          "wall"
                          ? "line"
                          : "annotation",
                      )
                    }
                  >
                    {categories.find((c) => c.code === category)?.kind ===
                    "wall"
                      ? "Tracer un axe de mur"
                      : "Dessiner une annotation"}
                  </button>
                  <button type="button" onClick={() => setTool("floor")}>
                    Délimiter le niveau
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      change({
                        ...data,
                        region: { ...wholePage },
                        floor_id: null,
                      })
                    }
                  >
                    Page entière
                  </button>
                  <label>
                    Zoom
                    <input
                      aria-label="Zoom du plan"
                      type="range"
                      min="40"
                      max="300"
                      step="10"
                      value={zoom}
                      onChange={(e) => setZoom(Number(e.target.value))}
                    />
                  </label>
                  <label className="training-check">
                    <input
                      type="checkbox"
                      checked={showImage}
                      onChange={(e) => setShowImage(e.target.checked)}
                    />
                    Fond du plan
                  </label>
                  <button
                    type="button"
                    disabled={!history.current.length}
                    onClick={() => undo()}
                  >
                    Annuler la correction
                  </button>
                  <button
                    type="button"
                    disabled={!future.current.length}
                    onClick={() => undo(true)}
                  >
                    Rétablir
                  </button>
                </div>
                <PlanCanvas
                  image={url(
                    `/projects/${project.id}/documents/${data.document_id}/pages/${data.page}`,
                  )}
                  width={page.width}
                  height={page.height}
                  region={data.region}
                  rotation={data.rotation}
                  zoom={zoom}
                  tool={tool}
                  annotations={annotations}
                  selected={selected}
                  showBoxes
                  showAnchors
                  showImage={showImage}
                  centerlines={centerlines}
                  proposals={showProposals && !applied ? proposed : []}
                  onSelect={setSelected}
                  onBox={(box) => {
                    if (tool === "floor") {
                      change({ ...data, region: box, floor_id: null });
                      setTool("select");
                    } else add(box);
                  }}
                  onSegment={(a, b) => add(boxFor([[a, b]]), [[a, b]])}
                  onVertex={(id, segment, vertex, point) => {
                    const l = data.labels.find((l) => l.id === id);
                    if (l) {
                      const segments = structuredClone(l.segments);
                      segments[segment][vertex] = point;
                      updateLabel(id, { segments, bbox: boxFor(segments) });
                    }
                  }}
                  onAnchor={(point) => {
                    if (chosen) updateLabel(chosen.id, { anchor: point });
                    setTool("select");
                  }}
                  onMove={(id, patch) => {
                    const l = data.labels.find((l) => l.id === id);
                    if (!l) return;
                    if (patch.bbox && l.segments.length) {
                      const dx = patch.bbox.x - l.bbox.x,
                        dy = patch.bbox.y - l.bbox.y;
                      const segments = l.segments.map(
                        (s) =>
                          s.map((p) => ({
                            x: Math.max(0, Math.min(1, p.x + dx)),
                            y: Math.max(0, Math.min(1, p.y + dy)),
                          })) as [Point, Point],
                      );
                      updateLabel(id, { segments, bbox: boxFor(segments) });
                    } else
                      updateLabel(id, {
                        ...(patch.bbox ? { bbox: patch.bbox } : {}),
                        ...(patch.anchor ? { anchor: patch.anchor } : {}),
                      });
                  }}
                />
                {engine === "architecture" && (
                  <p className="training-hint">
                    Tracez un axe noir par mur. Déplacez ses extrémités pour le
                    corriger. Les portes et ouvertures coupent les axes à
                    l’enregistrement.
                  </p>
                )}
              </div>
              <aside className="training-properties">
                <h3>
                  Corrections{" "}
                  <span className="training-badge">{data.labels.length}</span>
                </h3>
                <div className="training-labels">
                  {data.labels.map((l, i) => (
                    <button
                      type="button"
                      key={l.id}
                      className={selected.includes(l.id) ? "active" : ""}
                      onClick={() => setSelected([l.id])}
                    >
                      {l.checked ? "✓" : "○"} {i + 1} ·{" "}
                      {l.text ||
                        categories.find((c) => c.code === l.category)?.name}
                    </button>
                  ))}
                </div>
                {chosen ? (
                  <>
                    <label>
                      Catégorie de l’annotation
                      <select
                        aria-label="Catégorie de l’annotation"
                        value={chosen.category}
                        onChange={(e) => {
                          const c = categories.find(
                            (c) => c.code === e.target.value,
                          );
                          updateLabel(chosen.id, {
                            category: e.target.value,
                            segments: c?.kind === "wall" ? chosen.segments : [],
                          });
                        }}
                      >
                        {categories
                          .filter(
                            (c) =>
                              c.active &&
                              compatible(engine, c.kind) &&
                              (kind === "wall"
                                ? c.kind === "wall"
                                : c.kind !== "wall"),
                          )
                          .map((c) => (
                            <option key={c.code} value={c.code}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      {kind === "text"
                        ? "Transcription exacte"
                        : "Texte de l’annotation"}
                      <textarea
                        aria-label={
                          kind === "text"
                            ? "Transcription exacte"
                            : "Texte de l’annotation"
                        }
                        value={chosen.text}
                        maxLength={4000}
                        onChange={(e) =>
                          updateLabel(chosen.id, { text: e.target.value })
                        }
                      />
                    </label>
                    {kind !== "wall" && (
                      <div className="training-box-fields">
                        {(["x", "y", "w", "h"] as const).map((k) => (
                          <label key={k}>
                            {k} (%)
                            <input
                              type="number"
                              min={k === "w" || k === "h" ? 0.01 : 0}
                              max={100}
                              step="0.01"
                              value={Number((chosen.bbox[k] * 100).toFixed(2))}
                              onChange={(e) => {
                                const b = {
                                  ...chosen.bbox,
                                  [k]: Number(e.target.value) / 100,
                                };
                                if (
                                  b.w > 0 &&
                                  b.h > 0 &&
                                  b.x + b.w <= 1 &&
                                  b.y + b.h <= 1
                                )
                                  updateLabel(chosen.id, { bbox: b });
                              }}
                            />
                          </label>
                        ))}
                      </div>
                    )}
                    {kind === "equipment" && (
                      <>
                        <button type="button" onClick={() => setTool("anchor")}>
                          Pointer l’implantation
                        </button>
                        <p>
                          {chosen.anchor
                            ? "Implantation renseignée."
                            : "Cliquez sur la position réelle de l’équipement."}
                        </p>
                      </>
                    )}
                    <label className="training-check">
                      <input
                        type="checkbox"
                        checked={chosen.checked}
                        onChange={(e) =>
                          updateLabel(chosen.id, { checked: e.target.checked })
                        }
                      />
                      Annotation vérifiée
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        change({
                          ...data,
                          labels: data.labels.filter((l) => l.id !== chosen.id),
                        });
                        setSelected([]);
                      }}
                    >
                      Supprimer l’annotation
                    </button>
                  </>
                ) : (
                  <p>
                    Sélectionnez une annotation ou dessinez-en une sur le plan.
                  </p>
                )}
              </aside>
            </div>
          )}
          {data.document_id && (
            <section className="training-card">
              <h3>Propositions IA</h3>
              <label>
                Analyses enregistrées
                <select
                  aria-label="Analyses enregistrées"
                  value={job?.id || ""}
                  onChange={(e) => {
                    setJob(
                      previousJobs.find((j) => j.id === e.target.value) || null,
                    );
                    setApplied(false);
                  }}
                >
                  <option value="">
                    Choisir une analyse de ce moteur et de cette page
                  </option>
                  {previousJobs.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.id.slice(0, 8)} · {statusNames[j.status] || j.status}
                    </option>
                  ))}
                </select>
              </label>
              <label className="training-check">
                <input
                  type="checkbox"
                  checked={showProposals}
                  onChange={(e) => setShowProposals(e.target.checked)}
                />
                Afficher les propositions sur le plan
              </label>
              <p>
                Une analyse peut démarrer le GPU. Ses propositions restent
                séparées de vos corrections.
              </p>
              <button
                disabled={
                  !aiAvailable ||
                  (!!job &&
                    !["completed", "failed", "cancelled"].includes(job.status))
                }
                onClick={() => {
                  if (
                    !window.confirm(
                      "Lancer une analyse IA sur ce relevé ? Le GPU peut être démarré et facturé.",
                    )
                  )
                    return;
                  void perform(async () => {
                    const next = await api<{ id: string; status: string }>(
                      `/projects/${project.id}/jobs`,
                      "POST",
                      {
                        document_id: data.document_id,
                        page: data.page,
                        engine,
                      },
                    );
                    setJob({ ...next, stage: "En attente", error: null });
                    setApplied(false);
                  });
                }}
              >
                Analyser avec l’IA
              </button>
              {!aiAvailable && (
                <p>
                  Moteur d’analyse indisponible. Vous pouvez annoter le plan
                  manuellement.
                </p>
              )}
              {job && (
                <>
                  <p role="status">
                    {statusNames[job.status] || job.status} · {job.stage}
                  </p>
                  {job.error && <p role="alert">{job.error}</p>}
                  {job.result && (
                    <>
                      {job.result.warnings.map((w) => (
                        <p key={w} className="training-warning">
                          {w}
                        </p>
                      ))}
                      {engine === "qwen" && (
                        <pre>
                          {JSON.stringify(job.result.observations, null, 2)}
                        </pre>
                      )}
                      {engine === "rtmdet" && (
                        <p>
                          Les classes source ne sont pas des catégories DOEMO.
                          Catégorie choisie pour la copie :{" "}
                          {categories.find((c) => c.code === category)?.name}.
                          Chaque boîte et chaque implantation doivent être
                          vérifiées.
                        </p>
                      )}
                      <details>
                        <summary>Résultat détaillé de l’analyse</summary>
                        <pre>{JSON.stringify(job.result, null, 2)}</pre>
                      </details>
                      <button
                        disabled={
                          applied ||
                          job.status !== "completed" ||
                          (engine !== "qwen" && !proposed.length)
                        }
                        onClick={() => {
                          const result = job.result!;
                          if (engine === "qwen")
                            change({
                              ...data,
                              observed: JSON.stringify(
                                result.observations,
                                null,
                                2,
                              ),
                            });
                          else {
                            const candidates = proposed.map(
                              (a) =>
                                ({
                                  id: crypto.randomUUID(),
                                  category:
                                    engine === "paddleocr"
                                      ? "HANDWRITING"
                                      : category,
                                  bbox: a.bbox,
                                  anchor: null,
                                  segments: [],
                                  mask_polygons: [],
                                  text: a.text,
                                  origin: `${engine}:${job.id}`,
                                  checked: false,
                                }) as Label,
                            );
                            change({
                              ...data,
                              labels: [...data.labels, ...candidates],
                            });
                          }
                          setApplied(true);
                        }}
                      >
                        Copier les propositions à vérifier
                      </button>
                    </>
                  )}
                </>
              )}
              {jobError && <p role="alert">{jobError}</p>}
            </section>
          )}
          {engine === "qwen" && (
            <section className="training-card training-fields">
              <h3>Conventions et interprétation</h3>
              <label>
                Réponse proposée par Qwen
                <textarea
                  aria-label="Réponse proposée par Qwen"
                  value={data.observed}
                  maxLength={16000}
                  onChange={(e) =>
                    change({ ...data, observed: e.target.value })
                  }
                />
              </label>
              <label>
                Convention DOEMO
                <input
                  value={data.convention}
                  maxLength={400}
                  placeholder="Ex. PCF"
                  onChange={(e) =>
                    change({ ...data, convention: e.target.value })
                  }
                />
              </label>
              <label>
                Interprétation corrigée
                <textarea
                  aria-label="Interprétation corrigée"
                  value={data.interpretation}
                  maxLength={16000}
                  onChange={(e) =>
                    change({ ...data, interpretation: e.target.value })
                  }
                />
              </label>
              <p>
                Ces corrections alimentent un référentiel. Elles ne modifient
                pas les poids de Qwen.
              </p>
            </section>
          )}
          <label>
            Notes
            <textarea
              aria-label="Notes"
              value={data.notes}
              maxLength={4000}
              onChange={(e) => change({ ...data, notes: e.target.value })}
            />
          </label>
          <div className="training-toolbar">
            <span role="status">
              {dirty
                ? "Corrections non enregistrées"
                : record
                  ? `${statusNames[record.status]} · révision ${record.revision}`
                  : "Nouvel exemple"}
            </span>
            <button
              className="primary"
              disabled={!data.document_id}
              onClick={() =>
                void perform(async () => {
                  await save();
                }, "Corrections enregistrées.")
              }
            >
              Enregistrer les corrections
            </button>
            <button
              disabled={
                !data.document_id ||
                project.metadata?.training_authorized !== true
              }
              onClick={() =>
                void perform(() => decision("validated"), "Exemple validé.")
              }
            >
              Valider l’exemple
            </button>
            <button
              onClick={() => download("DOEMO-corrections-locales.json", data)}
            >
              Sauver la copie locale
            </button>
          </div>
          {record && (
            <div className="training-inline">
              <label>
                Motif du rejet
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={2000}
                />
              </label>
              <button
                disabled={!reason.trim()}
                onClick={() =>
                  void perform(() => decision("rejected"), "Exemple rejeté.")
                }
              >
                Rejeter l’exemple
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
