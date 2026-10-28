import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { Project, State } from "./types";

export function useEditor() {
  const [project, setProject] = useState<Project | null>(null);
  const [dirty, setDirty] = useState(false),
    [saving, setSaving] = useState(false),
    [error, setError] = useState("");
  const current = useRef<Project | null>(null),
    generation = useRef(0),
    saved = useRef(0);
  const undoStack = useRef<State[]>([]),
    redoStack = useRef<State[]>([]);
  const inFlight = useRef<Promise<void> | null>(null),
    blocked = useRef(false);
  function install(p: Project) {
    current.current = p;
    setProject(p);
    generation.current = 0;
    saved.current = 0;
    setDirty(false);
    setError("");
    blocked.current = false;
    undoStack.current = [];
    redoStack.current = [];
  }
  function update(state: State) {
    if (!current.current) return;
    generation.current++;
    current.current = { ...current.current, state };
    setProject(current.current);
    setDirty(true);
  }
  function edit(fn: (s: State) => State) {
    if (!current.current) return;
    if (!blocked.current) setError("");
    undoStack.current.push(structuredClone(current.current.state));
    if (undoStack.current.length > 100) undoStack.current.shift();
    redoStack.current = [];
    const next = fn(structuredClone(current.current.state));
    next.workflow = "corrected";
    update(next);
  }
  function undo() {
    if (!current.current || !undoStack.current.length) return;
    redoStack.current.push(structuredClone(current.current.state));
    const s = undoStack.current.pop()!;
    s.revision = current.current.state.revision;
    s.workflow = "corrected";
    update(s);
  }
  function redo() {
    if (!current.current || !redoStack.current.length) return;
    undoStack.current.push(structuredClone(current.current.state));
    const s = redoStack.current.pop()!;
    s.revision = current.current.state.revision;
    s.workflow = "corrected";
    update(s);
  }
  async function save() {
    while (inFlight.current) await inFlight.current;
    if (!current.current || generation.current === saved.current) return;
    if (blocked.current)
      throw Error(
        "Sauvegarde suspendue : exportez vos corrections locales puis rechargez le projet.",
      );
    const snapshot = current.current,
      version = generation.current;
    setSaving(true);
    const pending = (async () => {
      try {
        const result = await api<Project>(
          `/projects/${snapshot.id}/state`,
          "PUT",
          snapshot.state,
        );
        if (current.current?.id !== snapshot.id) return;
        current.current =
          generation.current === version
            ? result
            : {
                ...current.current,
                state: {
                  ...current.current.state,
                  revision: result.state.revision,
                },
              };
        saved.current = version;
        setProject(current.current);
        setDirty(generation.current !== version);
        setError("");
      } catch (e) {
        blocked.current = e instanceof ApiError && e.status === 409;
        setError(String(e));
        throw e;
      } finally {
        setSaving(false);
        inFlight.current = null;
      }
    })();
    inFlight.current = pending;
    await pending;
    // Flush any edits performed while the request was pending.
    if (generation.current !== saved.current) await save();
  }
  useEffect(() => {
    if (!dirty || blocked.current) return;
    const t = setTimeout(() => {
      void save().catch(() => {});
    }, 1000);
    return () => clearTimeout(t);
  }, [project, dirty]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (generation.current !== saved.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  return {
    project,
    install,
    edit,
    undo,
    redo,
    save,
    dirty,
    saving,
    error,
    canUndo: undoStack.current.length > 0,
    canRedo: redoStack.current.length > 0,
  };
}
