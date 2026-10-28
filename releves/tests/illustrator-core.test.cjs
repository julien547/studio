const test = require("node:test"),
  assert = require("node:assert/strict"),
  crypto = require("node:crypto");
const core = require("../illustrator/doemo-core.js");
test("SHA-256 matches FIPS and binary files", () => {
  for (const value of ["", "abc", "écriture", "x".repeat(10000)]) {
    const bytes = Buffer.from(value, "utf8");
    assert.equal(
      core.sha256(bytes.toString("latin1")),
      crypto.createHash("sha256").update(bytes).digest("hex")
    );
  }
});
test("strict JSON accepts real data without eval", () => {
  const data = { annotation: 'CO₂ "5 kg"', nested: [true, null, 1.25, -9e2] };
  assert.deepEqual(core.parse(core.stringify(data)), data);
  for (const bad of [
    '{"a":1,"a":2}',
    '{"__proto__":1}',
    "[1,]",
    '{"a":Infinity}',
    "1 trailing",
    "(()=>1)()",
    '{"a":01}'
  ])
    assert.throws(() => core.parse(bad));
});
test("coordinates account for Illustrator artboard offset and upward Y", () =>
  assert.deepEqual(core.point([200, 900, 700, 400], 100, 150), [300, 750]));
test("unsafe library paths cannot escape the selected folder", () => {
  for (const path of ["../x.ai", "C:/x.ai", "/x.ai", "a\\b.ai", "a//b.ai"])
    assert.throws(() => core.safePath(path));
  assert.equal(core.safePath("uuid/component.ai"), "uuid/component.ai");
});
test("reruns identify unchanged, corrected, manually moved and removed objects", () => {
  const p = {
    placement_id: "p1",
    asset_id: "a",
    floor_id: "f",
    x: 10,
    y: 20,
    rotation_deg: 0,
    size_mm: 7
  };
  assert.equal(core.diff([p], {})[0].action, "add");
  const current = { p1: { signature: core.signature(p), manually_changed: false } };
  assert.equal(core.diff([p], current)[0].action, "unchanged");
  assert.equal(core.diff([{ ...p, x: 40 }], current)[0].action, "update");
  current.p1.manually_changed = true;
  assert.equal(core.diff([p], current)[0].action, "conflict");
  assert.equal(core.diff([], current)[0].action, "removed_preserve");
});
test("native import refuses incomplete reviews, missing resources and off-artboard coordinates", () => {
  const data = {
    schema_version: "doemo.placements/1",
    project_id: "test",
    coordinate_system: {
      unit: "pt",
      origin: "artboard_top_left",
      x_axis: "right",
      y_axis: "down",
      rotation_rule: "clockwise_degrees",
      size_rule: "longest_visible_edge_mm_before_rotation"
    },
    target: {
      sha256: "a".repeat(64),
      floors: [{ id: "rdc", confirmed: true, artboard_index: 0, target_page: 1 }],
      pages: [{ pdf_size_pt: [500, 400] }]
    },
    assets: [{ asset_id: "asset", sha256: "b".repeat(64), relative_path: "asset/file.ai" }],
    placements: [
      {
        placement_id: "mark",
        validated: true,
        floor_id: "rdc",
        asset_id: "asset",
        review: {
          equipment: true,
          asset: true,
          floor: true,
          position: true,
          orientation: true,
          size: true
        },
        x: 100,
        y: 200,
        rotation_deg: 0,
        size_mm: 7
      }
    ]
  };
  assert.ok(core.validate(data));
  data.placements[0].review.position = false;
  assert.throws(() => core.validate(data));
  data.placements[0].review.position = true;
  data.placements[0].x = 600;
  assert.throws(() => core.validate(data));
  data.placements[0].x = 100;
  data.assets = [];
  assert.throws(() => core.validate(data));
});
