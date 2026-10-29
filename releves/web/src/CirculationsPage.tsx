import { useEffect, useRef, useState } from "react";
import { api, download } from "./api";
import "./circulations.css";
type XY = [number, number];
type Shape = { shell: XY[]; holes: XY[][] };
type Region = {
  id: string;
  level: string;
  artboard: number;
  shape: Shape;
  category: string;
  status: string;
  confidence: number;
  reason: string;
  suggested: boolean;
};
type Data = {
  revision: number;
  rules: {
    include: string[];
    curve_tolerance_pt: number;
    confidence_threshold: number;
  };
  source_version: string;
  regions: Region[];
  warnings: string[];
  timings_ms: { total: number };
  color: Color | null;
  source: {
    document_id: string;
    source_name: string;
    provider: string;
    color_space: "RGB" | "CMYK";
    artboards: number[][];
    levels: { id: string; name: string; artboard: number; footprint: Shape }[];
    paths: {
      id: string;
      nodes: number[][];
      closed: boolean;
      filled: boolean;
      fill?: unknown[] | null;
      stroke?: unknown[] | null;
      stroke_width: number;
      visible: boolean;
      role: string;
      clipped: boolean;
      layer: string;
    }[];
    texts: { text: string; point: XY; level: string }[];
  };
};
type Color = {
  mode: "RGB" | "CMYK" | "SPOT";
  values: number[];
  swatch: string;
  opacity: number;
  tint: number;
  approved: boolean;
};
const outline = (s: Shape) =>
  [s.shell, ...s.holes]
    .map((r) => "M" + r.map((p) => `${p[0]},${-p[1]}`).join("L") + "Z")
    .join(" ");
