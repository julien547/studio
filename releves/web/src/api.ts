const base = "/api/releves.php?route=";
export const url = (path: string) => base + encodeURIComponent(path);
export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const r = await fetch(url(path), {
    method,
    credentials: "same-origin",
    headers: body && !form ? { "Content-Type": "application/json" } : {},
    body: body ? (form ? body : JSON.stringify(body)) : undefined
  });
  if (!r.ok) {
    let error;
    try {
      error = await r.json();
    } catch {
      error = { detail: `Erreur serveur ${r.status}` };
    }
    throw new Error(
      typeof error.detail === "string" ? error.detail : error.error || `Erreur ${r.status}`
    );
  }
  return r.json();
}
export function download(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
