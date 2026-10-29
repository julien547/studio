import { useCallback, useEffect, useRef, useState } from "react";
import { api, url } from "../api";
import { AnnotationEditor } from "./AnnotationEditor";
import { QwenPreview } from "./QwenPreview";
import {
  engines,
  message,
  prefix,
  statusNames,
  type Capability,
  type Category,
  type Dataset,
  type Engine,
  type Example,
  type Perform,
  type ProjectSummary,
  type Registry,
  type Run,
} from "./types";
import { GpuPanel } from "../GpuPanel";
import "./training.css";
import {CirculationCorrections} from './CirculationCorrections';
const tabs = [
  "Annotations",
  "Datasets",
  "Entraînements",
  "Modèles IA",
] as const;
type Tab = (typeof tabs)[number];
export function TrainingPage({
  onBack,
  user,
}: {
  onBack: () => void;
  user: { login: string; role: string };
}) {
  const [engine, setEngine] = useState<Engine>("qwen"),
    [tab, setTab] = useState<Tab>("Annotations"),
    [caps, setCaps] = useState<Record<Engine, Capability> | null>(null),
    [categories, setCategories] = useState<Category[]>([]),
    [projects, setProjects] = useState<ProjectSummary[]>([]),
    [error, setError] = useState(""),
    [initial, setInitial] = useState<Example | null>(null);
  const dirty = useRef(false),
    onDirty = useCallback((v: boolean) => {
      dirty.current = v;
    }, []);
  const admin = ["admin", "administration"].includes(user.role);
  const refreshProjects = useCallback(
    async () => setProjects(await api("/projects")),
    [],
  );
  const load = useCallback(async () => {
    try {
      const [c, cs, ps] = await Promise.all([
        api<{ engines: Record<Engine, Capability> }>(prefix + "/capabilities"),
        api<Category[]>(prefix + "/categories"),
        api<ProjectSummary[]>("/projects"),
      ]);
      setCaps(c.engines);
      setCategories(cs);
      setProjects(ps);
      setError("");
    } catch (e) {
      setError(message(e));
    }
  }, []);
  useEffect(() => {
    if (admin) void load();
  }, [admin, load]);
  const leave = (fn: () => void) => {
    if (
      !dirty.current ||
      window.confirm("Abandonner les corrections non enregistrées ?")
    ) {
      dirty.current = false;
      fn();
    }
  };
  if (!admin)
    return (
      <main className="training-denied">
        <h1>Accès réservé aux administrateurs</h1>
        <button onClick={onBack}>Retour à l’atelier</button>
      </main>
    );
  return (
    <div className="training-shell">
      <aside className="training-sidebar">
        <a
          className="training-brand"
          href="/releves/"
          onClick={(e) => {
            e.preventDefault();
            leave(onBack);
          }}
        >
          DOEMO <span>STUDIO</span>
        </a>
        <button onClick={() => leave(onBack)}>← Atelier de plans</button>
        <p className="training-eyebrow">Entraînement IA</p>
        <nav aria-label="Moteurs d’apprentissage">
          {Object.entries(engines).map(([id, name]) => (
            <button
              key={id}
              aria-current={engine === id ? "page" : undefined}
              className={engine === id ? "active" : ""}
              onClick={() => {
                if (id !== engine)
                  leave(() => {
                    setEngine(id as Engine);
                    setInitial(null);
                  });
              }}
            >
              {name}
              <small>
                {id === "qwen"
                  ? "Comprendre les plans"
                  : id === "paddleocr"
                    ? "Lire les écritures"
                    : id === "rtmdet"
                      ? "Détecter les équipements"
                      : "Reconstruire les murs"}
              </small>
            </button>
          ))}
        </nav>
        <div className="training-sidebar-footer">
          {user.login}
          <br />
          Espace administrateur
        </div>
      </aside>
      <main className="training-main">
        <CirculationCorrections/>
        <header>
          <p className="training-eyebrow">Corrections → datasets → modèles</p>
          <h1>Entraînement IA</h1>
          <p>
            Conservez vos corrections et préparez chaque moteur à partir
            d’exemples vérifiés.
          </p>
        </header>
        {error && (
          <div role="alert" className="training-error">
            {error} <button onClick={() => void load()}>Réessayer</button>
          </div>
        )}
        {!caps && !error && (
          <p role="status">Connexion aux services d’apprentissage…</p>
        )}
        {caps && (
          <>
            <div className="training-engine-title">
              <div>
                <h2>{engines[engine]}</h2>
                <p>{caps[engine].function}</p>
              </div>
              <span className="training-badge">
                {caps[engine].training
                  ? "Entraînement disponible"
                  : "Annotations disponibles"}
              </span>
            </div>
            <nav
              className="training-tabs"
              aria-label="Rubriques d’apprentissage"
            >
              {tabs.map((t) => (
                <button
                  key={t}
                  aria-current={tab === t ? "page" : undefined}
                  className={tab === t ? "active" : ""}
                  onClick={() => {
                    if (t !== tab)
                      leave(() => {
                        setTab(t);
                        setInitial(null);
                      });
                  }}
                >
                  {t}
                </button>
              ))}
            </nav>
            <Workspace
              key={engine}
              engine={engine}
              tab={tab}
              capability={caps[engine]}
              categories={categories}
              projects={projects}
              refreshProjects={refreshProjects}
              onCategories={setCategories}
              initial={initial}
              onDirty={onDirty}
              onEdit={(e) =>
                leave(() => {
                  setInitial(e);
                  setTab("Annotations");
                })
              }
            />
          </>
        )}
      </main>
    </div>
  );
}
function Workspace({
  engine,
  tab,
  capability,
  categories,
  projects,
  refreshProjects,
  onCategories,
  initial,
  onDirty,
  onEdit,
}: {
  engine: Engine;
  tab: Tab;
  capability: Capability;
  categories: Category[];
  projects: ProjectSummary[];
  refreshProjects: () => Promise<void>;
  onCategories: (v: Category[]) => void;
  initial: Example | null;
  onDirty: (v: boolean) => void;
  onEdit: (e: Example) => void;
}) {
  const [examples, setExamples] = useState<Example[]>([]),
    [datasets, setDatasets] = useState<Dataset[]>([]),
    [runs, setRuns] = useState<Run[]>([]),
    [registry, setRegistry] = useState<Registry | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const alive = useRef(true),
    working = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const refresh = useCallback(async () => {
    const [e, d, r, m] = await Promise.all([
      api<Example[]>(`${prefix}/examples?engine=${engine}`),
      api<Dataset[]>(`${prefix}/datasets?engine=${engine}`),
      api<Run[]>(`${prefix}/runs?engine=${engine}`),
      api<Registry>(`${prefix}/models?engine=${engine}`),
    ]);
    if (alive.current) {
      setExamples(e);
      setDatasets(d);
      setRuns(r);
      setRegistry(m);
    }
  }, [engine]);
  const perform: Perform = useCallback(async (fn, success = "") => {
    if (working.current) return;
    working.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      if (alive.current) setNotice(success);
    } catch (e) {
      if (alive.current) setError(message(e));
    } finally {
      working.current = false;
      if (alive.current) setBusy(false);
    }
  }, []);
  useEffect(() => {
    void perform(refresh);
  }, [refresh, perform]);
  useEffect(() => {
    if (tab !== "Entraînements") return;
    const timer = setInterval(() => {
      if (!working.current)
        void refresh().catch((e) => {
          if (alive.current) setError(message(e));
        });
    }, 5000);
    return () => clearInterval(timer);
  }, [tab, refresh]);
  return (
    <>
      <div aria-live="polite">
        {busy && <p role="status">Traitement en cours…</p>}
        {notice && (
          <p className="training-success" role="status">
            {notice}
          </p>
        )}
      </div>
      {error && (
        <p className="training-error" role="alert">
          {error}
        </p>
      )}
      <fieldset
        disabled={busy}
        inert={busy}
        className="training-content"
        aria-busy={busy}
      >
        {tab === "Annotations" && (
          <AnnotationEditor
            key={initial?.id || "new"}
            engine={engine}
            categories={categories}
            projects={projects}
            initial={initial}
            perform={perform}
            onSaved={refresh}
            onDirty={onDirty}
            refreshProjects={refreshProjects}
          />
        )}
        {tab === "Datasets" && (
          <Datasets
            engine={engine}
            examples={examples}
            datasets={datasets}
            categories={categories}
            projects={projects}
            perform={perform}
            refresh={refresh}
            onEdit={onEdit}
            onCategories={onCategories}
          />
        )}
        {tab === "Entraînements" && (
          <Runs
            engine={engine}
            capability={capability}
            datasets={datasets}
            runs={runs}
            perform={perform}
            refresh={refresh}
          />
        )}
        {tab === "Modèles IA" && registry && (
          <Models
            engine={engine}
            capability={capability}
            registry={registry}
            datasets={datasets}
            runs={runs}
            perform={perform}
            refresh={refresh}
          />
        )}
      </fieldset>
    </>
  );
}
function DatasetSelect({
  datasets,
  value,
  onChange,
}: {
  datasets: Dataset[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label>
      Version du dataset
      <select
        aria-label="Version du dataset"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Choisir une version</option>
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name} · v{d.version}
          </option>
        ))}
      </select>
    </label>
  );
}
function Datasets({
  engine,
  examples,
  datasets,
  categories,
  projects,
  perform,
  refresh,
  onEdit,
  onCategories,
}: {
  engine: Engine;
  examples: Example[];
  datasets: Dataset[];
  categories: Category[];
  projects: ProjectSummary[];
  perform: Perform;
  refresh: () => Promise<void>;
  onEdit: (e: Example) => void;
  onCategories: (v: Category[]) => void;
}) {
  const [filter, setFilter] = useState({
      project: "",
      category: "",
      status: "",
      since: "",
    }),
    [selected, setSelected] = useState<string[]>([]),
    [name, setName] = useState(""),
    [detail, setDetail] = useState<Dataset | null>(null),
    [category, setCategory] = useState<Category>({
      code: "",
      name: "",
      kind: "equipment",
      active: true,
    });
  const visible = examples.filter(
    (e) =>
      (!filter.project || e.project_id === filter.project) &&
      (!filter.category ||
        e.data.labels.some((l) => l.category === filter.category)) &&
      (!filter.status || e.status === filter.status) &&
      (!filter.since || e.updated.slice(0, 10) >= filter.since),
  );
  return (
    <>
      <div className="training-toolbar">
        <label>
          Filtrer par projet
          <select
            aria-label="Filtrer par projet"
            value={filter.project}
            onChange={(e) => setFilter({ ...filter, project: e.target.value })}
          >
            <option value="">Tous les projets</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filtrer par catégorie
          <select
            aria-label="Filtrer par catégorie"
            value={filter.category}
            onChange={(e) => setFilter({ ...filter, category: e.target.value })}
          >
            <option value="">Toutes les catégories</option>
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Statut
          <select
            aria-label="Statut"
            value={filter.status}
            onChange={(e) => setFilter({ ...filter, status: e.target.value })}
          >
            <option value="">Tous les statuts</option>
            {["draft", "validated", "rejected"].map((s) => (
              <option key={s} value={s}>
                {statusNames[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Depuis le
          <input
            type="date"
            value={filter.since}
            onChange={(e) => setFilter({ ...filter, since: e.target.value })}
          />
        </label>
      </div>
      <h3>
        Exemples enregistrés{" "}
        <span className="training-badge">{visible.length}</span>
      </h3>
      {!visible.length ? (
        <div className="training-empty">
          Aucun exemple avec ces filtres. Enregistrez vos premières corrections
          dans Annotations.
        </div>
      ) : (
        <div className="training-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Sélection</th>
                <th>Projet / page</th>
                <th>Statut</th>
                <th>Annotations</th>
                <th>Dernière modification</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((e) => (
                <tr key={e.id}>
                  <td>
                    <input
                      aria-label={`Inclure l’exemple ${e.id}`}
                      type="checkbox"
                      disabled={e.status !== "validated"}
                      checked={selected.includes(e.id)}
                      onChange={(ev) =>
                        setSelected(
                          ev.target.checked
                            ? [...selected, e.id]
                            : selected.filter((id) => id !== e.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    {projects.find((p) => p.id === e.project_id)?.name ||
                      e.project_id}
                    <small>
                      Page {e.page} · {e.id.slice(0, 8)}
                    </small>
                  </td>
                  <td>{statusNames[e.status]}</td>
                  <td>{e.data.labels.length}</td>
                  <td>
                    {e.updated}
                    <small>{e.author}</small>
                  </td>
                  <td>
                    <button onClick={() => onEdit(e)}>
                      Vérifier / corriger
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form
        className="training-card training-inline"
        onSubmit={(e) => {
          e.preventDefault();
          void perform(async () => {
            const d = await api<Dataset>(prefix + "/datasets", "POST", {
              engine,
              name,
              example_ids: selected,
            });
            setDetail(d);
            setSelected([]);
            await refresh();
          }, "Version du dataset créée.");
        }}
      >
        <label>
          Nom du dataset
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
          />
        </label>
        <span>{selected.length} exemple(s) sélectionné(s)</span>
        <button className="primary" disabled={!selected.length || !name.trim()}>
          Créer une version du dataset
        </button>
      </form>
      <h3>Versions immuables</h3>
      <div className="training-cards">
        {datasets.map((d) => (
          <article key={d.id} className="training-card">
            <h4>
              {d.name} · v{d.version}
            </h4>
            <p>{d.created}</p>
            <button
              onClick={() =>
                void perform(async () =>
                  setDetail(await api(`${prefix}/datasets/${d.id}`)),
                )
              }
            >
              Voir le contenu
            </button>
            <button
              onClick={() =>
                void perform(async () => {
                  const response = await fetch(
                    url(`${prefix}/datasets/${d.id}/export`),
                    { credentials: "same-origin" },
                  );
                  if (!response.ok) {
                    let text = "Export impossible";
                    try {
                      text = (await response.json()).detail || text;
                    } catch {}
                    throw Error(text);
                  }
                  const href = URL.createObjectURL(await response.blob());
                  const a = document.createElement("a");
                  a.href = href;
                  a.download = `DOEMO-dataset-${d.id}.zip`;
                  a.click();
                  setTimeout(() => URL.revokeObjectURL(href), 1000);
                })
              }
            >
              Exporter le dataset
            </button>
          </article>
        ))}
      </div>
      {detail && (
        <section className="training-card">
          <h4>
            {detail.name} · v{detail.version}
          </h4>
          <p>
            {detail.snapshot?.examples.length} exemples ·{" "}
            {detail.snapshot?.groups} groupes de bâtiments/documents
          </p>
          <div className="training-stats">
            {["train", "validation", "test"].map((s) => (
              <span key={s}>
                {s === "train"
                  ? "Entraînement"
                  : s === "validation"
                    ? "Validation"
                    : "Test"}{" "}
                :{" "}
                {detail.snapshot?.examples.filter((e) => e.split === s).length}
              </span>
            ))}
          </div>
          {detail.snapshot?.warnings.map((w) => (
            <p key={w} className="training-warning">
              {w}
            </p>
          ))}
          <small>SHA-256 : {detail.sha256}</small>
        </section>
      )}
      <details className="training-card">
        <summary>Administrer les catégories</summary>
        <p>Une catégorie utilisée conserve son type géométrique.</p>
        <label>
          Catégorie existante
          <select
            aria-label="Catégorie existante"
            value={
              categories.some((c) => c.code === category.code)
                ? category.code
                : ""
            }
            onChange={(e) =>
              setCategory(
                categories.find((c) => c.code === e.target.value) || {
                  code: "",
                  name: "",
                  kind: "equipment",
                  active: true,
                },
              )
            }
          >
            <option value="">Nouvelle catégorie</option>
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <form
          className="training-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            void perform(async () => {
              await api(`${prefix}/categories/${category.code}`, "PUT", {
                ...category,
                active: !!category.active,
              });
              onCategories(await api(prefix + "/categories"));
            }, "Catégorie enregistrée.");
          }}
        >
          <label>
            Code
            <input
              required
              pattern="[A-Z][A-Z0-9_]{1,50}"
              value={category.code}
              onChange={(e) =>
                setCategory({ ...category, code: e.target.value })
              }
            />
          </label>
          <label>
            Nom
            <input
              required
              value={category.name}
              onChange={(e) =>
                setCategory({ ...category, name: e.target.value })
              }
            />
          </label>
          <label>
            Type
            <select
              aria-label="Type"
              value={category.kind}
              disabled={categories.some((c) => c.code === category.code)}
              onChange={(e) =>
                setCategory({
                  ...category,
                  kind: e.target.value as Category["kind"],
                })
              }
            >
              {Object.entries({
                wall: "Mur",
                door: "Porte",
                opening: "Ouverture",
                equipment: "Équipement",
                text: "Texte",
                other: "Autre",
              }).map(([k, n]) => (
                <option key={k} value={k}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="training-check">
            <input
              type="checkbox"
              checked={!!category.active}
              onChange={(e) =>
                setCategory({ ...category, active: e.target.checked })
              }
            />
            Active
          </label>
          <button>Enregistrer la catégorie</button>
        </form>
      </details>
    </>
  );
}
function Runs({
  engine,
  capability,
  datasets,
  runs,
  perform,
  refresh,
}: {
  engine: Engine;
  capability: Capability;
  datasets: Dataset[];
  runs: Run[];
  perform: Perform;
  refresh: () => Promise<void>;
}) {
  const [dataset, setDataset] = useState<Dataset | null>(null),
    [epochs, setEpochs] = useState(10),
    [batch, setBatch] = useState(1),
    [rate, setRate] = useState(0.0001),
    [logs, setLogs] = useState<unknown>(null);
  const request = useRef<{ fingerprint: string; key: string } | null>(null);
  const count = dataset?.snapshot?.examples.length || 0,
    splitReady = ["train", "validation", "test"].every((s) =>
      dataset?.snapshot?.examples.some((e) => e.split === s),
    );
  return (
    <>
      <GpuPanel administrator onStatus={() => {}} />
      {engine === "qwen" && (
        <p className="training-card">
          Fine-tuning LoRA de Qwen3.5-9B sur les images et interprétations
          validées. Les poids de base restent figés ; le résultat est un
          adaptateur candidat. La perte sur les lots réservés ne garantit pas
          une amélioration des réponses. Le référentiel de conventions et l’IA
          architecturale restent des fonctions distinctes.
        </p>
      )}
      {engine === "paddleocr" && (
        <p className="training-card">
          Cet entraînement améliore la lecture des textes recadrés et vérifiés.
          Les résultats mesurent les erreurs de caractères (CER) et de mots
          (WER) sur des exemples réservés. Le modèle obtenu reste un candidat à
          valider avant utilisation dans les analyses.
        </p>
      )}
      {!capability.training && (
        <div className="training-warning">
          <h3>Entraînement non disponible</h3>
          <p>{capability.reason}</p>
          <p>
            Les exemples et datasets restent accessibles lorsque le GPU est
            arrêté.
          </p>
        </div>
      )}
      <form
        className="training-card training-fields"
        onSubmit={(e) => {
          e.preventDefault();
          if (!capability.training || !dataset || !splitReady) return;
          if (
            !window.confirm(
              "Lancer cet entraînement sur le GPU ? Cette opération peut entraîner des coûts RunPod.",
            )
          )
            return;
          void perform(async () => {
            const parameters = {
              engine,
              dataset_id: dataset.id,
              epochs,
              batch_size: batch,
              learning_rate: rate,
            };
            const fingerprint = JSON.stringify(parameters);
            if (request.current?.fingerprint !== fingerprint)
              request.current = { fingerprint, key: crypto.randomUUID() };
            await api(prefix + "/runs", "POST", {
              ...parameters,
              confirmed: true,
              request_key: request.current!.key,
            });
            await refresh();
            request.current = null;
          }, "Entraînement demandé.");
        }}
      >
        <DatasetSelect
          datasets={datasets}
          value={dataset?.id || ""}
          onChange={(id) =>
            void perform(async () =>
              setDataset(id ? await api(`${prefix}/datasets/${id}`) : null),
            )
          }
        />
        {dataset && (
          <>
            <p>
              {count} exemples · {dataset.snapshot?.groups} groupes indépendants
            </p>
            {count < capability.minimum_recommended_examples && (
              <p className="training-warning">
                Peu d’exemples : {capability.minimum_recommended_examples}{" "}
                recommandés. Ce seuil ne garantit pas la qualité du modèle.
              </p>
            )}
            {!splitReady && (
              <p className="training-warning">
                Il manque un lot indépendant de validation ou de test.
              </p>
            )}
          </>
        )}
        <div className="training-toolbar">
          <label>
            Époques
            <input
              type="number"
              min="1"
              max="100"
              value={epochs}
              onChange={(e) => setEpochs(Number(e.target.value))}
            />
          </label>
          <label>
            Taille de lot
            <input
              type="number"
              min="1"
              max={capability.batch_size_max || 4}
              value={batch}
              onChange={(e) => setBatch(Number(e.target.value))}
            />
          </label>
          <label>
            Taux d’apprentissage
            <input
              type="number"
              min="0.000001"
              max={capability.learning_rate_max || 0.001}
              step="0.000001"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
            />
          </label>
        </div>
        <button
          className="primary"
          disabled={!capability.training || !dataset || !splitReady}
        >
          Lancer l’entraînement
        </button>
      </form>
      <h3>Tâches d’entraînement</h3>
      {!runs.length && <p>Aucun entraînement lancé pour ce moteur.</p>}
      {runs.map((r) => (
        <article className="training-card" key={r.id}>
          <h4>
            {statusNames[r.status] || r.status} · {r.id.slice(0, 8)}
          </h4>
          <p>
            {r.created} ·{" "}
            {datasets.find((d) => d.id === r.dataset_id)?.name || r.dataset_id}
          </p>
          {r.progress !== null ? (
            <label>
              Progression reçue du service
              <progress value={r.progress} max={1} />
              <span>{Math.round(r.progress * 100)} %</span>
            </label>
          ) : (
            <p>Progression non communiquée.</p>
          )}
          {r.error && <p role="alert">{r.error}</p>}
          <button
            onClick={() =>
              void perform(async () =>
                setLogs(await api(`${prefix}/runs/${r.id}/logs`)),
              )
            }
          >
            Voir les journaux
          </button>
          <button
            disabled={["completed", "failed", "cancelled"].includes(r.status)}
            onClick={() => {
              if (
                window.confirm("Demander l’interruption de cet entraînement ?")
              )
                void perform(async () => {
                  await api(`${prefix}/runs/${r.id}/cancel`, "POST");
                  await refresh();
                });
            }}
          >
            Interrompre proprement
          </button>
          {r.status === "interrupted" && (
            <button
              disabled={!capability.training}
              onClick={() => {
                if (
                  window.confirm(
                    "Reprendre depuis le dernier checkpoint vérifié ? Le GPU peut être facturé.",
                  )
                )
                  void perform(async () => {
                    await api(`${prefix}/runs/${r.id}/resume`, "POST", {
                      confirmed: true,
                    });
                    await refresh();
                  });
              }}
            >
              Reprendre depuis le checkpoint
            </button>
          )}
          {!!r.result && (
            <pre>
              {typeof r.result === "string"
                ? r.result
                : JSON.stringify(r.result, null, 2)}
            </pre>
          )}
        </article>
      ))}
      {logs !== null && (
        <details open className="training-card">
          <summary>Journal de la tâche</summary>
          <pre>{JSON.stringify(logs, null, 2)}</pre>
        </details>
      )}
    </>
  );
}
function Models({
  engine,
  capability,
  registry,
  datasets,
  runs,
  perform,
  refresh,
}: {
  engine: Engine;
  capability: Capability;
  registry: Registry;
  datasets: Dataset[];
  runs: Run[];
  perform: Perform;
  refresh: () => Promise<void>;
}) {
  const [dataset, setDataset] = useState(""),
    [name, setName] = useState(""),
    [run, setRun] = useState(""),
    [previewVersion, setPreviewVersion] = useState("");
  const action = async (v: string, a: string) => {
    await api(
      `${prefix}/models/${engine}/${v}/${a}`,
      "POST",
      a === "test" ? undefined : { confirmed: true },
    );
    await refresh();
  };
  return (
    <>
      <section className="training-card">
        <h3>Version utilisée en production</h3>
        <p>
          {registry.versions.find(
            (v) => v.id === registry.deployment.version_id,
          )?.name || registry.base_status}
        </p>
        <p>Enregistrer une version ne la met pas en production.</p>
      </section>
      <form
        className="training-card training-fields"
        onSubmit={(e) => {
          e.preventDefault();
          void perform(async () => {
            await api(`${prefix}/models/${engine}/versions`, "POST", {
              name,
              dataset_id: dataset,
              ...(run ? { run_id: run } : {}),
            });
            await refresh();
          }, "Version enregistrée dans le registre.");
        }}
      >
        <h3>
          {engine === "qwen" && !run
            ? "Enregistrer une version du référentiel"
            : "Enregistrer le modèle entraîné"}
        </h3>
        <label>
          Nom de la version
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
          />
        </label>
        <DatasetSelect
          datasets={datasets}
          value={dataset}
          onChange={(id) => {
            setDataset(id);
            setRun("");
          }}
        />
        <label>
          Entraînement terminé
          <select
            aria-label="Entraînement terminé"
            value={run}
            onChange={(e) => setRun(e.target.value)}
          >
            <option value="">
              {engine === "qwen"
                ? "Référentiel uniquement — aucun poids modifié"
                : "Choisir un entraînement"}
            </option>
            {runs
              .filter(
                (r) => r.status === "completed" && r.dataset_id === dataset,
              )
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id} · {r.created}
                </option>
              ))}
          </select>
        </label>
        {engine === "qwen" && !run && (
          <p>
            Cette version mémorise les conventions du lot d’entraînement. Elle
            ne constitue pas un fine-tuning.
          </p>
        )}
        <button
          className="primary"
          disabled={
            !dataset ||
            !name.trim() ||
            (run
              ? !capability.register_weights
              : !capability.reference_versions)
          }
        >
          {run || engine !== "qwen"
            ? "Enregistrer le modèle entraîné"
            : "Enregistrer le référentiel"}
        </button>
      </form>
      <h3>Historique des versions</h3>
      {!registry.versions.length && (
        <p>Aucune version enregistrée pour ce moteur.</p>
      )}
      {registry.versions.map((v) => (
        <article key={v.id} className="training-card">
          <div className="training-engine-title">
            <h4>{v.name}</h4>
            <span className="training-badge">
              {statusNames[v.status] || v.status}
            </span>
          </div>
          <p>
            {v.method === "reference"
              ? "Référentiel, sans modification des poids"
              : engine === "qwen"
                ? "Adaptateur LoRA, poids de base inchangés"
                : "Poids entraînés"}{" "}
            · {v.created} · {v.author}
          </p>
          <p>
            Dataset :{" "}
            {datasets.find((d) => d.id === v.dataset_id)?.name || v.dataset_id}{" "}
            · v{datasets.find((d) => d.id === v.dataset_id)?.version || "?"}
          </p>
          <div className="training-toolbar">
            {engine === "qwen" && v.method === "reference" && (
              <button
                onClick={() =>
                  setPreviewVersion(previewVersion === v.id ? "" : v.id)
                }
                aria-expanded={previewVersion === v.id}
              >
                Comparer Qwen sur un plan
              </button>
            )}
            <button
              disabled={v.method !== "reference" && !capability.evaluation}
              onClick={() =>
                void perform(
                  () => action(v.id, "test"),
                  "Évaluation enregistrée.",
                )
              }
            >
              {v.method === "reference"
                ? "Tester le référentiel"
                : "Tester le modèle"}
            </button>
            <button
              disabled={
                !capability.evaluation ||
                v.evaluation?.publication_eligible !== true ||
                v.status !== "candidate"
              }
              onClick={() => {
                if (
                  window.confirm(
                    "Approuver cette version après comparaison des résultats ?",
                  )
                )
                  void perform(() => action(v.id, "approve"));
              }}
            >
              Approuver le modèle
            </button>
            <button
              disabled={!capability.deployment || v.status !== "approved"}
              onClick={() => {
                if (
                  window.confirm(
                    "Mettre cette version en production pour les nouvelles analyses ?",
                  )
                )
                  void perform(() => action(v.id, "publish"));
              }}
            >
              Mettre en production
            </button>
            <button
              disabled={
                !capability.deployment ||
                registry.deployment.previous_id !== v.id
              }
              onClick={() => {
                if (
                  window.confirm(
                    "Revenir à cette version précédente pour les nouvelles analyses ?",
                  )
                )
                  void perform(() => action(v.id, "rollback"));
              }}
            >
              Revenir à la version précédente
            </button>
          </div>
          {!capability.deployment && (
            <p className="training-hint">
              Publication indisponible : l’activation des versions sur le GPU
              n’est pas encore raccordée.
            </p>
          )}
          {v.evaluation && (
            <>
              <h4>Résultats de l’évaluation</h4>
              {v.evaluation.scope === "reference_lookup_only" && (
                <p>
                  Test de recherche dans le référentiel uniquement. L’inférence
                  Qwen n’a pas été évaluée.
                </p>
              )}
              <pre>{JSON.stringify(v.evaluation, null, 2)}</pre>
            </>
          )}
          {previewVersion === v.id && (
            <QwenPreview key={v.id} version={v.id} perform={perform} />
          )}
          <details>
            <summary>Artefacts, paramètres et métriques</summary>
            <pre>{JSON.stringify(v.manifest, null, 2)}</pre>
          </details>
        </article>
      ))}
    </>
  );
}
