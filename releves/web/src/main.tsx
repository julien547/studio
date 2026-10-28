import React, { useEffect, useRef, useState } from "react";

import { api, url, download } from "./api";
import { projectPoint, clearReview } from "./geometry";
import type {
  Annotation,
  Asset,
  Doc,
  Floor,
  Library,
  Point,
  Project,
  Registration,
  Review,
  State
} from "./types";
import "./style.css";

const emptyReview: Review = {
  equipment: false,
  asset: false,
  floor: false,
  position: false,
  orientation: false,
  size: false
};
const criteria: { key: keyof Review; label: string }[] = [
  { key: "equipment", label: "Équipement identifié" },
  { key: "asset", label: "Pictogramme exact vérifié" },
  { key: "floor", label: "Niveau vérifié" },
  { key: "position", label: "Position réelle vérifiée" },
  { key: "orientation", label: "Orientation vérifiée" },
  { key: "size", label: "Taille vérifiée" }
];
const colors: Record<string, string> = {
  red: "Rouge",
  orange: "Orange",
  yellow: "Jaune",
  green: "Vert",
  blue: "Bleu",
  violet: "Violet",
  pink: "Rose",
  unknown: "Non précisée"
};
const shapes: Record<string, string> = {
  colored_strokes: "Tracés colorés",
  point_or_circle: "Point ou cercle",
  unknown: "Forme à préciser",
  manual: "Ajout manuel"
};
const statuses: Record<string, string> = {
  review: "À vérifier",
  confirmed: "Confirmé",
  rejected: "Rejeté",
  missing_asset: "Symbole manquant",
  uncertain_position: "Position incertaine"
};
const pointText = (p: Point) => `${(p.x * 100).toFixed(1)} %, ${(p.y * 100).toFixed(1)} %`;
type Pair = { source: Point; target: Point };