type Hints = {
  roles: { id: string; role: string; confidence: number; reason: string }[];
  outlines: { id: string; artboard: number; reason: string }[];
  total_roles: number;
  total_outlines: number;
  excluded_paths: number;
};
const names: Record<string, string> = {
  circulation: "Circulation",
  room: "Local",
  technical: "Zone technique",
  outside: "Extérieur",
  unknown: "Indéterminée",
};
const previewColor = (c: unknown[] | null | undefined) => {
  if (!c) return "#333";
  const v = c.slice(1).map(Number);
  if (c[0] === "RGBColor") return `rgb(${v.slice(0, 3).join(",")})`;
  if (c[0] === "CMYKColor")
    return `rgb(${v
      .slice(0, 3)
      .map((x) => Math.round(255 * (1 - x / 100) * (1 - v[3] / 100)))
      .join(",")})`;
  if (c[0] === "GrayColor")
    return `rgb(${Array(3)
      .fill(255 * (1 - v[0] / 100))
      .join(",")})`;
  return "#555";
};
export function CirculationsPage({ onBack }: { onBack: () => void }) {
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]),
    [project, setProject] = useState(""),
    [documents, setDocuments] = useState<{ id: string }[]>([]),
    [data, setData] = useState<Data | null>(null),
    [level, setLevel] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<
      | "select"
      | "add"
      | "replace"
      | "hole"
      | "split"
      | "qualify"
      | "footprint"
      | "threshold"
    >("select"),
    [points, setPoints] = useState<XY[]>([]),
    [editShape, setEditShape] = useState<Shape | null>(null),
    [drag, setDrag] = useState<number | null>(null);
  const [include, setInclude] = useState<string[]>([]),
    [tolerance, setTolerance] = useState(0.1),
    [threshold, setThreshold] = useState(0.95),
    [zoom, setZoom] = useState(1),
    [colorText, setColorText] = useState(""),
    [swatch, setSwatch] = useState(""),
    [opacity, setOpacity] = useState(100),
    [spot, setSpot] = useState(false),
    [aiJob, setAiJob] = useState("");
  const [pathIds, setPathIds] = useState<string[]>([]),
    [board, setBoard] = useState(0),
    [levelName, setLevelName] = useState("RDC"),
    [role, setRole] = useState("wall"),
    [hints, setHints] = useState<Hints | null>(null),
    [hintId, setHintId] = useState("");
  const undo = useRef<number[]>([]),
    redo = useRef<number[]>([]),
    svg = useRef<SVGSVGElement>(null);
  const base = `/projects/${project}/circulations`,
    path = data ? base + "/" + encodeURIComponent(data.source.document_id) : "",
    current = data?.source.levels.find((l) => l.id === level),
    r = data?.regions.find((v) => v.id === selected[0]);
  useEffect(() => {
    api<{ id: string; name: string }[]>("/projects")
      .then(setProjects)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    setData(null);
    setSelected([]);
    setHints(null);
    setMode("select");
    setPathIds([]);
    setPoints([]);
    undo.current = [];
    redo.current = [];
    if (project)
      api<{ id: string }[]>(base)
        .then(setDocuments)
        .catch((e) => setError(String(e)));
  }, [project]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  function accept(d: Data) {
    if (data?.source.document_id !== d.source.document_id) {
      undo.current = [];
      redo.current = [];
      setMode("select");
    }
    setData(d);
    setInclude(d.rules.include);
    setTolerance(d.rules.curve_tolerance_pt);
    setThreshold(d.rules.confidence_threshold);
    if (!d.source.levels.some((l) => l.id === level))
      setLevel(d.source.levels[0]?.id || "");
    setSelected([]);
    setEditShape(null);
    setPoints([]);
    setPathIds([]);
    setHints(null);
    setHintId("");
    setBoard((b) => (b < d.source.artboards.length ? b : 0));
  }
  async function change(
    operation: string,
    extra: Record<string, unknown> = {},
  ) {
    if (!data) return;
    const before = data.revision;
    const next = await api<Data>(path, "PUT", {
      revision: before,
      operation,
      ids: selected,
      ...extra,
    });
    undo.current.push(before);
    redo.current = [];
    accept(next);
  }
  async function prepare(
    operation: string,
    extra: Record<string, unknown> = {},
  ) {
    if (!data) return;
    const reviewed = data.regions.some(
      (r) =>
        r.status !== "proposed" || r.reason === "Contour corrigé à valider",
    );
    if (
      reviewed &&
      !confirm(
        "Modifier les limites recalcule les régions. Les corrections restent dans l’historique. Continuer ?",
      )
    )
      return;
    const before = data.revision;
    const next = await api<Data>(path + "/preparation", "POST", {
      revision: before,
      operation,
      replace_reviewed: reviewed,
      ...extra,
    });
    undo.current.push(before);
    redo.current = [];
    accept(next);
    setMode("select");
  }
  function prepareMode(value: typeof mode) {
    setMode(value);
    setPoints([]);
    setSelected([]);
    setEditShape(null);
  }
  function choosePath(id: string, shift = false) {
    setPathIds(
      shift
        ? pathIds.includes(id)
          ? pathIds.filter((v) => v !== id)
          : [...pathIds, id]
        : [id],
    );
  }
  async function history(back: boolean) {
    if (!data) return;
    const from = back ? undo : redo,
      to = back ? redo : undo;
    if (!from.current.length) return;
    const rev = from.current.at(-1)!;
    const next = await api<Data>(path, "PUT", {
      revision: data.revision,
      operation: "restore",
      restore_revision: rev,
    });
    from.current.pop();
    to.current.push(data.revision);
    accept(next);
  }
  function coords(e: React.PointerEvent<SVGSVGElement>): XY {
    const p = svg.current!.createSVGPoint();
    p.x = e.clientX;
    p.y = e.clientY;
    const matrix = svg.current!.getScreenCTM()!;
    const q = p.matrixTransform(matrix.inverse());
    if ((mode === "threshold" || mode === "footprint") && data) {
      let distance = 8,
        nearest: XY | undefined;
      for (const path of data.source.paths)
        if (path.visible && !path.clipped)
          for (const n of path.nodes) {
            const dx = n[0] - q.x,
              dy = -n[1] - q.y;
            const pixels = Math.hypot(
              matrix.a * dx + matrix.c * dy,
              matrix.b * dx + matrix.d * dy,
            );
            if (pixels < distance) {
              distance = pixels;
              nearest = [n[0], n[1]];
            }
          }
      if (nearest) return nearest;
    }
    return [q.x, -q.y];
  }
  function pick(id: string, shift: boolean) {
    setSelected(
      shift
        ? selected.includes(id)
          ? selected.filter((i) => i !== id)
          : [...selected, id]
        : [id],
    );
    setEditShape(null);
  }
  const preparing = ["qualify", "footprint", "threshold"].includes(mode);
  const rect = data
      ? data.source.artboards[preparing ? board : (current?.artboard ?? board)]
      : [0, 100, 100, 0],
    width = rect[2] - rect[0],
    height = rect[1] - rect[3];
  function pathD(p: Data["source"]["paths"][number]) {
    const ns = p.nodes;
    let d = `M${ns[0][0]},${-ns[0][1]}`;
    for (let i = 0; i < (p.closed ? ns.length : ns.length - 1); i++) {
      const a = ns[i],
        b = ns[(i + 1) % ns.length];
      d += `C${a[4]},${-a[5]} ${b[2]},${-b[3]} ${b[0]},${-b[1]}`;
    }
    return d + (p.closed ? "Z" : "");
  }
  return (
    <main className="circulation-page">
      <header>
        <button onClick={onBack}>← Atelier</button>
        <h1>Vert des circulations</h1>
        <span>Calcul vectoriel · revue · Illustrator</span>
      </header>
      <div className="circ-toolbar">
        <label>
          Projet{" "}
          <select
            aria-label="Projet"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">Choisir</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Géométrie Illustrator{" "}
          <input
            aria-label="Géométrie Illustrator"
            disabled={!project || busy}
            type="file"
            accept=".json"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f)
                void run(async () => {
                  if (f.size > 32 * 1024 * 1024)
                    throw Error("Fichier trop volumineux");
                  const source = JSON.parse(await f.text());
                  accept(
                    await api<Data>(base, "POST", {
                      source,
                      rules: {
                        include,
                        curve_tolerance_pt: tolerance,
                        confidence_threshold: threshold,
                      },
                    }),
                  );
                  setDocuments(await api(base));
                });
            }}
          />
        </label>
        <select
          aria-label="Document enregistré"
          disabled={busy}
          value={data?.source.document_id || ""}
          onChange={(e) => {
            if (e.target.value)
              void run(async () =>
                accept(
                  await api(base + "/" + encodeURIComponent(e.target.value)),
                ),
              );
          }}
        >
          <option value="">Documents enregistrés</option>
          {documents.map((d) => (
            <option key={d.id}>{d.id}</option>
          ))}
        </select>
      </div>
      <details>
        <summary>Règles de reconstruction</summary>
        <p>
          Qualifier les murs et seuils dans la préparation ci-dessous ou dans
          Illustrator. Les seuils sont virtuels ; un passage de circulation
          reste ouvert.
        </p>
        {["hall", "stair", "landing", "sas", "outside"].map((v, i) => (
          <label key={v}>
            <input
              type="checkbox"
              checked={include.includes(v)}
              onChange={(e) =>
                setInclude(
                  e.target.checked
                    ? [...include, v]
                    : include.filter((x) => x !== v),
                )
              }
            />
            {
              [
                "Halls",
                "Escaliers",
                "Paliers",
                "Sas",
                "Circulations extérieures dans l’emprise",
              ][i]
            }{" "}
          </label>
        ))}
        <label>
          Tolérance des courbes (pt){" "}
          <input
            type="number"
            min="0.01"
            max="1"
            step="0.01"
            value={tolerance}
            onChange={(e) => setTolerance(+e.target.value)}
          />
        </label>
        <label>
          Seuil des propositions{" "}
          <input
            type="number"
            min="0.5"
            max="1"
            step="0.01"
            value={threshold}
            onChange={(e) => setThreshold(+e.target.value)}
          />
        </label>
        <button
          disabled={!data || busy}
          onClick={() =>
            void run(async () => {
              if (!data) return;
              const hasReview = data.regions.some(
                (r) => r.status !== "proposed",
              );
              if (
                hasReview &&
                !confirm(
                  "Recalculer ? Les corrections actuelles restent dans l’historique, mais les nouvelles propositions devront être revues.",
                )
              )
                return;
              accept(
                await api<Data>(base, "POST", {
                  source: data.source,
                  rules: {
                    include,
                    curve_tolerance_pt: tolerance,
                    confidence_threshold: threshold,
                  },
                  revision: data.revision,
                  replace_reviewed: hasReview,
                }),
              );
            })
          }
        >
          Recalculer
        </button>
      </details>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!data ? (
        <p>
          Exécutez DOEMO-Exporter-Circulations.jsx dans Illustrator, puis
          importez son JSON ici. La sauvegarde finale AI s’effectue avec
          DOEMO-Importer-Circulations.jsx.
        </p>
      ) : (
        <>
          <div className="circ-toolbar">
            <select
              aria-label="Niveau"
              value={level}
              onChange={(e) => {
                setLevel(e.target.value);
                setSelected([]);
              }}
            >
              {data.source.levels.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
            <button
              disabled={busy || !undo.current.length}
              onClick={() => void run(() => history(true))}
            >
              Annuler
            </button>
            <button
              disabled={busy || !redo.current.length}
              onClick={() => void run(() => history(false))}
            >
              Rétablir
            </button>
            <button onClick={() => setZoom(Math.min(4, zoom + 0.25))}>
              Zoom +
            </button>
            <button onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}>
              Zoom −
            </button>
            <span>
              {data.regions.length} régions · {data.timings_ms.total} ms ·
              révision {data.revision}
            </span>
          </div>
          <details
            className="circ-preparation"
            open={!data.source.levels.length || preparing}
          >
            <summary>Préparer les murs et les niveaux</summary>
            <p>
              Confirmer les tracés utiles et l’emprise réelle. Les propositions
              peuvent contenir des cotes, du mobilier ou des cartouches. Aucun
              rôle ni seuil n’est appliqué automatiquement.
            </p>
            <div className="circ-toolbar">
              <label>
                Plan de travail{" "}
                <select
                  aria-label="Plan de travail"
                  value={board}
                  onChange={(e) => {
                    setBoard(+e.target.value);
                    prepareMode("qualify");
                    setPathIds([]);
                  }}
                >
                  {data.source.artboards.map((_, i) => (
                    <option value={i} key={i}>
                      {i + 1}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={busy}
                onClick={() => {
                  prepareMode("qualify");
                  void run(async () =>
                    setHints(await api(path + "/preparation")),
                  );
                }}
              >
                Proposer les tracés à vérifier
              </button>
              <button onClick={() => prepareMode("qualify")}>
                Sélectionner des tracés
              </button>
              <button onClick={() => prepareMode("select")}>
                Revenir aux régions
              </button>
            </div>
            {hints && (
              <>
                <p>
                  {hints.total_roles} propositions de rôle ·{" "}
                  {hints.total_outlines} contours fermés ·{" "}
                  {hints.excluded_paths} tracés masqués ou composés exclus.
                  Affichage limité à 1 000 rôles et 200 contours.
                </p>
                <label>
                  Proposition à examiner{" "}
                  <select
                    aria-label="Proposition à examiner"
                    value={hintId}
                    onChange={(e) => {
                      setHintId(e.target.value);
                      if (!e.target.value) {
                        setPathIds([]);
                        return;
                      }
                      const [kind, index] = e.target.value.split(":");
                      const h =
                        kind === "role"
                          ? hints.roles[+index]
                          : hints.outlines[+index];
                      if (h) {
                        setPathIds([h.id]);
                        prepareMode("qualify");
                        if (kind === "role") setRole(hints.roles[+index].role);
                        else setBoard(hints.outlines[+index].artboard);
                      }
                    }}
                  >
                    <option value="">Choisir une proposition</option>
                    {hints.roles.map((h, i) => (
                      <option key={"role" + i} value={"role:" + i}>
                        {h.id} · {h.role} · {h.reason}
                      </option>
                    ))}
                    {hints.outlines.map((h, i) => (
                      <option key={"outline" + i} value={"outline:" + i}>
                        {h.id} · emprise possible · {h.reason}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            <p>
              {pathIds.length} tracé(s) sélectionné(s). En mode préparation,
              cliquer sur un trait ; Majuscule pour une sélection multiple. Les
              tracés sélectionnés apparaissent en violet.
            </p>
            <div className="circ-toolbar">
              <label>
                Rôle confirmé{" "}
                <select
                  aria-label="Rôle confirmé"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  {[
                    ["wall", "Mur / cloison"],
                    ["boundary", "Limite"],
                    ["door_threshold", "Seuil droit"],
                    ["passage", "Passage ouvert"],
                    ["obstacle", "Obstacle rempli"],
                    ["existing_green", "Vert existant"],
                    ["unknown", "Non qualifié"],
                  ].map(([v, n]) => (
                    <option key={v} value={v}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={busy || !pathIds.length}
                onClick={() =>
                  void run(() => prepare("roles", { ids: pathIds, role }))
                }
              >
                Confirmer le rôle des tracés
              </button>
              <button
                disabled={
                  busy ||
                  !pathIds.length ||
                  pathIds.some((id) => !id.startsWith("virtual-threshold-"))
                }
                onClick={() =>
                  void run(() => prepare("remove_threshold", { ids: pathIds }))
                }
              >
                Retirer les seuils virtuels
              </button>
            </div>
            <label>
              Nom du niveau à définir{" "}
              <input
                aria-label="Nom du niveau à définir"
                value={levelName}
                onChange={(e) => setLevelName(e.target.value)}
              />
            </label>
            <div className="circ-toolbar">
              <button
                disabled={busy || pathIds.length !== 1 || !levelName.trim()}
                onClick={() =>
                  void run(() =>
                    prepare("footprint", {
                      ids: pathIds,
                      level_id: levelName.trim(),
                      name: levelName.trim(),
                      artboard: board,
                    }),
                  )
                }
              >
                Utiliser le contour sélectionné comme emprise
              </button>
              <button
                disabled={busy || !levelName.trim()}
                onClick={() => prepareMode("footprint")}
              >
                Tracer l’emprise réelle
              </button>
              <button
                disabled={busy || !current}
                onClick={() => {
                  setBoard(current!.artboard);
                  prepareMode("threshold");
                }}
              >
                Tracer un seuil entre jambages
              </button>
              <button
                disabled={busy || !current}
                onClick={() =>
                  void run(() => prepare("remove_level", { level_id: level }))
                }
              >
                Retirer l’emprise du niveau
              </button>
            </div>
            {(mode === "footprint" || mode === "threshold") && (
              <>
                <p>
                  {mode === "footprint"
                    ? "Cliquer les sommets du contour du bâtiment, sans reprendre le rectangle englobant."
                    : "Cliquer exactement les deux jambages de la porte. Le seuil sépare un local ; ne pas fermer un passage de circulation."}{" "}
                  {points.length} point(s).
                </p>
                <button
                  onClick={() => setPoints(points.slice(0, -1))}
                  disabled={!points.length}
                >
                  Retirer le dernier point
                </button>
                <button
                  disabled={
                    busy ||
                    (mode === "footprint"
                      ? points.length < 3
                      : points.length !== 2)
                  }
                  onClick={() =>
                    void run(() =>
                      prepare(mode, {
                        level_id:
                          mode === "footprint" ? levelName.trim() : level,
                        name: levelName.trim(),
                        artboard: board,
                        ...(mode === "footprint"
                          ? { shape: { shell: points, holes: [] } }
                          : { points }),
                      }),
                    )
                  }
                >
                  Confirmer {mode === "footprint" ? "l’emprise" : "le seuil"}
                </button>
              </>
            )}
          </details>
          <div className="circ-layout">
            <div className="circ-canvas">
              <svg
                ref={svg}
                aria-label="Plan et régions"
                viewBox={`${rect[0]} ${-rect[1]} ${width} ${height}`}
                style={{ width: `${zoom * 100}%`, minHeight: 550 }}
                onPointerDown={(e) => {
                  if (
                    mode !== "select" &&
                    mode !== "qualify" &&
                    (mode !== "threshold" || points.length < 2)
                  ) {
                    setPoints([...points, coords(e)]);
                  }
                }}
                onPointerMove={(e) => {
                  if (drag !== null && r) {
                    const s = structuredClone(editShape || r.shape);
                    s.shell[drag] = coords(e);
                    if (drag === 0 && s.shell.length > 1)
                      s.shell[s.shell.length - 1] = s.shell[0];
                    setEditShape(s);
                  }
                }}
                onPointerUp={() => setDrag(null)}
              >
                <rect
                  x={rect[0]}
                  y={-rect[1]}
                  width={width}
                  height={height}
                  fill="white"
                />
                {!preparing &&
                  data.regions
                    .filter((v) => v.level === level)
                    .map((v) => (
                      <path
                        key={v.id}
                        d={outline(
                          selected[0] === v.id && editShape
                            ? editShape
                            : v.shape,
                        )}
                        fillRule="evenodd"
                        fill={
                          v.status === "rejected"
                            ? "#ddd"
                            : v.status === "validated"
                              ? "#b4ce91"
                              : v.suggested
                                ? "#d3e3b8"
                                : "#fff2c4"
                        }
                        stroke={
                          selected.includes(v.id)
                            ? "#5742cf"
                            : v.status === "rejected"
                              ? "#a13c36"
                              : "#bf9d40"
                        }
                        strokeWidth={selected.includes(v.id) ? 1.5 : 0.4}
                        onClick={(e) => {
                          if (mode === "select") pick(v.id, e.shiftKey);
                        }}
                      >
                        <title>
                          {names[v.category]} : {v.reason}
                        </title>
                      </path>
                    ))}
                <g pointerEvents="none">
                  {data.source.paths
                    .filter((p) => p.visible)
                    .map((p) => (
                      <path
                        key={p.id}
                        d={pathD(p)}
                        fill={p.filled ? previewColor(p.fill) : "none"}
                        stroke={
                          p.role === "door_threshold"
                            ? preparing
                              ? "#c35c0b"
                              : "none"
                            : previewColor(p.stroke)
                        }
                        strokeWidth={
                          p.stroke_width ||
                          (p.role === "door_threshold" ? 0.7 : 0.2)
                        }
                        opacity={p.role === "unknown" ? 0.45 : 1}
                      />
                    ))}
                  {data.source.texts
                    .filter((t) => !t.level || t.level === level)
                    .map((t, i) => (
                      <text
                        key={i}
                        x={t.point[0]}
                        y={-t.point[1]}
                        fontSize={Math.max(width / 150, 2)}
                        textAnchor="middle"
                      >
                        {t.text}
                      </text>
                    ))}
                </g>
                {preparing && (
                  <g pointerEvents="none">
                    {data.source.levels
                      .filter((l) => l.artboard === board)
                      .map((l) => (
                        <path
                          key={l.id}
                          d={outline(l.footprint)}
                          fill="none"
                          stroke="#068894"
                          strokeDasharray="3 2"
                          strokeWidth=".7"
                        />
                      ))}
                  </g>
                )}
                {mode === "qualify" &&
                  data.source.paths
                    .filter((p) => p.visible && !p.clipped)
                    .map((p) => (
                      <path
                        key={"pick" + p.id}
                        data-path-id={p.id}
                        d={pathD(p)}
                        fill="none"
                        stroke={
                          pathIds.includes(p.id) ? "#6843da" : "transparent"
                        }
                        strokeWidth={
                          pathIds.includes(p.id)
                            ? 2
                            : Math.max(p.stroke_width, width / 200)
                        }
                        pointerEvents="stroke"
                        onClick={(e) => {
                          e.stopPropagation();
                          choosePath(p.id, e.shiftKey);
                        }}
                      >
                        <title>
                          {p.id} · {p.layer} · {p.role}
                        </title>
                      </path>
                    ))}
                {r &&
                  mode === "select" &&
                  (editShape || r.shape).shell.slice(0, -1).map((p, i) => (
                    <circle
                      key={i}
                      cx={p[0]}
                      cy={-p[1]}
                      r={width / 350}
                      fill="#5742cf"
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        setDrag(i);
                        svg.current?.setPointerCapture(e.pointerId);
                      }}
                    />
                  ))}
                {points.length > 0 && (
                  <polyline
                    points={points.map((p) => `${p[0]},${-p[1]}`).join(" ")}
                    fill="none"
                    stroke="#5742cf"
                    strokeWidth="1"
                  />
                )}
              </svg>
            </div>
            <aside>
              <h2>Contrôle du dessinateur</h2>
              <p>
                Vert : validé · vert pâle : proposé · jaune : incertain · gris :
                exclu. Les couleurs de cette revue sont indicatives ; la nuance
                de sortie se valide ci-dessous.
              </p>
              {r && (
                <>
                  <h3>{names[r.category]}</h3>
                  <p>{r.reason}</p>
                  <p>
                    Confiance indicative : {Math.round(r.confidence * 100)} %
                  </p>
                </>
              )}
              <button
                disabled={preparing || !selected.length || busy}
                onClick={() => void run(() => change("accept"))}
              >
                Ceci est une circulation
              </button>
              <button
                disabled={preparing || !selected.length || busy}
                onClick={() =>
                  void run(() => change("reject", { category: "room" }))
                }
              >
                Ceci n’est pas une circulation
              </button>
              <button
                disabled={preparing || !selected.length || busy}
                onClick={() =>
                  void run(() => change("reject", { category: "unknown" }))
                }
              >
                Retirer du vert
              </button>
              <button
                disabled={selected.length < 2 || busy}
                onClick={() => void run(() => change("merge"))}
              >
                Fusionner la sélection
              </button>
              <label>
                Correction{" "}
                <select
                  aria-label="Mode de correction"
                  value={preparing ? "select" : mode}
                  onChange={(e) => {
                    setMode(e.target.value as typeof mode);
                    setPoints([]);
                  }}
                >
                  <option value="select">
                    Sélection / déplacer les sommets
                  </option>
                  <option value="add">Ajouter une zone</option>
                  <option value="replace">Remplacer le contour</option>
                  <option value="hole">Ajouter un évidement</option>
                  <option value="split">Séparer par une ligne</option>
                </select>
              </label>
              {mode !== "select" && !preparing && (
                <p>
                  Sélectionner d’abord une région du niveau, puis cliquer pour
                  tracer {mode === "split" ? "la ligne" : "le contour"}.
                </p>
              )}
              <button
                disabled={
                  busy ||
                  preparing ||
                  (!editShape && points.length < (mode === "split" ? 2 : 3)) ||
                  !selected.length
                }
                onClick={() =>
                  void run(async () => {
                    await change(editShape ? "replace" : mode, {
                      geometry:
                        editShape ||
                        (mode === "split"
                          ? points
                          : { shell: points, holes: [] }),
                    });
                    setMode("select");
                  })
                }
              >
                Appliquer le contour
              </button>
              <h3>Nuance de sortie {data.source.color_space}</h3>
              <label>
                <input
                  type="checkbox"
                  checked={spot}
                  onChange={(e) => setSpot(e.target.checked)}
                />{" "}
                Ton direct existant
              </label>
              {spot ? (
                <label>
                  Nom exact de nuance{" "}
                  <input
                    value={swatch}
                    onChange={(e) => setSwatch(e.target.value)}
                  />
                </label>
              ) : (
                <label>
                  Composantes {data.source.color_space} séparées par des
                  virgules{" "}
                  <input
                    aria-label="Composantes couleur"
                    placeholder={
                      data.source.color_space === "RGB"
                        ? "R, V, B (0–255)"
                        : "C, M, J, N (0–100)"
                    }
                    value={colorText}
                    onChange={(e) => setColorText(e.target.value)}
                  />
                </label>
              )}
              <label>
                Opacité %{" "}
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={opacity}
                  onChange={(e) => setOpacity(+e.target.value)}
                />
              </label>
              <button
                disabled={
                  busy || (!spot && !colorText.trim()) || (spot && !swatch)
                }
                onClick={() =>
                  void run(() =>
                    change("color", {
                      color: {
                        mode: spot ? "SPOT" : data.source.color_space,
                        values: spot ? [] : colorText.split(",").map(Number),
                        swatch: spot ? swatch : "",
                        opacity,
                        tint: 100,
                        approved: true,
                      },
                    }),
                  )
                }
              >
                Valider la nuance
              </button>
              <p>
                {data.color?.approved
                  ? "Nuance de sortie validée"
                  : "Aucune nuance de sortie validée"}
              </p>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    download(
                      "circulations-validees.json",
                      await api(path + "/export"),
                    );
                    setNotice(
                      "Exécuter DOEMO-Importer-Circulations.jsx avec ce JSON et le fichier AI source.",
                    );
                  })
                }
              >
                Préparer la copie Illustrator
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    const v = await api<{ ids: string[] }>(
                      path + "/corrections",
                      "POST",
                    );
                    setNotice(
                      v.ids.length +
                        " corrections conservées pour la page Entraînement.",
                    );
                  })
                }
              >
                Conserver pour l’apprentissage
              </button>
              <details>
                <summary>Aide IA sur les zones indéterminées</summary>
                <p>
                  Réutiliser une analyse Qwen ou PaddleOCR terminée sur ce même
                  fichier. Les libellés complètent la classification ; les
                  contours restent vectoriels.
                </p>
                <input
                  aria-label="Identifiant analyse IA"
                  value={aiJob}
                  onChange={(e) => setAiJob(e.target.value)}
                />
                <button
                  disabled={!aiJob || busy}
                  onClick={() =>
                    void run(async () =>
                      accept(
                        await api(path + "/ai-hints", "POST", {
                          revision: data.revision,
                          job_id: aiJob,
                        }),
                      ),
                    )
                  }
                >
                  Importer les libellés
                </button>
              </details>
            </aside>
          </div>
          <details open>
            <summary>Contrôles géométriques</summary>
            <ul>
              {data.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </main>
  );
}
