export function projectPoint(matrix, point) {
  if (!matrix || !point) return null;
  const [x, y, z] = matrix.map((row) => row[0] * point.x + row[1] * point.y + row[2]);
  if (!Number.isFinite(z) || Math.abs(z) < 1e-9) return null;
  const result = { x: x / z, y: y / z };
  return Number.isFinite(result.x) && Number.isFinite(result.y) ? result : null;
}
export function clearReview(annotation, changes) {
  const review = { ...(changes.review || annotation.review) };
  const fields = {
    equipment: ["text", "equipment_type"],
    asset: ["asset_id"],
    floor: ["floor_id"],
    position: ["anchor", "target"],
    orientation: ["rotation_deg"],
    size: ["size_mm"]
  };
  for (const [criterion, keys] of Object.entries(fields))
    if (
      keys.some(
        (key) => key in changes && JSON.stringify(changes[key]) !== JSON.stringify(annotation[key])
      )
    )
      review[criterion] = false;
  const edited = { ...annotation, ...changes, review };
  if (annotation.status === "confirmed" && Object.values(review).some((x) => !x))
    edited.status = "review";
  return edited;
}
