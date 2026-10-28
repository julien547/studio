import { useCallback, useEffect, useRef, useState } from "react";
import { api, url } from "../api";
import { prefix, statusNames, message, type Perform } from "./types";

type Output = {
  id: string;
  status: string;
  error: string | null;
  result: null | {
    observations: { text?: string; interpretation?: string }[];
    raw?: unknown;
  };
  context_sha256: string;
};
type Comparison = {
  id: string;
  created: string;
  complete: boolean;
  expected: string;
  source: {
    project_id: string;
    document_id: string;
    name: string;
    page: number;
  };
  baseline: Output;
  candidate: Output;
  review: null | { verdict: string; notes: string };
  reviewer: string | null;
};
const verdicts: Record<string, string> = {
  candidate_better: "Avec le référentiel : meilleur",
  same: "Résultats équivalents",
  baseline_better: "Sans le référentiel : meilleur",
  inconclusive: "Comparaison non concluante",
};

export function QwenPreview({
  version,
  perform,
}: {
  version: string;
  perform: Perform;
}) {
  const [options, setOptions] = useState<
    { id: string; name: string; page: number; expected: string }[]
  >([]);
  const [example, setExample] = useState("");
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [error, setError] = useState("");
  const request = useRef<{ example: string; key: string } | null>(null);
  const mounted = useRef(true);
  const base = `${prefix}/models/qwen/${version}`;
  const refresh = useCallback(async () => {
    const rows = await api<Comparison[]>(base + "/previews");
    if (mounted.current) {
      setComparisons(rows);
      setError("");
    }
  }, [base]);
  useEffect(() => {
    mounted.current = true;
    void Promise.all([
      api<{ examples: typeof options }>(base + "/preview-options"),
      api<Comparison[]>(base + "/previews"),
    ])
      .then(([data, rows]) => {
        if (mounted.current) {
          setOptions(data.examples);
          setComparisons(rows);
        }
      })
      .catch((e) => {
        if (mounted.current) setError(message(e));
      });
    const timer = setInterval(() => {
      void refresh().catch((e) => {
        if (mounted.current) setError(message(e));
      });
    }, 5000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [base, refresh]);
  return (
    <section
      className="training-qwen-preview"
      aria-label="Comparaison Qwen sur plan"
    >
      <h4>Comparer sur un plan réservé au test</h4>
      <p>
        Deux lectures de la même page : l’une sans conventions, l’autre avec ce
        référentiel. La correction attendue reste séparée des données envoyées à
        Qwen. Vos poids et le modèle de production restent inchangés.
      </p>
      {error && (
        <p role="alert" className="training-error">
          {error}
        </p>
      )}
      <form
        className="training-fields"
        onSubmit={(e) => {
          e.preventDefault();
          if (
            !example ||
            !window.confirm(
              "Lancer deux analyses Qwen sur le GPU ? Le démarrage et les inférences peuvent être facturés.",
            )
          )
            return;
          void perform(async () => {
            if (request.current?.example !== example)
              request.current = { example, key: crypto.randomUUID() };
            await api(base + "/previews", "POST", {
              example_id: example,
              confirmed: true,
              request_key: request.current!.key,
            });
            await refresh();
            request.current = null;
          }, "Comparaison Qwen demandée.");
        }}
      >
        <label>
          Exemple réservé au test
          <select
            aria-label="Exemple réservé au test"
            value={example}
            onChange={(e) => setExample(e.target.value)}
          >
            <option value="">Choisir un exemple</option>
            {options.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} · page {e.page} · {e.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {!options.length && (
          <p>
            Aucun exemple de test disponible. Le dataset doit contenir au moins
            trois groupes indépendants pour séparer entraînement, validation et
            test.
          </p>
        )}
        <button disabled={!example}>Lancer les deux analyses Qwen</button>
      </form>
      <p className="training-hint">
        Les résultats restent des propositions à vérifier. Cette comparaison
        visuelle ne certifie pas la stabilité des poids du serveur entre les
        deux appels et ne permet pas de publier automatiquement une version.
      </p>
      {comparisons.map((c) => (
        <article className="training-card" key={c.id}>
          <h4>Comparaison {c.id.slice(0, 8)}</h4>
          <p>
            {c.created} · {c.source.name} · page {c.source.page}
          </p>
          <details>
            <summary>Voir la page source</summary>
            <img
              className="training-preview-image"
              alt="Page source comparée"
              src={url(
                `/projects/${c.source.project_id}/documents/${c.source.document_id}/pages/${c.source.page}`,
              )}
            />
          </details>
          <p>
            <strong>Interprétation attendue, conservée sur OVH :</strong>{" "}
            {c.expected}
          </p>
          <div className="training-comparison-columns">
            {(
              [
                ["baseline", "Sans référentiel"],
                ["candidate", "Avec ce référentiel"],
              ] as const
            ).map(([key, title]) => (
              <section key={key} aria-label={title}>
                <h5>{title}</h5>
                <p>{statusNames[c[key].status] || c[key].status}</p>
                {c[key].error && <p role="alert">{c[key].error}</p>}
                {c[key].result ? (
                  <>
                    {c[key].result!.observations.map((o, i) => (
                      <div key={i}>
                        <p>{o.text || "Observation sans texte"}</p>
                        {o.interpretation && (
                          <p>
                            <strong>Interprétation proposée :</strong>{" "}
                            {o.interpretation}
                          </p>
                        )}
                      </div>
                    ))}
                    <details>
                      <summary>Résultat brut et traçabilité</summary>
                      <pre>
                        {JSON.stringify(
                          {
                            context_sha256: c[key].context_sha256,
                            result: c[key].result,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  </>
                ) : (
                  <p>Aucun résultat reçu.</p>
                )}
              </section>
            ))}
          </div>
          {c.review && (
            <p>
              <strong>{verdicts[c.review.verdict]}</strong> — {c.review.notes} ·{" "}
              {c.reviewer}
            </p>
          )}
          {c.complete && (
            <Review
              comparison={c}
              base={base}
              perform={perform}
              refresh={refresh}
            />
          )}
        </article>
      ))}
    </section>
  );
}
function Review({
  comparison,
  base,
  perform,
  refresh,
}: {
  comparison: Comparison;
  base: string;
  perform: Perform;
  refresh: () => Promise<void>;
}) {
  const [verdict, setVerdict] = useState(
    comparison.review?.verdict || "inconclusive",
  );
  const [notes, setNotes] = useState(comparison.review?.notes || "");
  return (
    <form
      className="training-fields"
      onSubmit={(e) => {
        e.preventDefault();
        void perform(async () => {
          await api(`${base}/previews/${comparison.id}/review`, "POST", {
            verdict,
            notes,
          });
          await refresh();
        }, "Avis de comparaison enregistré, sans mise en production.");
      }}
    >
      <label>
        Avis de comparaison
        <select
          aria-label="Avis de comparaison"
          value={verdict}
          onChange={(e) => setVerdict(e.target.value)}
        >
          {Object.entries(verdicts).map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Motif de l’avis
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          maxLength={2000}
          required
        />
      </label>
      <button>Enregistrer l’avis de comparaison</button>
    </form>
  );
}
