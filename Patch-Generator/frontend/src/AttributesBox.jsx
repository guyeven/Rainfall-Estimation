import React, { useMemo } from "react";

const AREA_TYPES = ["lake","sea","land","urban","desert","mountain","forest","agriculture","other"];
const RAIN_TYPES = ["convective","stratiform","frontal","orographic","cyclone","mixed","spiral"];
const INTENSITIES = ["light","moderate","heavy","extreme"];

export function defaultAttrs() {
  return { area_type: [], rain_type: [], intensity: "", notes: "", approved: false };
}

export function isAttrsValid(a) {
  if (!a) return false;
  const hasNotes = String(a.notes || "").trim().length > 0;
  return (a.area_type?.length || 0) > 0 || (a.rain_type?.length || 0) > 0 || Boolean(a.intensity) || hasNotes;
}

export default function AttributesBox({ patchId, attrs, onChange }) {
  const valid = useMemo(() => isAttrsValid(attrs), [attrs]);
  const summary = useMemo(() => {
    if (!attrs) return "";
    const area = attrs.area_type?.length ? attrs.area_type.join(", ") : "—";
    const rain = attrs.rain_type?.length ? attrs.rain_type.join(", ") : "—";
    const intensity = attrs.intensity || "—";
    const notes = String(attrs.notes || "").trim();
    const notesShort = notes ? (notes.length > 60 ? notes.slice(0, 60) + "…" : notes) : "—";
    return `Area: ${area} | Rain: ${rain} | Intensity: ${intensity} | Notes: ${notesShort}`;
  }, [attrs]);

  function toggle(key, val) {
    const cur = attrs || defaultAttrs();
    const set = new Set(Array.isArray(cur[key]) ? cur[key] : []);
    if (set.has(val)) set.delete(val);
    else set.add(val);
    onChange?.({ ...cur, [key]: Array.from(set) });
  }

  function setField(key, val) {
    const cur = attrs || defaultAttrs();
    onChange?.({ ...cur, [key]: val });
  }

  if (!patchId) {
    return (
      <div style={{ border: "1px solid #ddd", borderRadius: 4, padding: 10, color: "#666" }}>
        Select a patch to edit attributes.
      </div>
    );
  }

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 4, padding: 10, minHeight: 0, display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontWeight: 700 }}>
          Attributes · <span style={{ fontFamily: "monospace", fontWeight: 600 }}>{patchId}</span>
        </div>
        <label style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={Boolean(attrs?.approved)}
            disabled={!valid}
            onChange={(e) => setField("approved", e.target.checked)}
          />
          Approved
        </label>
      </div>

      <div style={{ fontSize: 13 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Area type</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {AREA_TYPES.map((t) => (
            <label key={t} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={(attrs?.area_type || []).includes(t)} onChange={() => toggle("area_type", t)} />
              {t}
            </label>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 13 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Rain type</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {RAIN_TYPES.map((t) => (
            <label key={t} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={(attrs?.rain_type || []).includes(t)} onChange={() => toggle("rain_type", t)} />
              {t}
            </label>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 13 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Intensity (optional)</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="radio" name={`intensity-${patchId}`} checked={!attrs?.intensity} onChange={() => setField("intensity", "")} />
            —
          </label>
          {INTENSITIES.map((t) => (
            <label key={t} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="radio" name={`intensity-${patchId}`} checked={attrs?.intensity === t} onChange={() => setField("intensity", t)} />
              {t}
            </label>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 13 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Notes</div>
        <textarea
          value={attrs?.notes || ""}
          onChange={(e) => setField("notes", e.target.value)}
          rows={3}
          style={{ width: "100%", resize: "vertical", padding: 8, borderRadius: 4, border: "1px solid #ccc" }}
          placeholder="Optional notes…"
        />
      </div>

      {!valid && (
        <div style={{ padding: 8, background: "#ffe4e4", border: "1px solid #ffb3b3", borderRadius: 4, fontSize: 13 }}>
          <strong>Validation:</strong> Add at least one attribute
        </div>
      )}

      <div style={{ fontSize: 12, color: "#444" }}>
        <div style={{ fontWeight: 600, marginBottom: 2 }}>Summary</div>
        <div style={{ fontFamily: "monospace" }}>{summary}</div>
      </div>
    </div>
  );
}
