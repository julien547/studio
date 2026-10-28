// Page coordinates are immutable normalized upright-source coordinates.
export const wholePage = { x: 0, y: 0, w: 1, h: 1 };
export function pageToView(p, b = wholePage, rotation = 0) {
  const x = (p.x - b.x) / b.w,
    y = (p.y - b.y) / b.h;
  return rotation === 90
    ? { x: 1 - y, y: x }
    : rotation === 180
      ? { x: 1 - x, y: 1 - y }
      : rotation === 270
        ? { x: y, y: 1 - x }
        : { x, y };
}
export function viewToPage(p, b = wholePage, rotation = 0) {
  const q =
    rotation === 90
      ? { x: p.y, y: 1 - p.x }
      : rotation === 180
        ? { x: 1 - p.x, y: 1 - p.y }
        : rotation === 270
          ? { x: 1 - p.y, y: p.x }
          : p;
  return { x: b.x + q.x * b.w, y: b.y + q.y * b.h };
}
export function rectangle(a, b) {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  };
}
export function contains(b, p) {
  return p.x >= b.x && p.y >= b.y && p.x <= b.x + b.w && p.y <= b.y + b.h;
}
export function clampPoint(p) {
  return { x: Math.max(0, Math.min(1, p.x)), y: Math.max(0, Math.min(1, p.y)) };
}
export function moveBox(box, dx, dy) {
  return {
    ...box,
    x: Math.max(0, Math.min(1 - box.w, box.x + dx)),
    y: Math.max(0, Math.min(1 - box.h, box.y + dy)),
  };
}
