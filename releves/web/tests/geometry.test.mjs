import test from "node:test";
import assert from "node:assert/strict";
import { projectPoint, clearReview } from "../src/geometry.js";
test("perspective projection uses homogeneous division", () => {
  assert.deepEqual(
    projectPoint(
      [
        [1, 0, 0],
        [0, 1, 0],
        [1, 0, 1]
      ],
      { x: 1, y: 1 }
    ),
    { x: 0.5, y: 0.5 }
  );
  assert.equal(
    projectPoint(
      [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 0]
      ],
      { x: 1, y: 1 }
    ),
    null
  );
});
test("manual corrections invalidate the relevant checks", () => {
  const a = {
    status: "confirmed",
    target: null,
    text: "DM",
    review: {
      equipment: true,
      asset: true,
      floor: true,
      position: true,
      orientation: true,
      size: true
    }
  };
  const edited = clearReview(a, { target: { x: 0.4, y: 0.5 } });
  assert.equal(edited.review.position, false);
  assert.equal(edited.review.equipment, true);
  assert.equal(edited.status, "review");
  assert.equal(a.review.position, true);
});
test("each human checkbox can be set explicitly", () => {
  const a = { status: "review", review: { position: false } };
  assert.equal(clearReview(a, { review: { position: true } }).review.position, true);
});
