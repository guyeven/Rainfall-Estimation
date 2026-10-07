export function defaultAttrs() {
  return { area_type: [], rain_type: [], intensity: "", notes: "", approved: false };
}

export function isAttrsValid(attrs) {
  if (!attrs) return false;
  const hasNotes = String(attrs.notes || "").trim().length > 0;
  return (
    (attrs.area_type?.length || 0) > 0 ||
    (attrs.rain_type?.length || 0) > 0 ||
    Boolean(attrs.intensity) ||
    hasNotes
  );
}
