import assert from "node:assert/strict";
import {
  alongWall,
  moveWall,
  solidIntervals,
  sourcePoint,
  restoreStructureHistory,
} from "../src/structureGeometry.js";
import { pageToView, viewToPage } from "../src/editorGeometry.js";

const frame = { width: 1200, height: 800 };
const anchor = { x: 0.25, y: 0.4 };
const native = sourcePoint(anchor, frame);
assert.deepEqual(native, [300, 320]);
for (const rotation of [0, 90, 180, 270]) {
  const region = { x: 0.1, y: 0.2, w: 0.6, h: 0.5 };
  const wallPosition = pageToView(
    { x: native[0] / frame.width, y: native[1] / frame.height },
    region,
    rotation,
  );
  assert.deepEqual(wallPosition, pageToView(anchor, region, rotation));
  const original = viewToPage(wallPosition, region, rotation);
  assert.ok(Math.hypot(original.x - anchor.x, original.y - anchor.y) < 1e-12);
}
const wall = {
  a: [100, 200],
  b: [600, 200],
  status: "approved",
  openings: [{ start: 0.2, end: 0.4, kind: "window" }],
};
const moved = moveWall(wall, 0.9, -0.8, frame);
assert.deepEqual(moved.a, [700, 0]);
assert.deepEqual(moved.b, [1200, 0]);
assert.equal(moved.b[0] - moved.a[0], 500);
assert.equal(moved.status, "pending");
assert.deepEqual(moved.openings, wall.openings);
assert.deepEqual(wall.a, [100, 200]);
assert.deepEqual(solidIntervals(wall.openings), [
  [0, 0.2],
  [0.4, 1],
]);
assert.deepEqual(alongWall(wall, 0.4), [300, 200]);
assert.deepEqual(
  solidIntervals([
    { start: 0.4, end: 0.7 },
    { start: 0.2, end: 0.5 },
  ]),
  [
    [0, 0.2],
    [0.7, 1],
  ],
);
assert.deepEqual(solidIntervals([{ start: 0, end: 1 }]), []);
console.log(
  "Structure geometry: common source frame, crop/rotation, bounded movement and openings passed",
);

const framePage = {
  source_document_id: "source",
  source_page: 1,
  source_sha256: "a".repeat(64),
  width: 1200,
  height: 800,
  unit: "px",
  warnings: [],
};
const correctedWall = { ...wall, id: "recognized", a: [110, 200] };
const newWall = { ...wall, id: "later", status: "approved" };
const currentState = {
  structure_pages: [
    {
      ...framePage,
      analysis_ids: ["job-old", "job-new"],
      walls: [correctedWall, newWall],
    },
  ],
};
const historicalState = {
  structure_pages: [
    {
      ...framePage,
      analysis_ids: ["job-old"],
      walls: [{ ...wall, id: "recognized" }],
    },
  ],
};
const restored = restoreStructureHistory(currentState, historicalState);
assert.deepEqual(restored[0].analysis_ids, ["job-old", "job-new"]);
assert.deepEqual(restored[0].walls[0].a, wall.a);
assert.equal(restored[0].walls[0].status, "pending");
assert.equal(
  restored[0].walls.find((w) => w.id === "later").status,
  "rejected",
);
assert.equal(currentState.structure_pages[0].walls[1].status, "approved");
const beforeStructure = restoreStructureHistory(currentState, {});
assert.equal(beforeStructure[0].walls.length, 2);
assert.ok(beforeStructure[0].walls.every((w) => w.status === "rejected"));
assert.deepEqual(beforeStructure[0].analysis_ids, ["job-old", "job-new"]);
const missingPage = restoreStructureHistory({}, historicalState);
assert.deepEqual(missingPage[0].analysis_ids, []);
assert.equal(missingPage[0].walls[0].status, "pending");
assert.throws(
  () =>
    restoreStructureHistory(currentState, {
      structure_pages: [{ ...historicalState.structure_pages[0], width: 600 }],
    }),
  /repère/,
);
console.log(
  "History restoration: geometry restored, analysis ledger retained, removed walls remain rejected",
);
