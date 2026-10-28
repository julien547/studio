import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, url, download, standalone } from "./api";
import { useEditor } from "./useEditor";
import { PlanCanvas, Tool } from "./PlanCanvas";
import { clearReview } from "./geometry";
import { wholePage, moveBox } from "./editorGeometry";
import type { Annotation, Box, Library, Project, Review, State } from "./types";
import { AdvancedApp } from "./main";
import "./studio.css";

type User = { login: string; role: string };
type Entry = {
  code: string;
  name: string;
  synonyms: string[];
  asset_id: string | null;
  active: boolean;
  description: string;
};
type Summary = {
  id: string;
  name: string;
  owner: string;
  revision: number;
  workflow: string;
  annotation_count: number;
  metadata: Record<string, string>;
};
type Job = {
  id: string;
  status: string;
  stage: string;
  error: string | null;
  created: string;
  result?: {
    annotations: Annotation[];
    warnings: string[];
    observations: Record<string, unknown>[];
  };
};
const emptyReview: Review = {
  equipment: false,
  asset: false,
  floor: false,
  position: false,
  orientation: false,
  size: false,
};
const reviewLabels: Record<keyof Review, string> = {
  equipment: "Catégorie et texte vérifiés",
  asset: "Pictogramme SAI vérifié",
  floor: "Niveau vérifié",
  position: "Position réelle vérifiée",
  orientation: "Orientation vérifiée",
  size: "Taille vérifiée",
};
const statusLabels: Record<string, string> = {
  review: "À vérifier",
  confirmed: "Validé",
  rejected: "Rejeté",
  missing_asset: "Pictogramme à associer",
  uncertain_position: "Position à pointer",
};
const workflows: Record<string, string> = {
  draft: "Brouillon",
  review: "À vérifier",
  corrected: "Corrigé",
  validated: "Validé",
};
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="login-screen">
      <form
        className="login-card"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          const f = new FormData(e.currentTarget);
          try {
            const r = await fetch("/session", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(Object.fromEntries(f)),
            });
            const data = await r.json();
            if (!r.ok) throw Error(data.detail);
            onLogin(data);
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="studio-wordmark">
          DOEMO <span>STUDIO</span>
        </div>
        <h1>Votre atelier de plans.</h1>
        <p>Connectez-vous pour retrouver vos relevés et vos corrections.</p>
        <label>
          Identifiant
          <input name="login" autoComplete="username" required autoFocus />
        </label>
        <label>
          Mot de passe
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button className="primary" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </main>
  );
}
function Root() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [advanced, setAdvanced] = useState(false);
  useEffect(() => {
    void fetch(standalone ? "/session" : "/api/me.php")
      .then((r) => (r.ok ? r.json() : null))
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);
  if (loading) return <p className="loading">Ouverture de DOEMO Studio…</p>;
  if (!user)
    return standalone ? (
      <Login onLogin={setUser} />
    ) : (
      <p className="loading">
        <a href="/">Se connecter à DOEMO Studio</a>
      </p>
    );
  if (advanced)
    return (
      <>
        <div className="return-editor">
          <button onClick={() => setAdvanced(false)}>
            ← Retour à l’atelier
          </button>
          <span>Recalage BAT, bibliothèque et préparation Illustrator</span>
        </div>
        <AdvancedApp />
      </>
    );
  return (
    <Studio
      user={user}
      onLogout={() => {
        void fetch("/session/logout", { method: "POST" }).then(() =>
          setUser(null),
        );
      }}
      onAdvanced={() => setAdvanced(true)}
    />
  );
}
function Studio({
  user,
  onLogout,
  onAdvanced,
}: {
  user: User;
  onLogout: () => void;
  onAdvanced: () => void;
}) {
  const editor = useEditor(),
    p = editor.project;
  const [projects, setProjects] = useState<Summary[]>([]),
    [libraries, setLibraries] = useState<Library[]>([]),
    [catalogue, setCatalogue] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [showCreate, setShowCreate] = useState(false),
    [showCatalogue, setShowCatalogue] = useState(false),
    [tab, setTab] = useState<"properties" | "analyses" | "history">(
      "properties",
    );
  const [documentId, setDocument] = useState(""),
    [page, setPage] = useState(1),
    [floorId, setFloor] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [tool, setTool] = useState<Tool>("select"),
    [zoom, setZoom] = useState(100),
    [showBoxes, setBoxes] = useState(true),
    [showAnchors, setAnchors] = useState(true);
  const [floorName, setFloorName] = useState("R-1"),
    [jobs, setJobs] = useState<Job[]>([]),
    [history, setHistory] = useState<
      { revision: number; actor: string; created: string }[]
    >([]),
    [gpu, setGpu] = useState("not_configured");
  const [engine, setEngine] = useState("local"),
    [importEngine, setImportEngine] = useState("paddleocr"),
    [imageWidth, setImageWidth] = useState(""),
    [imageHeight, setImageHeight] = useState("");
  const [catalogueDraft, setCatalogueDraft] = useState<Entry | null>(null);
  const source = p?.documents.find((d) => d.id === documentId),
    pageData = source?.pages[page - 1],
    floor = p?.state.floors.find((f) => f.id === floorId),
    a = p?.state.annotations.find((a) => a.id === selected[0]);
  const region =
    floor?.source_document_id === documentId && floor.source_page === page
      ? floor.source_region
      : undefined;
  const annotations =
    p?.state.annotations.filter(
      (a) =>
        a.source_document_id === documentId &&
        a.source_page === page &&
        (!floorId || a.floor_id === floorId),
    ) || [];
  const lib = libraries.find((l) => l.id === p?.state.library_id),
    asset = lib?.assets.find((x) => x.id === a?.asset_id);
  const image =
    p && source
      ? url(`/projects/${p.id}/documents/${source.id}/pages/${page}`)
      : "";
  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }
  async function refresh() {
    const [ps, ls, cs, gs] = await Promise.all([
      api<Summary[]>("/projects"),
      api<Library[]>("/libraries"),
      api<Entry[]>("/projects/catalogue"),
      api<{ status: string }>("/projects/ai-status"),
    ]);
    setProjects(ps);
    setLibraries(ls);
    setCatalogue(cs);
    setGpu(gs.status);
  }
  useEffect(() => {
    void run("Ouverture…", refresh);
  }, []);
  useEffect(() => {
    if (!p) return;
    let alive = true;
    const poll = async () => {
      try {
        const js = await api<Job[]>(`/projects/${p.id}/jobs`);
        if (alive) setJobs(js);
      } catch {}
    };
    void poll();
    const id = setInterval(poll, 4000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [p?.id]);
  useEffect(() => {
    if (tab === "history" && p)
      void api<typeof history>(`/projects/${p.id}/history`)
        .then(setHistory)
        .catch((e) => setError(errorText(e)));
  }, [tab, p?.state.revision]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (busy) return;
      if (
        (e.target as Element).closest("input,textarea,select,[contenteditable]")
      )
        return;
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        e.shiftKey ? editor.redo() : editor.undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        void run("Enregistrement…", editor.save);
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        remove();
      } else if (e.key === "Escape") {
        setTool("select");
        setSelected([]);
      } else if (e.key === "v") setTool("select");
      else if (e.key === "h") setTool("pan");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });
  async function open(id: string) {
    await editor.save();
    const project = await api<Project>(`/projects/${id}`);
    editor.install(project);
    setDocument(project.documents.find((d) => d.role === "survey")?.id || "");
    setPage(1);
    setFloor("");
    setSelected([]);
    setZoom(100);
    setJobs([]);
    setTab("properties");
  }
  function patch(id: string, changes: Partial<Annotation>) {
    editor.edit((s) => ({
      ...s,
      annotations: s.annotations.map((item) =>
        item.id === id
          ? clearReview(item, { training_accepted: false, ...changes })
          : item,
      ),
    }));
  }
  function remove() {
    if (!selected.length) return;
    editor.edit((s) => ({
      ...s,
      annotations: s.annotations.filter((a) => !selected.includes(a.id)),
    }));
    setSelected([]);
  }
  function duplicate() {
    if (!a) return;
    const clone = {
      ...structuredClone(a),
      id: crypto.randomUUID().replaceAll("-", ""),
      bbox: moveBox(a.bbox, 0.01, 0.01),
      anchor: null,
      target: null,
      review: { ...emptyReview },
      status: "review",
      training_accepted: false,
    };
    editor.edit((s) => ({ ...s, annotations: [...s.annotations, clone] }));
    setSelected([clone.id]);
  }
  function draw(box: Box) {
    if (!p || !source) return;
    if (tool === "floor") {
      const id = "floor_" + crypto.randomUUID().slice(0, 8);
      editor.edit((s) => ({
        ...s,
        floors: [
          ...s.floors,
          {
            id,
            name: floorName || "Niveau",
            source_document_id: documentId,
            source_page: page,
            source_region: box,
            rotation_deg: 0,
            target_page: 1,
            artboard_index: 0,
            target_group: "",
            confirmed: false,
          },
        ],
      }));
      setFloor(id);
      setSelected([]);
      setTool("select");
      setNotice(
        "Niveau créé. Les coordonnées restent liées à la page originale.",
      );
      return;
    }
    const item: Annotation = {
      id: crypto.randomUUID().replaceAll("-", ""),
      source_document_id: documentId,
      source_page: page,
      bbox: box,
      anchor: null,
      anchor_kind: "unknown",
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
      evidence: "Annotation du dessinateur",
      comment: "",
      training_accepted: false,
    };
    editor.edit((s) => ({ ...s, annotations: [...s.annotations, item] }));
    setSelected([item.id]);
    setTool("select");
    setNotice(
      "Saisissez le texte, puis pointez séparément l’emplacement réel de l’équipement.",
    );
  }
  async function upload(files: FileList | File[]) {
    if (!p) return;
    await editor.save();
    for (const file of Array.from(files)) {
      const form = new FormData();
      form.append("file", file);
      form.append("role", "survey");
      const project = await api<Project>(
        `/projects/${p.id}/documents`,
        "POST",
        form,
      );
      editor.install(project);
      setDocument(project.documents.at(-1)!.id);
      setPage(1);
      setFloor("");
      setSelected([]);
    }
    setNotice("Import terminé. Les fichiers originaux sont conservés.");
  }
  async function exportData() {
    if (!p) return;
    await editor.save();
    download(
      "DOEMO-donnees.json",
      await api(`/projects/${p.id}/structured-export`),
    );
  }
  async function validate() {
    if (!p) return;
    await editor.save();
    const latest = await api<Project>(`/projects/${p.id}`);
    const result = await api<Project>(`/projects/${p.id}/state`, "PUT", {
      ...latest.state,
      workflow: "validated",
    });
    editor.install(result);
    setNotice(
      "Révision validée. Toute correction ultérieure réouvrira la revue.",
    );
  }
  async function importAnalysis(file: File) {
    if (!p || !source) return;
    if (!Number(imageWidth) || !Number(imageHeight))
      throw Error(
        "Indiquez les dimensions exactes de l’image utilisée par le moteur IA.",
      );
    if (file.size > 8 * 1024 ** 2) throw Error("JSON limité à 8 Mio");
    await editor.save();
    const latest = await api<Project>(`/projects/${p.id}`);
    await api(`/projects/${p.id}/analysis-imports`, "POST", {
      engine: importEngine,
      document_id: documentId,
      page,
      width: Number(imageWidth),
      height: Number(imageHeight),
      revision: latest.state.revision,
      data: JSON.parse(await file.text()),
    });
    setJobs(await api(`/projects/${p.id}/jobs`));
    setNotice(
      "Résultat archivé. Examinez les observations avant de les intégrer.",
    );
  }
  async function applyJob(job: Job) {
    if (!p) return;
    await editor.save();
    const latest = await api<Project>(`/projects/${p.id}`);
    editor.install(
      await api(`/projects/${p.id}/jobs/${job.id}/apply`, "POST", {
        revision: latest.state.revision,
      }),
    );
    setNotice(
      "Propositions ajoutées à la revue. Aucune correction existante remplacée.",
    );
  }
  const isAdmin = ["admin", "administration"].includes(user.role);
  return (
    <div className="studio-shell">
      <header className="studio-header" inert={!!busy}>
        <button
          className="studio-wordmark"
          onClick={() =>
            void run("Tableau de bord…", async () => {
              await editor.save();
              await refresh();
              setDocument("");
              window.location.hash = "";
              location.reload();
            })
          }
        >
          DOEMO <span>STUDIO</span>
        </button>
        <div className="header-context">
          {p ? (
            <>
              <span>Atelier de relevés</span>
              <strong>{p.name}</strong>
            </>
          ) : (
            <>
              <span>Production graphique</span>
              <strong>Votre espace de travail</strong>
            </>
          )}
        </div>
        <span className="gpu-status">
          ●{" "}
          {gpu === "available"
            ? "IA disponible"
            : gpu === "unavailable"
              ? "GPU indisponible"
              : "Travail sans GPU"}
        </span>
        <button onClick={() => setShowCatalogue(true)}>Référentiel</button>
        <span className="user-name">{user.login}</span>
        {standalone && (
          <button
            onClick={() =>
              void run("Déconnexion…", async () => {
                await editor.save();
                onLogout();
              })
            }
          >
            Déconnexion
          </button>
        )}
      </header>
      <div className="studio-nav" inert={!!busy}>
        <select
          aria-label="Projet"
          value={p?.id || ""}
          onChange={(e) => {
            if (e.target.value)
              void run("Ouverture…", () => open(e.target.value));
          }}
        >
          <option value="">Choisir un projet</option>
          {projects.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
        <button onClick={() => setShowCreate(true)}>＋ Nouveau projet</button>
        {p && (
          <>
            <label className="file-button">
              Importer des relevés
              <input
                aria-label="Importer des relevés"
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg"
                disabled={!!busy}
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  void run("Import et rendu des pages…", () => upload(files));
                  e.target.value = "";
                }}
              />
            </label>
            <button onClick={() => void run("Export…", exportData)}>
              Exporter les données
            </button>
            <button
              onClick={() =>
                void run("Ouverture Illustrator…", async () => {
                  await editor.save();
                  onAdvanced();
                })
              }
            >
              Illustrator & SAI ↗
            </button>
            <div className="spacer" />
            <span className={editor.dirty ? "save-pending" : "save-ok"}>
              {editor.saving
                ? "Sauvegarde…"
                : editor.dirty
                  ? "Modifications en cours"
                  : "✓ Enregistré"}
            </span>
            <button
              disabled={!!busy}
              onClick={() => void run("Enregistrement…", editor.save)}
            >
              Enregistrer
            </button>
          </>
        )}
      </div>
      {(error || editor.error || notice || busy) && (
        <div
          className={
            "studio-notice " + (error || editor.error ? "is-error" : "")
          }
          role={error || editor.error ? "alert" : "status"}
        >
          <span>{error || editor.error || busy || notice}</span>
          {editor.error && p && (
            <button
              onClick={() => download("DOEMO-corrections-locales.json", p)}
            >
              Sauver la copie locale
            </button>
          )}
          <button
            aria-label="Fermer le message"
            onClick={() => {
              setError("");
              setNotice("");
            }}
          >
            ×
          </button>
        </div>
      )}
      {!p ? (
        <main className="dashboard">
          <div className="dashboard-intro">
            <div>
              <div className="eyebrow">DU RELEVÉ AU PLAN VÉRIFIÉ</div>
              <h1>Chaque détail compte.</h1>
              <p>
                Importez vos relevés, repérez les équipements et préparez vos
                plans Illustrator dans un même atelier.
              </p>
            </div>
            <button className="primary" onClick={() => setShowCreate(true)}>
              Créer un projet →
            </button>
          </div>
          <div className="dashboard-stats">
            <div>
              <strong>{projects.length}</strong>
              <span>Projets</span>
            </div>
            <div>
              <strong>
                {projects.filter((x) => x.workflow !== "validated").length}
              </strong>
              <span>À vérifier</span>
            </div>
            <div>
              <strong>
                {projects.filter((x) => x.workflow === "validated").length}
              </strong>
              <span>Validés</span>
            </div>
            <div>
              <strong>
                {projects.reduce((n, x) => n + x.annotation_count, 0)}
              </strong>
              <span>Annotations enregistrées</span>
            </div>
          </div>
          <h2>Projets récents</h2>
          <div className="project-grid">
            {projects.map((x) => (
              <button
                className="project-card"
                key={x.id}
                onClick={() => void run("Ouverture…", () => open(x.id))}
              >
                <span className="project-icon">▧</span>
                <small>{x.metadata.reference || "DOSSIER"}</small>
                <strong>{x.name}</strong>
                <span>{x.metadata.client || x.owner}</span>
                <div>
                  <span className="pill">
                    {workflows[x.workflow] || "Brouillon"}
                  </span>
                  <span>{x.annotation_count} annotations →</span>
                </div>
              </button>
            ))}
            {!projects.length && (
              <div className="empty-project">
                Votre premier projet commence par un relevé PDF ou une image.
                L’éditeur reste disponible lorsque le GPU est arrêté.
              </div>
            )}
          </div>
        </main>
      ) : (
        <main className="editor-layout" aria-busy={!!busy} inert={!!busy}>
          <aside className="document-rail">
            <h2>Documents</h2>
            {p.documents
              .filter((d) => d.role === "survey")
              .map((d) => (
                <button
                  className={
                    "document-item " + (d.id === documentId ? "active" : "")
                  }
                  key={d.id}
                  onClick={() => {
                    setDocument(d.id);
                    setPage(1);
                    setFloor("");
                    setSelected([]);
                  }}
                >
                  <span>▧</span>
                  <strong>{d.name}</strong>
                  <small>
                    {d.pages.length} page{d.pages.length > 1 ? "s" : ""}
                  </small>
                </button>
              ))}
            <h2>Niveaux</h2>
            <button
              className={!floorId ? "active" : ""}
              onClick={() => {
                setFloor("");
                setZoom(100);
              }}
            >
              Page entière
            </button>
            {p.state.floors
              .filter(
                (f) =>
                  f.source_document_id === documentId && f.source_page === page,
              )
              .map((f) => (
                <button
                  className={f.id === floorId ? "active" : ""}
                  key={f.id}
                  onClick={() => {
                    setFloor(f.id);
                    setSelected([]);
                    setZoom(100);
                  }}
                >
                  {f.name} <span>→</span>
                </button>
              ))}
            <div className="floor-create">
              <label>
                Nom du niveau
                <input
                  value={floorName}
                  onChange={(e) => setFloorName(e.target.value)}
                  placeholder="RDC, R-1…"
                />
              </label>
              <button
                disabled={!source}
                onClick={() => {
                  setFloor("");
                  setTool("floor");
                  setNotice("Tracez un rectangle autour du niveau à isoler.");
                }}
              >
                ＋ Découper un niveau
              </button>
            </div>
            <h2>Affichage</h2>
            <label className="check">
              <input
                type="checkbox"
                checked={showBoxes}
                onChange={(e) => setBoxes(e.target.checked)}
              />
              Annotations
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={showAnchors}
                onChange={(e) => setAnchors(e.target.checked)}
              />
              Positions et liaisons
            </label>
            <div className="rail-note">
              Le cadre repère l’annotation.
              <br />
              Le point repère l’équipement.
              <br />
              Les deux restent indépendants.
            </div>
            <div className="revision-label">
              Révision {p.state.revision}
              <br />
              {workflows[p.state.workflow || "draft"]}
            </div>
          </aside>
          <section className="canvas-column">
            <div className="canvas-heading">
              <div>
                <h1>{floor?.name || source?.name || "Importer un relevé"}</h1>
                <span>
                  {pageData
                    ? `${pageData.width} × ${pageData.height} px · page ${page}`
                    : "PDF, PNG ou JPEG"}
                </span>
              </div>
              <select
                aria-label="Page"
                value={page}
                onChange={(e) => {
                  setPage(Number(e.target.value));
                  setFloor("");
                  setSelected([]);
                }}
              >
                {source?.pages.map((q) => (
                  <option key={q.number} value={q.number}>
                    Page {q.number}
                  </option>
                ))}
              </select>
            </div>
            <div className="canvas-toolbar">
              {(
                [
                  ["select", "↖", "Sélectionner"],
                  ["pan", "✥", "Déplacer la vue"],
                  ["annotation", "▣", "Encadrer une annotation"],
                  ["marquee", "▧", "Sélection rectangulaire"],
                  ["anchor", "⊕", "Pointer l’équipement"],
                ] as [Tool, string, string][]
              ).map(([id, symbol, label]) => (
                <button
                  key={id}
                  title={label}
                  aria-label={label}
                  aria-pressed={tool === id}
                  className={tool === id ? "active" : ""}
                  disabled={id === "anchor" && !a}
                  onClick={() => setTool(id)}
                >
                  {symbol}
                  <span>
                    {id === "annotation"
                      ? "Annotation"
                      : id === "anchor"
                        ? "Position"
                        : ""}
                  </span>
                </button>
              ))}
              <i />
              <button
                aria-label="Annuler"
                title="Annuler · ⌘Z"
                disabled={!editor.canUndo}
                onClick={editor.undo}
              >
                ↶
              </button>
              <button
                aria-label="Rétablir"
                disabled={!editor.canRedo}
                onClick={editor.redo}
              >
                ↷
              </button>
              <div className="spacer" />
              <button
                aria-label="Réduire"
                onClick={() => setZoom(Math.max(50, zoom - 25))}
              >
                −
              </button>
              <button onClick={() => setZoom(100)}>{zoom} %</button>
              <button
                aria-label="Agrandir"
                onClick={() => setZoom(Math.min(600, zoom + 25))}
              >
                ＋
              </button>
              <button
                title="Tourner le niveau"
                disabled={!floor}
                onClick={() =>
                  editor.edit((s) => ({
                    ...s,
                    floors: s.floors.map((f) =>
                      f.id === floorId
                        ? {
                            ...f,
                            rotation_deg: (((f.rotation_deg || 0) + 90) %
                              360) as 0 | 90 | 180 | 270,
                          }
                        : f,
                    ),
                  }))
                }
              >
                ⟳
              </button>
            </div>
            <div
              className="canvas-area"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const fs = Array.from(e.dataTransfer.files);
                if (fs.length) void run("Import…", () => upload(fs));
              }}
            >
              {source && pageData ? (
                <PlanCanvas
                  image={image}
                  width={pageData.width}
                  height={pageData.height}
                  region={region}
                  rotation={floor?.rotation_deg || 0}
                  zoom={zoom}
                  tool={tool}
                  annotations={annotations}
                  selected={selected}
                  showBoxes={showBoxes}
                  showAnchors={showAnchors}
                  onSelect={setSelected}
                  onBox={draw}
                  onAnchor={(q) => {
                    if (a)
                      patch(a.id, {
                        anchor: q,
                        anchor_kind: "manual",
                        target: null,
                      });
                    setTool("select");
                  }}
                  onMove={patch}
                />
              ) : (
                <div className="drop-zone">
                  <span>↥</span>
                  <h2>Déposez votre relevé ici</h2>
                  <p>
                    PDF, PNG ou JPEG · plusieurs fichiers acceptés
                    <br />
                    L’original est conservé dans le projet.
                  </p>
                </div>
              )}
            </div>
            <div className="canvas-bottom">
              <span>
                {tool === "annotation"
                  ? "Tracez le cadre du texte manuscrit"
                  : tool === "floor"
                    ? "Tracez le contour du niveau"
                    : tool === "anchor"
                      ? "Cliquez sur la position réelle de l’équipement"
                      : tool === "pan"
                        ? "Faites glisser pour déplacer la vue"
                        : "Sélectionnez un cadre ou faites glisser son point de position"}
              </span>
              <span>
                {selected.length} sélection · {annotations.length} annotations
              </span>
            </div>
            <section className="annotation-table">
              <div>
                <h2>Annotations du relevé</h2>
                <button disabled={!selected.length} onClick={remove}>
                  Supprimer la sélection
                </button>
              </div>
              <div className="annotation-rows">
                {annotations.map((item, i) => (
                  <button
                    key={item.id}
                    className={selected.includes(item.id) ? "active" : ""}
                    onClick={() => {
                      setSelected([item.id]);
                      setTab("properties");
                    }}
                  >
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    <strong>{item.text || "Sans texte"}</strong>
                    <span>
                      {catalogue.find((e) => e.code === item.equipment_type)
                        ?.name ||
                        item.equipment_type ||
                        "Catégorie à définir"}
                    </span>
                    <span className={"status-" + item.status}>
                      {statusLabels[item.status]}
                    </span>
                  </button>
                ))}
                {!annotations.length && (
                  <p>
                    Encadrez une annotation manuscrite pour commencer, ou
                    importez une analyse.
                  </p>
                )}
              </div>
            </section>
          </section>
          <aside className="inspector">
            <div className="inspector-tabs">
              {(["properties", "analyses", "history"] as const).map((t) => (
                <button
                  className={tab === t ? "active" : ""}
                  key={t}
                  onClick={() => setTab(t)}
                >
                  {t === "properties"
                    ? "Propriétés"
                    : t === "analyses"
                      ? "Analyses IA"
                      : "Historique"}
                </button>
              ))}
            </div>
            {tab === "properties" &&
              (!a ? (
                <div className="inspector-empty">
                  <span>↖</span>
                  <h2>Une annotation, une preuve.</h2>
                  <p>
                    Sélectionnez un élément du relevé pour vérifier son texte,
                    sa catégorie et sa position.
                  </p>
                  <h3>Bibliothèque du projet</h3>
                  <select
                    aria-label="Bibliothèque du projet"
                    value={p.state.library_id || ""}
                    onChange={(e) =>
                      editor.edit((s) => ({
                        ...s,
                        library_id: e.target.value || null,
                        mappings: [],
                        annotations: s.annotations.map((a) =>
                          clearReview(a, { asset_id: null }),
                        ),
                      }))
                    }
                  >
                    <option value="">Choisir la bibliothèque SAI</option>
                    {libraries.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={() =>
                      void run("Ouverture…", async () => {
                        await editor.save();
                        onAdvanced();
                      })
                    }
                  >
                    Importer / contrôler SAI
                  </button>
                  <hr />
                  <button
                    className="primary"
                    onClick={() => void run("Validation…", validate)}
                  >
                    Valider le projet
                  </button>
                  <p>La validation finale est réservée au responsable.</p>
                </div>
              ) : (
                <div className="property-form">
                  <div className="selection-heading">
                    <span className="pill">{statusLabels[a.status]}</span>
                    <div>
                      <button title="Dupliquer" onClick={duplicate}>
                        Dupliquer
                      </button>
                      <button title="Supprimer" onClick={remove}>
                        ×
                      </button>
                    </div>
                  </div>
                  <svg
                    className="evidence-crop"
                    viewBox={`${Math.max(0, a.bbox.x * pageData!.width - 12)} ${Math.max(0, a.bbox.y * pageData!.height - 12)} ${a.bbox.w * pageData!.width + 24} ${a.bbox.h * pageData!.height + 24}`}
                  >
                    <image
                      href={image}
                      width={pageData!.width}
                      height={pageData!.height}
                    />
                  </svg>
                  <small>Extrait du document original</small>
                  <label>
                    Texte de l’annotation
                    <input
                      aria-label="Texte de l’annotation"
                      value={a.text}
                      onChange={(e) => patch(a.id, { text: e.target.value })}
                    />
                  </label>
                  <label>
                    Catégorie
                    <select
                      aria-label="Catégorie"
                      value={a.equipment_type}
                      onChange={(e) => {
                        const entry = catalogue.find(
                          (c) => c.code === e.target.value,
                        );
                        const available = lib?.assets.find(
                          (x) => x.id === entry?.asset_id,
                        );
                        patch(a.id, {
                          equipment_type: e.target.value,
                          asset_id: available?.id || null,
                        });
                      }}
                    >
                      <option value="">À définir</option>
                      {catalogue
                        .filter((c) => c.active)
                        .map((c) => (
                          <option key={c.code} value={c.code}>
                            {c.name}
                          </option>
                        ))}
                      {a.equipment_type &&
                        !catalogue.some((c) => c.code === a.equipment_type) && (
                          <option value={a.equipment_type}>
                            {a.equipment_type}
                          </option>
                        )}
                    </select>
                  </label>
                  <label>
                    Niveau
                    <select
                      aria-label="Niveau de l’annotation"
                      value={a.floor_id || ""}
                      onChange={(e) =>
                        patch(a.id, { floor_id: e.target.value || null })
                      }
                    >
                      <option value="">À définir</option>
                      {p.state.floors
                        .filter(
                          (f) =>
                            !f.source_document_id ||
                            (f.source_document_id === documentId &&
                              f.source_page === page),
                        )
                        .map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Pictogramme SAI
                    <select
                      aria-label="Pictogramme SAI"
                      value={a.asset_id || ""}
                      onChange={(e) =>
                        patch(a.id, { asset_id: e.target.value || null })
                      }
                    >
                      <option value="">À associer</option>
                      {lib?.assets
                        .filter((x) => x.pictogram_candidate)
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.name}
                            {x.approved ? "" : " · à contrôler"}
                          </option>
                        ))}
                    </select>
                  </label>
                  {asset?.preview && (
                    <img
                      className="symbol-preview"
                      alt={asset.name}
                      src={url(
                        `/libraries/${lib!.id}/assets/${asset.id}/preview`,
                      )}
                    />
                  )}
                  <div className="position-card">
                    <strong>Position réelle de l’équipement</strong>
                    <p>
                      {a.anchor
                        ? `X ${(a.anchor.x * pageData!.width).toFixed(2)} · Y ${(a.anchor.y * pageData!.height).toFixed(2)} px`
                        : "Non définie"}
                    </p>
                    <button
                      className={tool === "anchor" ? "active" : ""}
                      onClick={() => setTool("anchor")}
                    >
                      ⊕ Pointer sur le plan
                    </button>
                    <small>
                      Le centre du texte ne définit pas la position de la porte.
                    </small>
                  </div>
                  <div className="form-pair">
                    <label>
                      Rotation (°)
                      <input
                        aria-label="Rotation"
                        type="number"
                        min={-360}
                        max={360}
                        value={a.rotation_deg}
                        onChange={(e) =>
                          patch(a.id, { rotation_deg: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Taille (mm)
                      <input
                        aria-label="Taille"
                        type="number"
                        min={0.1}
                        max={200}
                        step={0.1}
                        value={a.size_mm}
                        onChange={(e) =>
                          patch(a.id, { size_mm: Number(e.target.value) })
                        }
                      />
                    </label>
                  </div>
                  <label>
                    Commentaire
                    <textarea
                      value={a.comment || ""}
                      onChange={(e) => patch(a.id, { comment: e.target.value })}
                    />
                  </label>
                  <div className="provenance">
                    Source : {a.method}
                    <br />
                    {a.method === "manual"
                      ? "Saisie humaine"
                      : `Score du moteur : ${(a.confidence * 100).toFixed(1)} % · non calibré`}
                    <br />
                    {a.evidence}
                  </div>
                  <fieldset>
                    <legend>Contrôle humain</legend>
                    {(Object.keys(reviewLabels) as (keyof Review)[]).map(
                      (key) => (
                        <label className="check" key={key}>
                          <input
                            type="checkbox"
                            checked={a.review[key]}
                            disabled={
                              editor.saving ||
                              (key === "position" && !a.anchor) ||
                              (key === "asset" && !a.asset_id) ||
                              (key === "floor" && !a.floor_id) ||
                              (key === "equipment" && !a.equipment_type)
                            }
                            onChange={(e) =>
                              patch(a.id, {
                                review: {
                                  ...a.review,
                                  [key]: e.target.checked,
                                },
                              })
                            }
                          />
                          {reviewLabels[key]}
                        </label>
                      ),
                    )}
                  </fieldset>
                  <button
                    className="primary full-width"
                    disabled={
                      !Object.values(a.review).every(Boolean) || editor.saving
                    }
                    onClick={() => patch(a.id, { status: "confirmed" })}
                  >
                    Valider ce placement
                  </button>
                  <button
                    className="full-width"
                    onClick={() =>
                      patch(a.id, {
                        status: a.status === "rejected" ? "review" : "rejected",
                      })
                    }
                  >
                    {a.status === "rejected"
                      ? "Remettre à vérifier"
                      : "Rejeter cette proposition"}
                  </button>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={a.training_accepted || false}
                      disabled={
                        !a.review.equipment || !a.review.position || !a.anchor
                      }
                      onChange={(e) =>
                        patch(a.id, { training_accepted: e.target.checked })
                      }
                    />
                    Accepter cet exemple pour le dataset
                  </label>
                  <small>
                    L’export d’apprentissage nécessite aussi l’autorisation du
                    projet.
                  </small>
                </div>
              ))}
            {tab === "analyses" && (
              <div className="analysis-panel">
                <h2>Analyser le relevé</h2>
                <p>
                  Les résultats restent des propositions jusqu’à votre contrôle.
                </p>
                <label>
                  Moteur
                  <select
                    value={engine}
                    onChange={(e) => setEngine(e.target.value)}
                  >
                    <option value="local">OCR local · sans GPU</option>
                    <option value="paddleocr">PaddleOCR · RunPod</option>
                    <option value="qwen">Qwen · RunPod</option>
                    <option value="rtmdet">RTMDet · RunPod</option>
                  </select>
                </label>
                <button
                  className="primary full-width"
                  disabled={!source || !!busy}
                  onClick={() =>
                    void run("Mise en file…", async () => {
                      await api(`/projects/${p.id}/jobs`, "POST", {
                        document_id: documentId,
                        page,
                        engine,
                      });
                      setJobs(await api(`/projects/${p.id}/jobs`));
                    })
                  }
                >
                  Analyser avec l’IA
                </button>
                <h3>Importer un résultat existant</h3>
                <label>
                  Format
                  <select
                    value={importEngine}
                    onChange={(e) => setImportEngine(e.target.value)}
                  >
                    <option value="paddleocr">PaddleOCR JSON</option>
                    <option value="qwen">Qwen · analyse par zones</option>
                    <option value="rtmdet">RTMDet COCO · diagnostic</option>
                  </select>
                </label>
                <p>
                  Dimensions de l’image analysée, avant tout redimensionnement
                  d’affichage :
                </p>
                <div className="form-pair">
                  <label>
                    Largeur (px)
                    <input
                      type="number"
                      min={1}
                      value={imageWidth}
                      onChange={(e) => setImageWidth(e.target.value)}
                    />
                  </label>
                  <label>
                    Hauteur (px)
                    <input
                      type="number"
                      min={1}
                      value={imageHeight}
                      onChange={(e) => setImageHeight(e.target.value)}
                    />
                  </label>
                </div>
                <label className="file-button">
                  Choisir le JSON
                  <input
                    type="file"
                    accept=".json"
                    disabled={!source}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f)
                        void run("Import du résultat…", () =>
                          importAnalysis(f),
                        );
                      e.target.value = "";
                    }}
                  />
                </label>
                {jobs.map((j) => (
                  <article className="job-card" key={j.id}>
                    <strong>{j.stage}</strong>
                    <small>
                      {j.created} · {j.status}
                    </small>
                    {j.error && <p>{j.error}</p>}
                    {j.result?.warnings?.map((w, i) => (
                      <p key={i}>{w}</p>
                    ))}
                    {j.result && (
                      <>
                        <span>
                          {j.result.annotations.length} observations localisées
                        </span>
                        <details>
                          <summary>Observations non localisées</summary>
                          <pre>
                            {JSON.stringify(j.result.observations, null, 2)}
                          </pre>
                        </details>
                        {!!j.result.annotations.length && (
                          <button
                            onClick={() =>
                              void run("Intégration…", () => applyJob(j))
                            }
                          >
                            Ajouter à la revue
                          </button>
                        )}
                      </>
                    )}
                    {["failed", "waiting_gpu", "interrupted"].includes(
                      j.status,
                    ) && (
                      <button
                        onClick={() =>
                          void run("Relance…", async () => {
                            await api(
                              `/projects/${p.id}/jobs/${j.id}/retry`,
                              "POST",
                              {},
                            );
                            setJobs(await api(`/projects/${p.id}/jobs`));
                          })
                        }
                      >
                        Réessayer
                      </button>
                    )}
                  </article>
                ))}
              </div>
            )}
            {tab === "history" && (
              <div className="history-panel">
                <h2>Corrections enregistrées</h2>
                <p>
                  Chaque sauvegarde conserve une révision consultable. Une
                  restauration crée une nouvelle version.
                </p>
                {isAdmin && (
                  <details className="training-panel">
                    <summary>Apprentissage · autorisation et export</summary>
                    <p>
                      Activez cette option uniquement si la réutilisation des
                      documents de ce projet est autorisée.
                    </p>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={Boolean(p.metadata?.training_authorized)}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          void run("Autorisation…", async () => {
                            await editor.save();
                            editor.install(
                              await api(`/projects/${p.id}/metadata`, "PUT", {
                                ...p.metadata,
                                training_authorized: checked,
                              }),
                            );
                          });
                        }}
                      />
                      Réutilisation autorisée
                    </label>
                    <button
                      onClick={() =>
                        void run("Export du dataset…", async () => {
                          await editor.save();
                          download(
                            "DOEMO-dataset-coco.json",
                            await api(`/projects/${p.id}/dataset`),
                          );
                        })
                      }
                    >
                      Exporter les exemples acceptés (COCO)
                    </button>
                  </details>
                )}
                {history.map((h) => (
                  <div className="history-item" key={h.revision}>
                    <strong>Révision {h.revision}</strong>
                    <small>
                      {h.actor} · {h.created} UTC
                    </small>
                    <button
                      onClick={() =>
                        void run("Export de la révision…", async () =>
                          download(
                            `DOEMO-revision-${h.revision}.json`,
                            await api(
                              `/projects/${p.id}/history/${h.revision}`,
                            ),
                          ),
                        )
                      }
                    >
                      Télécharger
                    </button>
                    <button
                      onClick={() =>
                        void run("Restauration…", async () => {
                          await editor.save();
                          const historical = await api<State>(
                            `/projects/${p.id}/history/${h.revision}`,
                          );
                          editor.edit((s) => ({
                            ...historical,
                            revision: s.revision,
                          }));
                        })
                      }
                    >
                      Restaurer
                    </button>
                  </div>
                ))}
              </div>
            )}
          </aside>
        </main>
      )}
      {showCreate && (
        <div className="studio-modal-backdrop">
          <form
            className="studio-modal"
            aria-label="Nouveau projet"
            onSubmit={(e) => {
              e.preventDefault();
              const fields = Object.fromEntries(new FormData(e.currentTarget));
              void run("Création du projet…", async () => {
                await editor.save();
                const project = await api<Project>("/projects", "POST", fields);
                await refresh();
                editor.install(project);
                setDocument("");
                setFloor("");
                setSelected([]);
                setShowCreate(false);
              });
            }}
          >
            <div className="modal-title">
              <h2>Nouveau projet</h2>
              <button type="button" onClick={() => setShowCreate(false)}>
                ×
              </button>
            </div>
            <p>
              Un dossier pour vos relevés, annotations et plans de sécurité.
            </p>
            <label>
              Bâtiment / nom du projet
              <input name="name" required placeholder="Animalis · Grenelle" />
            </label>
            <div className="form-pair">
              <label>
                Référence
                <input name="reference" />
              </label>
              <label>
                Client
                <input name="client" />
              </label>
            </div>
            <label>
              Adresse
              <input name="address" />
            </label>
            <div className="form-pair">
              <label>
                Type d’établissement
                <input name="building_type" />
              </label>
              <label>
                Dessinateur responsable
                <input name="responsible" defaultValue={user.login} />
              </label>
            </div>
            <button className="primary full-width" disabled={!!busy}>
              Créer le projet
            </button>
          </form>
        </div>
      )}
      {showCatalogue && (
        <div className="studio-modal-backdrop">
          <section
            className="studio-modal catalogue-modal"
            role="dialog"
            aria-label="Référentiel des équipements"
          >
            <div className="modal-title">
              <h2>Référentiel DOEMO</h2>
              <button
                onClick={() => {
                  setShowCatalogue(false);
                  setCatalogueDraft(null);
                }}
              >
                Fermer
              </button>
            </div>
            <p>
              Codes métier et correspondances SAI. Les variantes d’extincteurs
              utilisent le pictogramme portatif unique.
            </p>
            {catalogue.map((c) => (
              <button
                className="catalogue-row"
                key={c.code}
                onClick={() => setCatalogueDraft({ ...c })}
              >
                <strong>{c.name}</strong>
                <span>{c.code}</span>
                <small>
                  {c.synonyms.join(" · ")} {!c.active ? "· inactif" : ""}
                </small>
              </button>
            ))}
            {isAdmin && (
              <button
                onClick={() =>
                  setCatalogueDraft({
                    code: "NOUVEAU",
                    name: "",
                    synonyms: [],
                    asset_id: null,
                    active: true,
                    description: "",
                  })
                }
              >
                ＋ Nouvelle catégorie
              </button>
            )}
            {catalogueDraft && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void run("Enregistrement du référentiel…", async () => {
                    await api(
                      `/projects/catalogue/${catalogueDraft.code}`,
                      "PUT",
                      catalogueDraft,
                    );
                    setCatalogue(await api("/projects/catalogue"));
                    setCatalogueDraft(null);
                  });
                }}
              >
                <label>
                  Code stable
                  <input
                    value={catalogueDraft.code}
                    onChange={(e) =>
                      setCatalogueDraft({
                        ...catalogueDraft,
                        code: e.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Nom
                  <input
                    value={catalogueDraft.name}
                    onChange={(e) =>
                      setCatalogueDraft({
                        ...catalogueDraft,
                        name: e.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Synonymes (séparés par une virgule)
                  <input
                    value={catalogueDraft.synonyms.join(",")}
                    onChange={(e) =>
                      setCatalogueDraft({
                        ...catalogueDraft,
                        synonyms: e.target.value.split(","),
                      })
                    }
                  />
                </label>
                <label>
                  Identifiant SAI
                  <input
                    value={catalogueDraft.asset_id || ""}
                    onChange={(e) =>
                      setCatalogueDraft({
                        ...catalogueDraft,
                        asset_id: e.target.value || null,
                      })
                    }
                  />
                </label>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={catalogueDraft.active}
                    onChange={(e) =>
                      setCatalogueDraft({
                        ...catalogueDraft,
                        active: e.target.checked,
                      })
                    }
                  />
                  Actif
                </label>
                <button className="primary" disabled={!isAdmin}>
                  Enregistrer
                </button>
              </form>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<Root />);
