// Patch file (JSONL/NDJSON) parsing helpers.

function safeParseJson(line, lineNo) {
  try {
    return { ok: true, value: JSON.parse(line) };
  } catch (e) {
    return { ok: false, error: `Invalid JSON on line ${lineNo}: ${e?.message || String(e)}` };
  }
}

export async function parsePatchesNdjsonFromFile(file) {
  if (!file) return { ok: false, error: "No file" };

  const text = await file.text();
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  const patches = [];
  for (let i = 0; i < lines.length; i++) {
    const res = safeParseJson(lines[i], i + 1);
    if (!res.ok) return { ok: false, error: res.error };
    const p = res.value;
    if (p && typeof p.id === "string" && p.id.trim()) patches.push(p);
  }

  if (!patches.length) {
    return { ok: false, error: "No valid patch records found (expected one JSON object per line with an 'id')." };
  }
  return { ok: true, patches };
}