export function AdvancedApp() {
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]),
    [p, setP] = useState<Project | null>(null),
    [libraries, setLibraries] = useState<Library[]>([]);
  const [docId, setDoc] = useState(""),
    [page, setPage] = useState(1),
    [floorId, setFloor] = useState(""),
    [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [dirty, setDirty] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false),
    [showRegistration, setShowRegistration] = useState(false),
    [showLegend, setShowLegend] = useState(false),
    [search, setSearch] = useState("");
  const [colorFilter, setColorFilter] = useState("all");
  const [zoom, setZoom] = useState(100),
    [rotation, setRotation] = useState(0),
    [opacity, setOpacity] = useState(0.3),
    [showOverlay, setShowOverlay] = useState(false);
  const [pick, setPick] = useState<"fit" | "check" | null>(null),
    [pending, setPending] = useState<Point | null>(null),
    [pairs, setPairs] = useState<Pair[]>([]),
    [checks, setChecks] = useState<Pair[]>([]),
    [model, setModel] = useState<"affine" | "homography">("affine");
  const [reports, setReports] = useState<
    {
      source: string;
      received_at?: string;
      report: {
        native_ai_verified: boolean;
        conformity_passed: boolean;
        placed_total: number;
        measurements: {
          placement_id: string;
          position_error_pt: number;
          validated_placement_matches: boolean;
        }[];
      };
    }[]
  >([]);
  const [mode, setMode] = useState("local"),
    [adding, setAdding] = useState(false),
    [legendPick, setLegendPick] = useState<Point | null>(null),
    [selectLegend, setSelectLegend] = useState(false);
  const inventoryInput = useRef<HTMLInputElement>(null),
    archiveInput = useRef<HTMLInputElement>(null);
  const state = p?.state,
    source = p?.documents.find((d) => d.id === docId),
    target = p?.documents.find((d) => d.role === "target"),
    floor = state?.floors.find((f) => f.id === floorId);
  const library = libraries.find((l) => l.id === state?.library_id),
    annotation = state?.annotations.find((a) => a.id === selected),
    asset = library?.assets.find((a) => a.id === annotation?.asset_id);
  const reg = state?.registrations.find(
    (r) => r.source_document_id === docId && r.source_page === page && r.floor_id === floorId
  );
  const legend = state?.legends.find(
    (l) => l.source_document_id === docId && l.source_page === page
  );
  const annotations =
    state?.annotations.filter((a) => a.source_document_id === docId && a.source_page === page) ||
    [];
  const allConfirmed = annotation && Object.values(annotation.review).every(Boolean);
  async function run(label: string, job: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await job();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }
  async function refresh() {
    setProjects(await api("/projects"));
    setLibraries(await api("/libraries"));
  }
  useEffect(() => {
    void run("Ouverture…", refresh);
  }, []);
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
    setPairs(reg?.source_points.map((s, i) => ({ source: s, target: reg.target_points[i] })) || []);
    setChecks(
      reg?.check_source_points.map((s, i) => ({ source: s, target: reg.check_target_points[i] })) ||
        []
    );
    setPick(null);
    setPending(null);
    setRotation(0);
  }, [docId, page, floorId, p?.id]);
  function edit(update: (s: State) => State) {
    if (p) {
      setP({ ...p, state: update(p.state) });
      setDirty(true);
    }
  }
  function change(changes: Partial<Annotation>) {
    if (annotation)
      edit((s) => ({
        ...s,
        annotations: s.annotations.map((a) => (a.id === selected ? clearReview(a, changes) : a))
      }));
  }
  function accept(project: Project) {
    setP(project);
    setDirty(false);
  }
  async function save() {
    if (!p) return null;
    const result = await api<Project>(`/projects/${p.id}/state`, "PUT", p.state);
    accept(result);
    return result;
  }
  async function open(id: string) {
    if (dirty && !confirm("Les modifications non enregistrées seront perdues. Continuer ?")) return;
    const project = await api<Project>(`/projects/${id}`);
    accept(project);
    setDoc(project.documents.find((d) => d.role === "survey")?.id || "");
    setPage(1);
    setFloor(project.state.floors[0]?.id || "");
    setSelected("");
  }
  function imageUrl(d: Doc | undefined, n: number) {
    return p && d ? url(`/projects/${p.id}/documents/${d.id}/pages/${n}`) : "";
  }
  async function create() {
    const name = prompt("Nom du dossier de relevés");
    if (!name) return;
    const project = await api<Project>("/projects", "POST", { name });
    accept(project);
    setDoc("");
    setFloor("");
    setSelected("");
    await refresh();
  }
  async function upload(file: File, role: "survey" | "target") {
    if (!p) return;
    const form = new FormData();
    form.append("file", file);
    form.append("role", role);
    const project = await api<Project>(`/projects/${p.id}/documents`, "POST", form);
    const current = state;
    setP({ ...project, state: current || project.state });
    if (role === "survey") {
      setDoc(project.documents.at(-1)!.id);
      setPage(1);
    }
    setNotice(`${file.name} importé, original conservé.`);
  }
  function chooseAnnotation(a: Annotation) {
    setSelected(a.id);
    setDoc(a.source_document_id);
    setPage(a.source_page);
    if (a.floor_id) setFloor(a.floor_id);
  }
  function clickSource(q: Point) {
    if (selectLegend) {
      if (!legendPick) {
        setLegendPick(q);
        return;
      }
      const x = Math.min(q.x, legendPick.x),
        y = Math.min(q.y, legendPick.y),
        w = Math.abs(q.x - legendPick.x),
        h = Math.abs(q.y - legendPick.y);
      if (w < 0.002 || h < 0.002) return;
      edit((s) => ({
        ...s,
        legends: [
          ...s.legends.filter((l) => !(l.source_document_id === docId && l.source_page === page)),
          {
            source_document_id: docId,
            source_page: page,
            bbox: { x, y, w, h },
            entries: legend?.entries || []
          }
        ]
      }));
      setLegendPick(null);
      setSelectLegend(false);
      return;
    }
    if (pick) {
      setPending(q);
      return;
    }
    if (adding && p && source) {
      const id = crypto.randomUUID().replaceAll("-", "");
      const a: Annotation = {
        id,
        source_document_id: docId,
        source_page: page,
        bbox: {
          x: Math.max(0, q.x - 0.005),
          y: Math.max(0, q.y - 0.005),
          w: Math.min(0.01, 1 - Math.max(0, q.x - 0.005)),
          h: Math.min(0.01, 1 - Math.max(0, q.y - 0.005))
        },
        anchor: q,
        anchor_kind: "manual",
        text: "",
        color: "unknown",
        shape: "manual",
        confidence: 0,
        method: "manual",
        equipment_type: "",
        asset_id: null,
        floor_id: floorId || null,
        rotation_deg: 0,
        size_mm: 7,
        target: null,
        status: "review",
        review: { ...emptyReview },
        evidence: "Ajout manuel du dessinateur"
      };
      edit((s) => ({ ...s, annotations: [...s.annotations, a] }));
      setSelected(id);
      setAdding(false);
      return;
    }
    if (annotation) change({ anchor: q, anchor_kind: "manual", target: null });
  }
  function clickTarget(q: Point) {
    if (pick) {
      if (!pending) {
        setNotice("Choisir d’abord le point sur le relevé.");
        return;
      }
      const pair = { source: pending, target: q };
      if (pick === "fit") setPairs([...pairs, pair]);
      else setChecks([...checks, pair]);
      setPending(null);
      return;
    }
    if (annotation) change({ target: q });
  }
  function addFloor() {
    if (!target) return;
    const name = prompt("Nom du niveau (ex. RDC, R+1)");
    if (!name) return;
    const id = "floor_" + crypto.randomUUID().slice(0, 8);
    edit((s) => ({
      ...s,
      floors: [
        ...s.floors,
        { id, name, target_page: 1, artboard_index: 0, target_group: "", confirmed: false }
      ]
    }));
    setFloor(id);
  }
  function editFloor(changes: Partial<Floor>) {
    edit((s) => ({
      ...s,
      floors: s.floors.map((f) => (f.id === floorId ? { ...f, ...changes } : f)),
      annotations: s.annotations.map((a) =>
        a.floor_id === floorId
          ? {
              ...a,
              review: { ...a.review, floor: false, position: false },
              status: a.status === "confirmed" ? "review" : a.status
            }
          : a
      )
    }));
  }
  async function calculate() {
    if (!p || !floor) return;
    const data: Registration = {
      source_document_id: docId,
      source_page: page,
      floor_id: floorId,
      model,
      matrix: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1]
      ],
      source_points: pairs.map((x) => x.source),
      target_points: pairs.map((x) => x.target),
      check_source_points: checks.map((x) => x.source),
      check_target_points: checks.map((x) => x.target),
      fit_error_px: 0,
      check_error_px: 0,
      max_error_px: 5,
      confirmed: false,
      architecture_confirmed: false
    };
    const solved = await api<Registration>(`/projects/${p.id}/registration`, "POST", data);
    edit((s) => ({
      ...s,
      registrations: [
        ...s.registrations.filter(
          (r) =>
            !(r.source_document_id === docId && r.source_page === page && r.floor_id === floorId)
        ),
        solved
      ],
      annotations: s.annotations.map((a) =>
        a.source_document_id === docId && a.source_page === page && a.floor_id === floorId
          ? {
              ...a,
              review: { ...a.review, position: false },
              status: a.status === "confirmed" ? "review" : a.status
            }
          : a
      )
    }));
    setPick(null);
    setNotice(
      "Recalage calculé. Enregistrer pour afficher la superposition, puis contrôler l’architecture et les positions."
    );
  }
  function editReg(changes: Partial<Registration>) {
    edit((s) => ({
      ...s,
      registrations: s.registrations.map((r) => (r === reg ? { ...r, ...changes } : r))
    }));
  }
  function mapped(a: Annotation) {
    if (a.target) return a.target;
    const r = state?.registrations.find(
      (r) =>
        r.source_document_id === a.source_document_id &&
        r.source_page === a.source_page &&
        r.floor_id === a.floor_id
    );
    return r && a.anchor ? projectPoint(r.matrix, a.anchor) : null;
  }
  async function analyze() {
    const current = await save();
    if (!current) return;
    const result = await api<{
      project: Project;
      analysis: { warnings: string[]; limitations?: string[] };
    }>(`/projects/${current.id}/analyze`, "POST", {
      document_id: docId,
      page,
      revision: current.state.revision,
      mode
    });
    accept(result.project);
    setNotice(
      `${result.project.state.annotations.filter((a) => a.source_document_id === docId && a.source_page === page).length} propositions sur cette page ; aucune validation automatique. ${[...result.analysis.warnings, ...(result.analysis.limitations || [])].join(" ")}`
    );
  }
  async function importLibrary() {
    const file = inventoryInput.current?.files?.[0];
    if (!file) throw new Error("Sélectionner l’inventaire JSON");
    const form = new FormData();
    form.append("inventory", file);
    const archive = archiveInput.current?.files?.[0];
    if (archive) form.append("archive", archive);
    const lib = await api<Library>("/libraries", "POST", form);
    setLibraries(await api("/libraries"));
    if (p)
      edit((s) => ({
        ...s,
        library_id: lib.id,
        mappings: [],
        annotations: s.annotations.map((a) => ({
          ...a,
          asset_id: null,
          review: { ...a.review, asset: false },
          status: a.status === "confirmed" ? "review" : a.status
        }))
      }));
    setNotice(
      lib.archive_verified
        ? "Archive vérifiée. Approuver visuellement les pictogrammes avant utilisation."
        : "Inventaire provisoire importé. Les ressources AI restent nécessaires."
    );
  }
  async function approveAsset(a: Asset) {
    if (!library) return;
    await api(`/libraries/${library.id}/assets/${a.id}`, "PUT", {
      approved: !a.approved,
      pictogram_candidate: a.pictogram_candidate
    });
    setLibraries(await api("/libraries"));
  }
  function addMapping() {
    if (!annotation?.asset_id || !annotation.equipment_type) return;
    edit((s) => ({
      ...s,
      mappings: [
        ...s.mappings.filter(
          (m) =>
            !(m.annotation === annotation.text && m.equipment_type === annotation.equipment_type)
        ),
        {
          annotation: annotation.text || annotation.equipment_type,
          equipment_type: annotation.equipment_type,
          asset_id: annotation.asset_id!,
          confirmed: true
        }
      ]
    }));
    setNotice("Correspondance confirmée pour ce dossier. Aucun autre relevé n’est modifié.");
  }
  function addLegendRow() {
    edit((s) => {
      const list = s.legends.filter(
        (l) => !(l.source_document_id === docId && l.source_page === page)
      );
      return {
        ...s,
        legends: [
          ...list,
          {
            source_document_id: docId,
            source_page: page,
            bbox: legend?.bbox || null,
            entries: [
              ...(legend?.entries || []),
              { color: "red", label: "", equipment_type: "", confirmed: false }
            ]
          }
        ]
      };
    });
  }
  function updateLegend(i: number, changes: Record<string, unknown>) {
    edit((s) => ({
      ...s,
      legends: s.legends.map((l) =>
        l.source_document_id === docId && l.source_page === page
          ? { ...l, entries: l.entries.map((e, j) => (i === j ? { ...e, ...changes } : e)) }
          : l
      )
    }));
  }
  function applyLegend() {
    if (!legend) return;
    edit((s) => ({
      ...s,
      annotations: s.annotations.map((a) => {
        const entry = legend.entries.find((e) => e.confirmed && e.color === a.color);
        return a.source_document_id === docId &&
          a.source_page === page &&
          a.status !== "rejected" &&
          entry
          ? clearReview(a, { equipment_type: entry.equipment_type })
          : a;
      })
    }));
    setNotice("Types proposés à partir de la légende de cette page. Ils restent à vérifier.");
  }
  function exportDictionary() {
    if (!state) return;
    const scope = prompt("Client ou méthode de relevé pour ce dictionnaire");
    if (!scope) return;
    download("DOEMO-dictionnaire.json", {
      schema_version: "doemo.dictionary/1",
      scope,
      library_id: state.library_id,
      mapping_version: state.mapping_version,
      mappings: state.mappings,
      legend_entries: legend?.entries || []
    });
  }
  async function importDictionary(file: File) {
    if (!state) return;
    const data = JSON.parse(await file.text());
    if (
      data.schema_version !== "doemo.dictionary/1" ||
      data.library_id !== state.library_id ||
      !Array.isArray(data.mappings) ||
      !Array.isArray(data.legend_entries)
    )
      throw new Error("Dictionnaire incompatible : choisir la même bibliothèque SAI.");
    edit((s) => ({
      ...s,
      mappings: data.mappings.map((m: unknown) => ({ ...(m as object), confirmed: false })),
      legends: [
        ...s.legends.filter((l) => !(l.source_document_id === docId && l.source_page === page)),
        {
          source_document_id: docId,
          source_page: page,
          bbox: legend?.bbox || null,
          entries: data.legend_entries.map((e: unknown) => ({ ...(e as object), confirmed: false }))
        }
      ]
    }));
    setNotice("Dictionnaire repris. Confirmer les associations pour ce relevé avant utilisation.");
  }
  function proposeMappings() {
    const normalize = (s: string) => s.normalize("NFKC").trim().replace(/\s+/g, " ").toUpperCase();
    edit((s) => ({
      ...s,
      annotations: s.annotations.map((a) => {
        if (
          a.source_document_id !== docId ||
          a.source_page !== page ||
          a.status === "confirmed" ||
          a.status === "rejected"
        )
          return a;
        const matches = s.mappings.filter(
          (m) => m.confirmed && normalize(m.annotation) === normalize(a.text)
        );
        return matches.length === 1
          ? clearReview(a, {
              equipment_type: matches[0].equipment_type,
              asset_id: matches[0].asset_id
            })
          : a;
      })
    }));
    setNotice(
      "Correspondances exactes proposées sur cette page ; les types, capacités et pictogrammes restent à vérifier."
    );
  }
  async function exportReview() {
    const saved = await save();
    if (saved) download("DOEMO-revue.json", await api(`/projects/${saved.id}/review-export`));
  }
  async function exportFinal(bundle = false) {
    const saved = await save();
    if (!saved) return;
    const data = await api(`/projects/${saved.id}/placements`);
    if (bundle) window.location.href = url(`/projects/${saved.id}/bundle`);
    else download("DOEMO-placements.json", data);
  }
  async function restore(file: File) {
    if (!p) return;
    const data = JSON.parse(await file.text());
    if (data.id !== p.id)
      throw new Error(
        "Ce dossier de revue appartient à un autre projet. Ouvrir le projet d’origine."
      );
    if (
      data.documents?.some(
        (d: Doc) => !p.documents.some((e) => e.id === d.id && e.sha256 === d.sha256)
      )
    )
      throw new Error("Documents de revue différents du projet.");
    const result = await api<Project>(`/projects/${p.id}/state`, "PUT", {
      ...data.state,
      revision: p.state.revision
    });
    accept(result);
    setNotice("Dossier de revue repris, documents et identifiants conservés.");
  }

  return (
    <div className="app">
      <header>
        <a className="brand" href="/">
          DOEMO <span>STUDIO</span>
        </a>
        <div className="module-title">
          <strong>Relevés & pictogrammes</strong>
          <small>Reconnaître · vérifier · placer dans Illustrator</small>
        </div>
        <button onClick={() => setShowLibrary(true)}>Bibliothèque SAI</button>
        <button
          disabled={!dirty || !!busy}
          className="primary"
          onClick={() =>
            void run("Enregistrement…", async () => {
              await save();
              setNotice("Modifications enregistrées.");
            })
          }
        >
          {dirty ? "Enregistrer les corrections" : "Enregistré"}
        </button>
      </header>
      <nav>
        <select
          aria-label="Dossier"
          value={p?.id || ""}
          onChange={(e) => void run("Ouverture…", () => open(e.target.value))}
        >
          <option value="">Choisir un dossier</option>
          {projects.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <button disabled={!!busy} onClick={() => void run("Création…", create)}>
          ＋ Nouveau dossier
        </button>
        {p && (
          <>
            <label className="button">
              Importer un relevé
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                disabled={!!busy}
                onChange={(e) => {
                  if (e.target.files?.[0])
                    void run("Import du relevé…", () => upload(e.target.files![0], "survey"));
                  e.target.value = "";
                }}
              />
            </label>
            <label className="button">
              Importer le BAT .ai
              <input
                type="file"
                accept=".ai"
                disabled={!!busy}
                onChange={(e) => {
                  if (e.target.files?.[0])
                    void run("Import du BAT…", () => upload(e.target.files![0], "target"));
                  e.target.value = "";
                }}
              />
            </label>
            <button onClick={() => void run("Export du dossier…", exportReview)}>
              Exporter la revue
            </button>
            <label className="button">
              Reprendre une revue
              <input
                type="file"
                accept=".json"
                onChange={(e) => {
                  if (e.target.files?.[0]) void run("Reprise…", () => restore(e.target.files![0]));
                  e.target.value = "";
                }}
              />
            </label>
            <button
              className="primary"
              onClick={() => void run("Contrôle des placements…", () => exportFinal(true))}
            >
              Préparer Illustrator
            </button>
          </>
        )}
      </nav>
      {(error || notice || busy) && (
        <div role={error ? "alert" : "status"} className={"message " + (error ? "error" : "")}>
          {busy || error || notice}
          <button
            onClick={() => {
              setError("");
              setNotice("");
            }}
            aria-label="Fermer le message"
          >
            ×
          </button>
        </div>
      )}
      {!p ? (
        <main className="welcome">
          <span className="eyebrow">RELEVÉS TERRAIN</span>
          <h1>Du relevé aux pictogrammes vérifiés.</h1>
          <p>
            Importez un relevé et son BAT Illustrator, examinez les propositions puis confirmez
            chaque placement. Les fichiers d’origine sont conservés.
          </p>
          <button className="primary" onClick={() => void run("Création…", create)}>
            Créer un dossier
          </button>
          <p className="subtle">
            L’export natif s’effectue ensuite sur votre poste Illustrator 2024 ou ultérieur.
          </p>
        </main>
      ) : (
        <>
          <div className="workspace">
            <section className="pane">
              <div className="pane-heading">
                <span className="step">01</span>
                <div>
                  <h2>Relevé original</h2>
                  <small>Les cadres sont des propositions à vérifier.</small>
                </div>
              </div>
              <div className="controls">
                <select
                  aria-label="Relevé"
                  value={docId}
                  onChange={(e) => {
                    setDoc(e.target.value);
                    setPage(1);
                    setSelected("");
                  }}
                >
                  <option value="">Choisir un relevé</option>
                  {p.documents
                    .filter((d) => d.role === "survey")
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                </select>
                <select
                  aria-label="Page du relevé"
                  value={page}
                  onChange={(e) => {
                    setPage(+e.target.value);
                    setSelected("");
                  }}
                >
                  {source?.pages.map((q) => (
                    <option key={q.number} value={q.number}>
                      Page {q.number}
                    </option>
                  ))}
                </select>
              </div>
              <div className="controls">
                <select
                  aria-label="Méthode d’analyse"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="local">Couleurs, formes et OCR local</option>
                  <option value="multimodal">Analyse IA multimodale</option>
                </select>
                <button
                  disabled={!source || !!busy}
                  onClick={() => void run("Analyse du relevé…", analyze)}
                >
                  Analyser cette page
                </button>
                <button disabled={!source} onClick={() => setShowLegend(!showLegend)}>
                  Légende
                </button>
              </div>
              {mode === "multimodal" && (
                <p className="hint">
                  L’image de cette page sera transmise au fournisseur IA configuré. Les résultats
                  restent à vérifier.
                </p>
              )}
              <div className="controls">
                <button
                  className={adding ? "active" : ""}
                  onClick={() => {
                    setAdding(!adding);
                    setPick(null);
                  }}
                >
                  ＋ Équipement oublié
                </button>
                <button onClick={() => setRotation((rotation + 180) % 360)}>Lecture ↻ 180°</button>
                <label>
                  Zoom{" "}
                  <input
                    type="range"
                    min="100"
                    max="350"
                    value={zoom}
                    onChange={(e) => setZoom(+e.target.value)}
                  />
                </label>
              </div>
              {source ? (
                <Viewer
                  image={imageUrl(source, page)}
                  ratio={source.pages[page - 1].height / source.pages[page - 1].width}
                  zoom={zoom}
                  rotation={rotation}
                  onPoint={clickSource}
                >
                  {annotations.map((a, i) => (
                    <g
                      key={a.id}
                      className={a.status === "rejected" ? "rejected" : ""}
                      onClick={(e) => {
                        if (a.id !== selected || pick || adding) {
                          e.stopPropagation();
                          chooseAnnotation(a);
                        }
                      }}
                    >
                      <rect
                        className={a.id === selected ? "box selected" : "box"}
                        x={a.bbox.x}
                        y={a.bbox.y}
                        width={a.bbox.w}
                        height={a.bbox.h}
                      />
                      <text x={a.bbox.x} y={Math.max(0.012, a.bbox.y - 0.003)}>
                        {i + 1}
                      </text>
                      {a.anchor && (
                        <circle cx={a.anchor.x} cy={a.anchor.y} r=".003" className="anchor" />
                      )}
                    </g>
                  ))}
                  {legend?.bbox && (
                    <rect
                      {...{
                        x: legend.bbox.x,
                        y: legend.bbox.y,
                        width: legend.bbox.w,
                        height: legend.bbox.h
                      }}
                      className="legend-box"
                    />
                  )}
                  {pairs.map((q, i) => (
                    <circle
                      key={"p" + i}
                      cx={q.source.x}
                      cy={q.source.y}
                      r=".004"
                      className="control-point"
                    />
                  ))}
                  {checks.map((q, i) => (
                    <circle
                      key={"c" + i}
                      cx={q.source.x}
                      cy={q.source.y}
                      r=".004"
                      className="check-point"
                    />
                  ))}
                </Viewer>
              ) : (
                <Empty text="Importez un relevé PDF, une photographie ou une image." />
              )}
              <p className="hint">
                {selectLegend
                  ? legendPick
                    ? "Cliquez sur le second coin de la légende."
                    : "Cliquez sur le premier coin de la légende."
                  : pick
                    ? "Choisissez un point sur le relevé, puis son équivalent sur le BAT."
                    : adding
                      ? "Cliquez à l’emplacement de l’équipement oublié."
                      : "Sélectionnez une marque. Cliquez dans l’image pour corriger son ancrage, notamment la pointe d’une flèche."}
              </p>
              {showLegend && (
                <div className="panel">
                  <h3>Légende de cette page</h3>
                  <button
                    onClick={() => {
                      setSelectLegend(true);
                      setLegendPick(null);
                      setPick(null);
                    }}
                  >
                    Délimiter la légende
                  </button>
                  <button
                    disabled={!legend?.bbox}
                    onClick={() =>
                      void run("Lecture de la légende…", async () => {
                        const result = await api<{ words: { text: string }[]; message: string }>(
                          `/projects/${p.id}/legend-read`,
                          "POST",
                          { document_id: docId, page, bbox: legend?.bbox }
                        );
                        setNotice(
                          result.words.map((x) => x.text).join(" ") + " — " + result.message
                        );
                      })
                    }
                  >
                    Lire la zone
                  </button>
                  {legend?.entries.map((entry, i) => (
                    <div className="legend-row" key={i}>
                      <select
                        aria-label="Couleur"
                        value={entry.color}
                        onChange={(e) =>
                          updateLegend(i, { color: e.target.value, confirmed: false })
                        }
                      >
                        {[
                          "red",
                          "yellow",
                          "blue",
                          "orange",
                          "green",
                          "violet",
                          "pink",
                          "unknown"
                        ].map((c) => (
                          <option key={c} value={c}>
                            {colors[c] || c}
                          </option>
                        ))}
                      </select>
                      <input
                        aria-label="Inscription dans la légende"
                        placeholder="Inscription lue"
                        value={entry.label}
                        onChange={(e) =>
                          updateLegend(i, { label: e.target.value, confirmed: false })
                        }
                      />
                      <input
                        aria-label="Équipement de la légende"
                        placeholder="Équipement exact"
                        value={entry.equipment_type}
                        onChange={(e) =>
                          updateLegend(i, { equipment_type: e.target.value, confirmed: false })
                        }
                      />
                      <label>
                        <input
                          type="checkbox"
                          checked={entry.confirmed}
                          onChange={(e) => updateLegend(i, { confirmed: e.target.checked })}
                        />
                        Confirmé
                      </label>
                    </div>
                  ))}
                  <button onClick={addLegendRow}>＋ Association</button>
                  <button onClick={applyLegend}>Proposer les types sur cette page</button>
                  <small>
                    Aucune association de couleur n’est appliquée aux autres pages ou dossiers.
                  </small>
                </div>
              )}
            </section>
            <section className="pane">
              <div className="pane-heading">
                <span className="step">02</span>
                <div>
                  <h2>BAT de référence</h2>
                  <small>Repères proposés, sans modifier l’architecture.</small>
                </div>
              </div>
              <div className="controls">
                <select
                  aria-label="Niveau"
                  value={floorId}
                  onChange={(e) => setFloor(e.target.value)}
                >
                  <option value="">Choisir un niveau</option>
                  {state?.floors.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
                <button disabled={!target} onClick={addFloor}>
                  ＋ Niveau
                </button>
                <button
                  disabled={!source || !floor}
                  onClick={() => setShowRegistration(!showRegistration)}
                >
                  Recalage
                </button>
              </div>
              {floor && (
                <div className="controls">
                  <label>
                    Page du BAT{" "}
                    <select
                      value={floor.target_page}
                      onChange={(e) =>
                        editFloor({ target_page: +e.target.value, confirmed: false })
                      }
                    >
                      {target?.pages.map((q) => (
                        <option key={q.number} value={q.number}>
                          {q.number}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Plan de travail Illustrator{" "}
                    <input
                      type="number"
                      min="1"
                      value={floor.artboard_index + 1}
                      onChange={(e) =>
                        editFloor({
                          artboard_index: Math.max(0, +e.target.value - 1),
                          confirmed: false
                        })
                      }
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={floor.confirmed}
                      onChange={(e) => editFloor({ confirmed: e.target.checked })}
                    />
                    Association niveau / plan de travail vérifiée
                  </label>
                </div>
              )}
              {target ? (
                <Viewer
                  image={imageUrl(target, floor?.target_page || 1)}
                  ratio={
                    target.pages[(floor?.target_page || 1) - 1].height /
                    target.pages[(floor?.target_page || 1) - 1].width
                  }
                  zoom={zoom}
                  onPoint={clickTarget}
                >
                  {showOverlay && reg && !dirty && (
                    <image
                      href={url(
                        `/projects/${p.id}/overlay?document_id=${docId}&page=${page}&floor_id=${floorId}&v=${state?.revision}`
                      )}
                      width="1"
                      height="1"
                      preserveAspectRatio="none"
                      opacity={opacity}
                    />
                  )}
                  {state?.annotations
                    .filter((a) => a.floor_id === floorId && a.status !== "rejected")
                    .map((a) => {
                      const q = mapped(a);
                      const item = library?.assets.find((s) => s.id === a.asset_id);
                      if (!q) return null;
                      return (
                        <g
                          key={a.id}
                          onClick={(e) => {
                            if (a.id !== selected || pick || adding) {
                              e.stopPropagation();
                              chooseAnnotation(a);
                            }
                          }}
                        >
                          <circle
                            cx={q.x}
                            cy={q.y}
                            r={a.id === selected ? 0.014 : 0.009}
                            className={a.status === "confirmed" ? "target confirmed" : "target"}
                          />
                          {item?.preview && (
                            <image
                              href={url(`/libraries/${library?.id}/assets/${item.id}/preview`)}
                              x={q.x - 0.008}
                              y={q.y - 0.008}
                              width=".016"
                              height=".016"
                              transform={`rotate(${a.rotation_deg} ${q.x} ${q.y})`}
                            />
                          )}
                          <text x={q.x + 0.01} y={q.y}>
                            {state.annotations.indexOf(a) + 1}
                          </text>
                        </g>
                      );
                    })}
                  {pairs.map((q, i) => (
                    <circle
                      key={"p" + i}
                      cx={q.target.x}
                      cy={q.target.y}
                      r=".004"
                      className="control-point"
                    />
                  ))}
                  {checks.map((q, i) => (
                    <circle
                      key={"c" + i}
                      cx={q.target.x}
                      cy={q.target.y}
                      r=".004"
                      className="check-point"
                    />
                  ))}
                </Viewer>
              ) : (
                <Empty
                  text={
                    target
                      ? "Ajoutez un niveau et associez-le au plan de travail Illustrator."
                      : "Importez le BAT .ai en conservant sa compatibilité PDF."
                  }
                />
              )}
              <div className="controls">
                <label>
                  <input
                    type="checkbox"
                    checked={showOverlay}
                    onChange={(e) => setShowOverlay(e.target.checked)}
                  />
                  Superposer le relevé recalé
                </label>
                <label>
                  Transparence{" "}
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step=".05"
                    value={opacity}
                    onChange={(e) => setOpacity(+e.target.value)}
                  />
                </label>
              </div>
              <p className="hint">
                Cliquez sur le BAT pour déplacer le repère sélectionné. Les cercles numérotés
                indiquent les positions à contrôler ; les ressources SAI disponibles s’affichent à
                l’intérieur.
              </p>
              {showRegistration && (
                <div className="panel">
                  <h3>Aligner les documents</h3>
                  <select
                    aria-label="Modèle de recalage"
                    value={model}
                    onChange={(e) => setModel(e.target.value as "affine" | "homography")}
                  >
                    <option value="affine">Échelle, rotation et translation</option>
                    <option value="homography">Perspective photographique</option>
                  </select>
                  <div className="controls">
                    <button onClick={() => setPick(pick === "fit" ? null : "fit")}>
                      Choisir les points communs ({pairs.length})
                    </button>
                    <button onClick={() => setPick(pick === "check" ? null : "check")}>
                      Point de contrôle indépendant ({checks.length})
                    </button>
                    <button
                      onClick={() => {
                        setPairs([]);
                        setChecks([]);
                        setPending(null);
                      }}
                    >
                      Recommencer
                    </button>
                  </div>
                  <ol>
                    {pairs.map((q, i) => (
                      <li key={i}>
                        Relevé {pointText(q.source)} → BAT {pointText(q.target)}{" "}
                        <button onClick={() => setPairs(pairs.filter((_, j) => j !== i))}>
                          Retirer
                        </button>
                      </li>
                    ))}
                  </ol>
                  <div className="controls">
                    <button
                      disabled={!!busy}
                      onClick={() =>
                        void run("Recherche des correspondances…", async () => {
                          const saved = await save();
                          if (!saved) return;
                          const result = await api<{
                            source_points: number[][];
                            target_points: number[][];
                          }>(
                            `/projects/${p.id}/automatic-registration?floor_id=${floorId}`,
                            "POST",
                            {
                              document_id: docId,
                              page,
                              revision: saved.state.revision,
                              mode: "local"
                            }
                          );
                          setPairs(
                            result.source_points.map((q, i) => ({
                              source: { x: q[0], y: q[1] },
                              target: {
                                x: result.target_points[i][0],
                                y: result.target_points[i][1]
                              }
                            }))
                          );
                          setModel("homography");
                          setNotice(
                            "Correspondances proposées. Choisir un point de contrôle indépendant et vérifier l’architecture."
                          );
                        })
                      }
                    >
                      Proposer un alignement
                    </button>
                    <button
                      className="primary"
                      disabled={pairs.length < (model === "affine" ? 3 : 4) || !checks.length}
                      onClick={() => void run("Calcul du recalage…", calculate)}
                    >
                      Calculer le recalage
                    </button>
                  </div>
                  {reg && (
                    <>
                      <p>
                        Écart des points : <strong>{reg.fit_error_px.toFixed(2)} px</strong> ·
                        Contrôle indépendant : <strong>{reg.check_error_px.toFixed(2)} px</strong> ·
                        Seuil : {reg.max_error_px} px
                      </p>
                      <label>
                        <input
                          type="checkbox"
                          checked={reg.architecture_confirmed}
                          onChange={(e) =>
                            editReg({ architecture_confirmed: e.target.checked, confirmed: false })
                          }
                        />
                        Même bâtiment, même niveau et même état architectural vérifiés
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          disabled={
                            !reg.architecture_confirmed ||
                            Math.max(reg.fit_error_px, reg.check_error_px) > reg.max_error_px
                          }
                          checked={reg.confirmed}
                          onChange={(e) => editReg({ confirmed: e.target.checked })}
                        />
                        Recalage contrôlé et accepté
                      </label>
                    </>
                  )}
                </div>
              )}
            </section>
            <aside className="pane equipment">
              <div className="pane-heading">
                <span className="step">03</span>
                <div>
                  <h2>Équipements</h2>
                  <small>
                    {state?.annotations.length} propositions ·{" "}
                    {state?.annotations.filter((a) => a.status === "confirmed").length} confirmées
                  </small>
                </div>
              </div>
              <div className="controls">
                <label>
                  Afficher
                  <select
                    aria-label="Filtre de couleur"
                    value={colorFilter}
                    onChange={(e) => setColorFilter(e.target.value)}
                  >
                    <option value="all">Toutes les couleurs</option>
                    {[...new Set(annotations.map((a) => a.color))].map((c) => (
                      <option key={c} value={c}>
                        {colors[c] || c}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="controls">
                <button onClick={exportDictionary}>Exporter le dictionnaire</button>
                <label className="button">
                  Reprendre un dictionnaire
                  <input
                    type="file"
                    accept=".json"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void run("Reprise du dictionnaire…", () => importDictionary(file));
                      e.target.value = "";
                    }}
                  />
                </label>
                <button onClick={proposeMappings}>Proposer les correspondances</button>
              </div>
              <div className="equipment-list">
                {annotations
                  .filter((a) => colorFilter === "all" || a.color === colorFilter)
                  .map((a, i) => (
                    <button
                      className={"equipment-row " + (selected === a.id ? "chosen" : "")}
                      key={a.id}
                      onClick={() => chooseAnnotation(a)}
                    >
                      <span className="number">{annotations.indexOf(a) + 1}</span>
                      <span>
                        <strong>{a.equipment_type || a.text || "Marque à identifier"}</strong>
                        <small>
                          {colors[a.color] || a.color} · {shapes[a.shape] || a.shape} · confiance
                          indicative {Math.round(a.confidence * 100)} %
                        </small>
                      </span>
                      <span className={"badge " + a.status}>{statuses[a.status]}</span>
                    </button>
                  ))}
                {!annotations.length && (
                  <p className="hint">
                    Lancez l’analyse de la page ou ajoutez manuellement un équipement.
                  </p>
                )}
              </div>
              {annotation && (
                <div className="editor">
                  <h3>
                    Vérifier la proposition {annotations.findIndex((a) => a.id === selected) + 1}
                  </h3>
                  <img
                    className="evidence-crop"
                    src={url(
                      `/projects/${p.id}/annotations/${annotation.id}/crop?v=${state?.revision}`
                    )}
                    alt="Extrait original de l’annotation à vérifier"
                  />
                  <p className="hint">{annotation.evidence}</p>
                  <label>
                    Inscription source
                    <input
                      value={annotation.text}
                      onChange={(e) => change({ text: e.target.value })}
                    />
                  </label>
                  <label>
                    Équipement exact
                    <input
                      value={annotation.equipment_type}
                      placeholder="Type et capacité, si lisibles"
                      onChange={(e) => change({ equipment_type: e.target.value })}
                    />
                  </label>
                  <label>
                    Bibliothèque
                    <select
                      value={state?.library_id || ""}
                      onChange={(e) => {
                        if (
                          state?.mappings.length &&
                          !confirm(
                            "Changer de bibliothèque effacera les correspondances de ce dossier. Continuer ?"
                          )
                        )
                          return;
                        edit((s) => ({
                          ...s,
                          library_id: e.target.value || null,
                          mappings: [],
                          annotations: s.annotations.map((a) => ({
                            ...a,
                            asset_id: null,
                            review: { ...a.review, asset: false },
                            status: a.status === "confirmed" ? "review" : a.status
                          }))
                        }));
                      }}
                    >
                      <option value="">Choisir la bibliothèque</option>
                      {libraries.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                          {l.archive_verified ? "" : " · inventaire provisoire"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Rechercher un pictogramme
                    <input value={search} onChange={(e) => setSearch(e.target.value)} />
                  </label>
                  <label>
                    Pictogramme SAI
                    <select
                      value={annotation.asset_id || ""}
                      onChange={(e) => change({ asset_id: e.target.value || null })}
                    >
                      <option value="">Aucun pictogramme choisi</option>
                      {library?.assets
                        .filter(
                          (a) =>
                            a.pictogram_candidate &&
                            (a.id === annotation.asset_id ||
                              a.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
                        )
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name} · {a.id.slice(0, 8)}
                            {a.approved ? " ✓" : ""}
                          </option>
                        ))}
                    </select>
                  </label>
                  {asset && (
                    <div className="asset-preview">
                      {asset.preview ? (
                        <img
                          src={url(`/libraries/${library?.id}/assets/${asset.id}/preview`)}
                          alt={asset.name}
                        />
                      ) : (
                        <span>Aperçu vectoriel indisponible</span>
                      )}
                      <small>
                        {asset.verified ? "Ressource vérifiée" : "Ressource AI à importer"} ·{" "}
                        {asset.approved ? "approuvée" : "à approuver"}
                      </small>
                    </div>
                  )}
                  <button
                    disabled={!annotation.asset_id || !annotation.equipment_type}
                    onClick={addMapping}
                  >
                    Confirmer cette correspondance métier
                  </button>
                  <label>
                    Niveau
                    <select
                      value={annotation.floor_id || ""}
                      onChange={(e) => change({ floor_id: e.target.value || null })}
                    >
                      <option value="">À définir</option>
                      {state?.floors.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="two-fields">
                    <label>
                      Rotation horaire (°)
                      <input
                        type="number"
                        min="-360"
                        max="360"
                        value={annotation.rotation_deg}
                        onChange={(e) => change({ rotation_deg: +e.target.value })}
                      />
                    </label>
                    <label>
                      Taille (mm)
                      <input
                        type="number"
                        min=".1"
                        max="200"
                        step=".1"
                        value={annotation.size_mm}
                        onChange={(e) => change({ size_mm: +e.target.value })}
                      />
                    </label>
                  </div>
                  <p className="hint">
                    Ancrage source :{" "}
                    {annotation.anchor ? pointText(annotation.anchor) : "à pointer sur le relevé"}
                    <br />
                    Position BAT :{" "}
                    {mapped(annotation) ? pointText(mapped(annotation)!) : "recalage requis"}
                  </p>
                  <fieldset>
                    <legend>Vérification séparée</legend>
                    {criteria.map((c) => (
                      <label key={c.key}>
                        <input
                          type="checkbox"
                          checked={annotation.review[c.key]}
                          onChange={(e) =>
                            change({ review: { ...annotation.review, [c.key]: e.target.checked } })
                          }
                        />
                        {c.label}
                      </label>
                    ))}
                  </fieldset>
                  <div className="controls">
                    <button
                      className="primary"
                      disabled={!allConfirmed}
                      onClick={() => change({ status: "confirmed" })}
                    >
                      Confirmer le placement
                    </button>
                    <button onClick={() => change({ status: "rejected" })}>Rejeter</button>
                    <button onClick={() => change({ status: "review" })}>À revoir</button>
                  </div>
                </div>
              )}
              <div className="panel">
                <label className="button">
                  Importer le rapport Illustrator
                  <input
                    type="file"
                    accept=".json"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file)
                        void run("Lecture du rapport Illustrator…", async () => {
                          const form = new FormData();
                          form.append("file", file);
                          await api(`/projects/${p.id}/illustrator-reports`, "POST", form);
                          setReports(await api(`/projects/${p.id}/illustrator-reports`));
                        });
                      e.target.value = "";
                    }}
                  />
                </label>
                {reports.map((r, i) => (
                  <div key={i}>
                    <h3>Contrôle Illustrator · {r.report.placed_total} objets</h3>
                    <p>
                      {r.source} ·{" "}
                      {r.report.native_ai_verified
                        ? "AI réouvert sur le poste"
                        : "Réouverture non confirmée"}{" "}
                      ·{" "}
                      {r.report.conformity_passed
                        ? "Placements conformes aux données validées"
                        : "Écarts à examiner"}
                    </p>
                    {r.report.measurements.map((m) => (
                      <p key={m.placement_id}>
                        {m.placement_id.slice(0, 8)} · écart {m.position_error_pt.toFixed(3)} pt ·{" "}
                        {m.validated_placement_matches ? "conforme" : "à examiner"}
                      </p>
                    ))}
                  </div>
                ))}
                <button onClick={() => void run("Contrôle de l’export…", () => exportFinal())}>
                  Exporter les placements JSON
                </button>
                <p className="hint">
                  Les propositions incertaines doivent être corrigées ou rejetées avant l’export
                  Illustrator. Le dossier de revue conserve les éléments non validés.
                </p>
              </div>
            </aside>
          </div>
          <footer>
            {p.name} · Révision {state?.revision} ·{" "}
            {dirty ? "Corrections non enregistrées" : "Corrections enregistrées"}
            <span>Originaux conservés · Aucun plan architectural reconstruit</span>
          </footer>
        </>
      )}
      {showLibrary && (
        <div className="modal-backdrop">
          <section className="modal" role="dialog" aria-modal="true" aria-label="Bibliothèque SAI">
            <div className="modal-heading">
              <h2>Bibliothèque de pictogrammes SAI</h2>
              <button onClick={() => setShowLibrary(false)}>Fermer</button>
            </div>
            <p>
              Un inventaire seul permet la recherche. Le manifeste et les fichiers AI de l’archive
              sont indispensables pour autoriser un placement.
            </p>
            <div className="controls">
              <label>
                Inventaire JSON
                <input type="file" accept=".json" ref={inventoryInput} />
              </label>
              <label>
                Archive SAI
                <input type="file" accept=".cclibs,.zip" ref={archiveInput} />
              </label>
              <button
                disabled={!!busy}
                onClick={() =>
                  void run("Import et vérification de la bibliothèque…", importLibrary)
                }
              >
                Importer la bibliothèque
              </button>
            </div>
            <input
              aria-label="Recherche bibliothèque"
              placeholder="Rechercher par nom ou catégorie"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {libraries.map((l) => (
              <div key={l.id}>
                <h3>
                  {l.name} · {l.assets.length} ressources ·{" "}
                  {l.archive_verified ? "archive vérifiée" : "inventaire provisoire"}
                </h3>
                <div className="catalog">
                  {l.assets
                    .filter((a) =>
                      (a.name + " " + a.groups.join(" "))
                        .toLowerCase()
                        .includes(search.toLowerCase())
                    )
                    .map((a) => (
                      <div key={a.id} className="catalog-item">
                        {a.preview && (
                          <img
                            alt={a.name}
                            src={url(`/libraries/${l.id}/assets/${a.id}/preview`)}
                          />
                        )}
                        <strong>{a.name}</strong>
                        <small>
                          {a.groups.join(" · ")}
                          <br />
                          {a.id}
                        </small>
                        <span>
                          {a.pictogram_candidate
                            ? "Candidat pictogramme"
                            : "Autre ressource graphique"}
                        </span>
                        <button
                          disabled={!a.verified || !a.pictogram_candidate}
                          onClick={() =>
                            void run("Validation de la ressource…", async () => {
                              await api(`/libraries/${l.id}/assets/${a.id}`, "PUT", {
                                approved: !a.approved,
                                pictogram_candidate: a.pictogram_candidate
                              });
                              setLibraries(await api("/libraries"));
                            })
                          }
                        >
                          {a.approved ? "Retirer l’approbation" : "Approuver le pictogramme"}
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </section>
        </div>
      )}
      {busy && <div className="busy-bar" aria-label={busy} />}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="empty">
      <span>＋</span>
      <p>{text}</p>
    </div>
  );
}
function Viewer({
  image,
  ratio,
  children,
  zoom,
  onPoint,
  rotation = 0
}: {
  image: string;
  ratio: number;
  children: React.ReactNode;
  zoom: number;
  onPoint: (p: Point) => void;
  rotation?: number;
}) {
  const group = useRef<SVGGElement>(null);
  return (
    <div className="viewport">
      <svg
        viewBox="0 0 1 1"
        preserveAspectRatio="none"
        style={{ width: `${zoom}%`, aspectRatio: String(1 / ratio) }}
        onClick={(e) => {
          const matrix = group.current?.getScreenCTM();
          if (!matrix) return;
          const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
          if (point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1)
            onPoint({ x: point.x, y: point.y });
        }}
      >
        <g ref={group} transform={`rotate(${rotation} .5 .5)`}>
          <image href={image} x="0" y="0" width="1" height="1" preserveAspectRatio="none" />
          {children}
        </g>
      </svg>
    </div>
  );
}
