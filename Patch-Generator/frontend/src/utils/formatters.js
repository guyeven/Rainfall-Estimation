
export function formatTimestamp(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;
  return date.toLocaleString();
}

export function formatNumber(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  return Number(value).toFixed(decimals);
}

export function formatKm(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return "";
  return `${n.toFixed(1)} km`;
}

export function formatMm(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return "";
  return `${n.toFixed(1)} mm`;
}
