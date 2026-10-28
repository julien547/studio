import { useEffect, useState } from "react";
import { api } from "./api";
export const gpuLabels: Record<string, string> = {
  not_configured: "GPU non configuré",
  stopped: "GPU arrêté",
  starting: "Démarrage du GPU",
  stopping: "Arrêt du GPU",
  restoring: "Restauration des environnements",
  warming: "Chargement des trois moteurs",
  ready: "GPU prêt",
  busy: "Analyse GPU en cours",
  provider_error: "RunPod temporairement indisponible",
  configuration_error: "Configuration à vérifier",
  unavailable: "Connexion GPU indisponible",
  available: "GPU disponible",
};
type Status = {
  status: string;
  configured: boolean;
  managed: boolean;
  pod_name: string;
  pod_id: string | null;
  provider_status: string | null;
  engines: Record<string, boolean>;
  observed_at: number | null;
  last_activity: number;
  stale: boolean;
  automatic_start: boolean;
  automatic_stop: boolean;
  idle_timeout_seconds: number;
  pending_tasks: number;
  request: string | null;
  error: string | null;
};
type Event = {
  id: number;
  created: string;
  actor: string;
  action: string;
  outcome: string;
  detail: string;
};
export function GpuPanel({
  administrator,
  onStatus,
}: {
  administrator: boolean;
  onStatus: (s: string) => void;
}) {
  const [status, setStatus] = useState<Status | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [expanded, setExpanded] = useState(false),
    [error, setError] = useState(""),
    [working, setWorking] = useState(false);
  async function refresh() {
    const s = await api<Status>("/projects/gpu");
    setStatus(s);
    onStatus(s.status);
    if (administrator && expanded) setEvents(await api("/projects/gpu/events"));
  }
  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const s = await api<Status>("/projects/gpu");
        if (live) {
          setStatus(s);
          onStatus(s.status);
        }
      } catch {
        if (live)
          setError("État GPU indisponible ; l’éditeur reste accessible.");
      }
    };
    void poll();
    const id = setInterval(poll, 10000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  useEffect(() => {
    if (administrator && expanded)
      void api<Event[]>("/projects/gpu/events")
        .then(setEvents)
        .catch(() => setError("Journal indisponible"));
  }, [expanded, status?.observed_at]);
  async function action(action: "start" | "stop") {
    setWorking(true);
    setError("");
    try {
      setStatus(await api("/projects/gpu/action", "POST", { action }));
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorking(false);
    }
  }
  if (!status) return error ? <p role="alert">{error}</p> : null;
  const transitioning =
    !!status.request || ["starting", "stopping"].includes(status.status);
  return (
    <section className="gpu-panel" aria-label="Gestion du serveur GPU">
      <div className="gpu-panel-heading">
        <div>
          <strong>DOEMO-STUDIO-IA</strong>
          <span className={"gpu-badge gpu-" + status.status}>
            {gpuLabels[status.status] || status.status}
          </span>
          {status.stale && status.configured && (
            <small>État à actualiser par le contrôleur</small>
          )}
        </div>
        <div>
          {administrator && (
            <>
              <button
                disabled={
                  !status.configured ||
                  transitioning ||
                  working ||
                  ["ready", "busy"].includes(status.status)
                }
                onClick={() => void action("start")}
              >
                Démarrer le GPU
              </button>
              <button
                disabled={
                  !status.configured ||
                  transitioning ||
                  working ||
                  status.pending_tasks > 0 ||
                  status.status === "stopped"
                }
                onClick={() => void action("stop")}
              >
                Arrêter le GPU
              </button>
            </>
          )}
          <button
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Masquer" : "Détails GPU"}
          </button>
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {status.error && <p>{status.error}</p>}
      {expanded && (
        <div className="gpu-details">
          <div>
            <span>Pod : {status.pod_id || "À renseigner sur OVH"}</span>
            <span>{status.pending_tasks} tâche(s) en cours ou en attente</span>
            <span>
              Démarrage automatique :{" "}
              {status.automatic_start ? "activé" : "désactivé"}
            </span>
            <span>
              Arrêt après 30 min d’inactivité :{" "}
              {status.automatic_stop ? "activé" : "désactivé"}
            </span>
            {status.request && (
              <span>
                Commande demandée :{" "}
                {status.request === "start" ? "démarrer" : "arrêter"}
              </span>
            )}
          </div>
          <div className="engine-status">
            {[
              ["qwen", "Qwen3.5-9B"],
              ["paddleocr", "PaddleOCR"],
              ["rtmdet", "RTMDet"],
            ].map(([key, label]) => (
              <span key={key}>
                ● {label} · {status.engines[key] ? "prêt" : "en attente"}
              </span>
            ))}
          </div>
          {!status.configured && (
            <p>
              La gestion automatique nécessite la configuration du backend OVH.
              Le travail sur les relevés reste disponible.
            </p>
          )}
          {administrator && (
            <details>
              <summary>Journal des actions</summary>
              <ol className="gpu-events">
                {events.map((e) => (
                  <li key={e.id}>
                    <time>{e.created} UTC</time> · {e.actor} · {e.action} ·{" "}
                    {e.outcome}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
