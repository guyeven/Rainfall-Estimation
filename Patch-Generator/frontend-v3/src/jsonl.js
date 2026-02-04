import { API_BASE } from "./apiBase";
// utils/jsonl.js
export function downloadTextFile({ filename, text, mime = "application/x-ndjson" }) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function toNdjsonLines(objs) {
  return objs.map((o) => JSON.stringify(o)).join("\n") + (objs.length ? "\n" : "");
}
