import test from "node:test";
import assert from "node:assert/strict";
import {
  pageToView,
  viewToPage,
  moveBox,
  rectangle,
} from "../src/editorGeometry.js";
for (const rotation of [0, 90, 180, 270])
  test(`source coordinates survive crop, rotation ${rotation} and repeated zoom round trips`, () => {
    const b = { x: 0.12, y: 0.08, w: 0.32, h: 0.47 };
    let p = { x: 0.2, y: 0.3 };
    for (let n = 0; n < 1000; n++) {
      const view = pageToView(p, b, rotation);
      const screen = { x: view.x * 2048 * 2.5, y: view.y * 1447 * 2.5 };
      p = viewToPage(
        { x: screen.x / (2048 * 2.5), y: screen.y / (1447 * 2.5) },
        b,
        rotation,
      );
    }
    assert.ok(Math.abs(p.x - 0.2) < 1e-12);
    assert.ok(Math.abs(p.y - 0.3) < 1e-12);
  });
test("moving an annotation box preserves its size and stays within the source", () => {
  assert.deepEqual(moveBox({ x: 0.1, y: 0.1, w: 0.2, h: 0.3 }, 2, -2), {
    x: 0.8,
    y: 0,
    w: 0.2,
    h: 0.3,
  });
  assert.deepEqual(rectangle({ x: 0.8, y: 0.7 }, { x: 0.2, y: 0.1 }), {
    x: 0.2,
    y: 0.1,
    w: 0.6000000000000001,
    h: 0.6,
  });
});
