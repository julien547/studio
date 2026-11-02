import React, { useEffect, useState } from "react";
import type { StructurePage, StructureWall } from "./types";

export function StructurePanel({
  frame,
  selected,
  onSelect,
  onChange,
  onRemove,
}: {
  frame?: StructurePage;
  selected: string;
  onSelect: (id: string) => void;
  onChange: (id: string, patch: Partial<StructureWall>) => void;
  onRemove: () => void;
}) {
  const wall = frame?.walls.find((w) => w.id === selected);
  const [coordinates, setCoordinates] = useState(["", "", "", ""]);
  const [error, setError] = useState("");
  useEffect(() => {
    setCoordinates(
      wall ? [...wall.a, ...wall.b].map(String) : ["", "", "", ""],
    );
    setError("");
  }, [wall?.id, wall?.a[0], wall?.a[1], wall?.b[0], wall?.b[1]]);
  function commit() {
    if (!frame || !wall) return;
    const values = coordinates.map((v) => (v.trim() ? Number(v) : NaN));
    if (
      values.some(
        (v, i) =>
          !Number.isFinite(v) ||
          v < 0 ||
          v > (i % 2 ? frame.height : frame.width),
      ) ||
      Math.hypot(values[2] - values[0], values[3] - values[1]) < 0.01
    ) {
      setError("Saisissez deux points distincts à l’intérieur de la page.");
      return;
    }
    setError("");
    onChange(wall.id, {
      a: [values[0], values[1]],
      b: [values[2], values[3]],
      status: "pending",
    });
  }
  return (
    <section className="structure-panel">
      <h2>Murs du plan commun</h2>
      <p>
        {frame?.walls.filter((w) => w.status !== "rejected").length || 0} murs ·
        coordonnées de la page source
      </p>
      <label>
        Choisir un mur
        <select
          aria-label="Choisir un mur"
          value={wall?.id || ""}
          onChange={(e) => onSelect(e.target.value)}
        >
          <option value="">Sélectionner sur le plan</option>
          {frame?.walls.map((w, i) => (
            <option value={w.id} key={w.id}>
              Mur {i + 1}
              {w.status === "rejected" ? " · rejeté" : ""}
            </option>
          ))}
        </select>
      </label>
      {wall && (
        <>
          <p>
            {wall.method === "manual"
              ? "Tracé manuel"
              : wall.confidence > 0
                ? `Proposition · confiance ${Math.round(wall.confidence * 100)} %`
                : "Proposition · confiance non renseignée"}{" "}
            · {frame?.unit}
          </p>
          <div className="form-pair">
            {["Départ X", "Départ Y", "Arrivée X", "Arrivée Y"].map(
              (label, i) => (
                <label key={label}>
                  {label}
                  <input
                    aria-label={label}
                    type="number"
                    step="any"
                    value={coordinates[i]}
                    onChange={(e) =>
                      setCoordinates((v) =>
                        v.map((x, j) => (j === i ? e.target.value : x)),
                      )
                    }
                  />
                </label>
              ),
            )}
          </div>
          {error && <p role="alert">{error}</p>}
          <button onClick={commit}>Appliquer les coordonnées</button>
          <label>
            Épaisseur dans la source ({frame?.unit})
            <input
              key={wall.id + ":" + wall.thickness}
              aria-label="Épaisseur du mur"
              type="number"
              min={0.01}
              step="any"
              placeholder="Inconnue"
              defaultValue={wall.thickness ?? ""}
              onBlur={(e) => {
                const value =
                  e.target.value === "" ? null : Number(e.target.value);
                if (
                  value !== null &&
                  (!Number.isFinite(value) ||
                    value <= 0 ||
                    value > Math.max(frame!.width, frame!.height))
                ) {
                  setError("Épaisseur invalide.");
                  return;
                }
                onChange(wall.id, { thickness: value, status: "pending" });
              }}
            />
          </label>
          <small>
            Ce champ n’est pas une mesure réelle du bâtiment. Les cotes
            nécessitent un calibrage.
          </small>
          <label>
            État
            <select
              aria-label="État du mur"
              value={wall.status}
              onChange={(e) =>
                onChange(wall.id, {
                  status: e.target.value as StructureWall["status"],
                })
              }
            >
              <option value="pending">À vérifier</option>
              <option value="approved">Vérifié par le dessinateur</option>
              <option value="rejected">Rejeté</option>
            </select>
          </label>
          <button onClick={onRemove}>Supprimer ce mur</button>
        </>
      )}
      {frame?.warnings.map((warning, i) => (
        <p key={i} className="structure-warning">
          {warning}
        </p>
      ))}
    </section>
  );
}
