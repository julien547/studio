// Geometry is stored in the full upright source frame; viewport transforms never
// enter saved coordinates. Paper size controls printed symbols, not building scale.
export function sourcePoint(point, frame) {
  return [point.x * frame.width, point.y * frame.height];
}

export function moveWall(wall, dx, dy, frame) {
  const x = Math.max(
    -Math.min(wall.a[0], wall.b[0]),
    Math.min(dx * frame.width, frame.width - Math.max(wall.a[0], wall.b[0])),
  );
  const y = Math.max(
    -Math.min(wall.a[1], wall.b[1]),
    Math.min(dy * frame.height, frame.height - Math.max(wall.a[1], wall.b[1])),
  );
  return {
    ...wall,
    a: [wall.a[0] + x, wall.a[1] + y],
    b: [wall.b[0] + x, wall.b[1] + y],
    status: "pending",
  };
}

export function solidIntervals(openings) {
  const intervals = [];
  let cursor = 0;
  for (const opening of [...openings].sort((a, b) => a.start - b.start)) {
    const start = Math.max(0, Math.min(1, opening.start));
    const end = Math.max(start, Math.min(1, opening.end));
    if (start > cursor) intervals.push([cursor, start]);
    cursor = Math.max(cursor, end);
  }
  if (cursor < 1) intervals.push([cursor, 1]);
  return intervals;
}

export function alongWall(wall, fraction) {
  return [
    wall.a[0] + (wall.b[0] - wall.a[0]) * fraction,
    wall.a[1] + (wall.b[1] - wall.a[1]) * fraction,
  ];
}

// Restoring geometry is not permission to roll back the server-owned analysis
// ledger. Keep removed observations as rejected IDs so rerunning a recognizer
// cannot silently reinsert them. Source frames are immutable during this edit.
export function restoreStructureHistory(current, historical) {
  const key = (page) => `${page.source_document_id}:${page.source_page}`;
  const past = new Map(
    (historical.structure_pages || []).map((page) => [key(page), page]),
  );
  const currentPages = current.structure_pages || [];
  const result = currentPages.map((page) => {
    const previous = past.get(key(page));
    past.delete(key(page));
    if (
      previous &&
      ["source_sha256", "width", "height", "unit"].some(
        (field) => page[field] !== previous[field],
      )
    ) {
      throw Error(
        "Impossible de restaurer les murs : le repère de cette révision diffère de la page actuelle.",
      );
    }
    const restored = (previous?.walls || []).map((wall) => ({
      ...structuredClone(wall),
      status: wall.status === "rejected" ? "rejected" : "pending",
    }));
    const restoredIds = new Set(restored.map((wall) => wall.id));
    return {
      ...structuredClone(page),
      walls: [
        ...restored,
        ...page.walls
          .filter((wall) => !restoredIds.has(wall.id))
          .map((wall) => ({ ...structuredClone(wall), status: "rejected" })),
      ],
    };
  });
  for (const previous of past.values()) {
    result.push({
      ...structuredClone(previous),
      analysis_ids: [],
      walls: previous.walls.map((wall) => ({
        ...structuredClone(wall),
        status: wall.status === "rejected" ? "rejected" : "pending",
      })),
    });
  }
  return result;
}
