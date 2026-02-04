import { useMemo, useState } from "react";
import PatchList from "./PatchList";
import PatchDetail from "./PatchDetail";
import MapPanel from "./MapPanel";

/**
 * BrowseBenchmarkPanel
 * - Loads an NDJSON/JSONL benchmark file exported by the batch runner.
 * - Lets the user browse patches (list + detail + map).
 * - Lets the user mark ("Keep") a subset and export ONLY selected patches to JSONL.
 *
 * Backend interaction:
 * - On patch selection, POST /benchmark/load_patch with (source_file + bbox + id).
 *   Backend crops from H5 on-demand and stores it in the existing in-memory cache
 *   so the standard /patch_image/{id} and /patch_geo/{id} endpoints work.
 */
export default function BrowseBenchmarkPanel({ apiBase }) {
  const [fileName, setFileName] = useState("");
  const [patches, setPatches] = useState([]);
  const [loadError, setLoadError] = useState(null);

  const [selectedPatchId, setSelectedPatchId] = useState(null);
  const [selectedPatchIds, setSelectedPatchIds] = useState([]);

  const [patchGeo, setPatchGeo] = useState(null);
  const [patchGeoLoading, setPatchGeoLoading] = useState(false);
  const [patchGeoError, setPatchGeoError] = useState(null);

  const [patchImageUrl, setPatchImageUrl] = useState(null);
  const [patchImageLoading, setPatchImageLoading] = useState(false);

  const [zoomFactor, setZoomFactor] = useState(1.0);

  // ---- ADDED: per-patch attribute annotations (local state) ----
  const AREA_TYPES = [
    "lake",
    "sea",
    "land",
    "urban",
    "desert",
    "mountain",
    "forest",
    "agriculture",
    "other",
  ];
  const RAIN_TYPES = [
    "convective",
    "stratiform",
    "frontal",
    "orographic",
    "cyclone",
    "mixed",
    "spiral",
  ];
  const INTENSITIES = ["light", "moderate", "heavy", "extreme"];

  const [attrsByPatch, setAttrsByPatch] = useState({});
  const [attrsOpen, setAttrsOpen] = useState(true);

  const selectedAttrs = useMemo(() => {
    if (!selectedPatchId) return null;
    return (
      attrsByPatch[selectedPatchId] || {
        area_type: [],
        rain_type: [],
        intensity: "",
        notes: "",
        approved: false,
      }
    );
  }, [attrsByPatch, selectedPatchId]);

  function isAttrsValid(a) {
    if (!a) return false;
    const hasNotes = String(a.notes || "").trim().length > 0;
    return (
      (Array.isArray(a.area_type) && a.area_type.length > 0) ||
      (Array.isArray(a.rain_type) && a.rain_type.length > 0) ||
      Boolean(a.intensity) ||
      hasNotes
    );
  }

  const selectedAttrsValid = useMemo(() => isAttrsValid(selectedAttrs), [selectedAttrs]);

  const attrsSummary = useMemo(() => {
    if (!selectedAttrs) return "";
    const area = (selectedAttrs.area_type || []).length ? selectedAttrs.area_type.join(", ") : "—";
    const rain = (selectedAttrs.rain_type || []).length ? selectedAttrs.rain_type.join(", ") : "—";
    const intensity = selectedAttrs.intensity || "—";
    const notes = String(selectedAttrs.notes || "").trim();
    const notesShort = notes ? (notes.length > 60 ? notes.slice(0, 60) + "…" : notes) : "—";
    return `Area: ${area} | Rain: ${rain} | Intensity: ${intensity} | Notes: ${notesShort}`;
  }, [selectedAttrs]);

  function ensureAttrs(patchId) {
    setAttrsByPatch((prev) => {
      if (prev[patchId]) return prev;
      return {
        ...prev,
        [patchId]: { area_type: [], rain_type: [], intensity: "", notes: "", approved: false },
      };
    });
  }

  function toggleAttr(patchId, key, value) {
    setAttrsByPatch((prev) => {
      const cur =
        prev[patchId] || { area_type: [], rain_type: [], intensity: "", notes: "", approved: false };
      const arr = new Set(Array.isArray(cur[key]) ? cur[key] : []);
      if (arr.has(value)) arr.delete(value);
      else arr.add(value);
      return { ...prev, [patchId]: { ...cur, [key]: Array.from(arr), approved: cur.approved } };
    });
  }

  function setAttrField(patchId, key, value) {
    setAttrsByPatch((prev) => {
      const cur =
        prev[patchId] || { area_type: [], rain_type: [], intensity: "", notes: "", approved: false };
      return { ...prev, [patchId]: { ...cur, [key]: value } };
    });
  }

  function setApproved(patchId, approved) {
    setAttrsByPatch((prev) => {
      const cur =
        prev[patchId] || { area_type: [], rain_type: [], intensity: "", notes: "", approved: false };
      return { ...prev, [patchId]: { ...cur, approved: Boolean(approved) } };
    });
  }

  function handleExportPatchesWithAttributes() {
    // Export ONLY patches that have >=1 attribute (valid)
    const lines = patches
      .filter((p) => isAttrsValid(attrsByPatch[p.id]))
      .map((p) => {
        const a = attrsByPatch[p.id];
        return JSON.stringify({
          patch_id: p.id,
          approved: Boolean(a?.approved),
          attributes: {
            area_type: Array.isArray(a?.area_type) ? a.area_type : [],
            rain_type: Array.isArray(a?.rain_type) ? a.rain_type : [],
            intensity: a?.intensity || "",
            notes: a?.notes || "",
          },
        });
      });

    const blob = new Blob([lines.join("\n") + (lines.length ? "\n" : "")], {
      type: "application/x-ndjson",
    });

    const a = document.createElement("a");
    const url = URL.createObjectURL(blob);
    a.href = url;

    const base = fileName ? fileName.replace(/\.(jsonl|ndjson)$/i, "") : "patches";
    a.download = `${base}_attributes.jsonl`;

    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
  // ---- END ADDED ----

  const selectedPatch = useMemo(() => {
    if (!selectedPatchId) return null;
    return patches.find((p) => p.id === selectedPatchId) || null;
  }, [patches, selectedPatchId]);

  const selectedPatchesForExport = useMemo(() => {
    const keep = new Set(selectedPatchIds || []);
    return patches.filter((p) => keep.has(p.id));
  }, [patches, selectedPatchIds]);

  function safeParseJson(line, lineNo) {
    try {
      return JSON.parse(line);
    } catch (e) {
      throw new Error(`Invalid JSON on line ${lineNo}: ${e?.message || String(e)}`);
    }
  }

  async function loadPatchIntoBackend(patch) {
    // Cropping-on-demand: only load the currently selected patch (bounded memory).
    const resp = await fetch(`${apiBase}/benchmark/load_patch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: patch.id,
        source_file: patch.source_file,
        timestamp: patch.timestamp,
        y_min: patch.y_min,
        y_max: patch.y_max,
        x_min: patch.x_min,
        x_max: patch.x_max,
        // include optional metadata if backend chooses to store it
        center_lat: patch.center_lat,
        center_lon: patch.center_lon,
        width_km: patch.width_km,
        height_km: patch.height_km,
        area_km2: patch.area_km2,
        mean_rainfall: patch.mean_rainfall,
        max_rainfall: patch.max_rainfall,
        nearest_city: patch.nearest_city,
      }),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(txt || `Backend load_patch failed: ${resp.status}`);
    }
  }

  async function loadPatchDetails(patchId, zoom) {
    setPatchGeoError(null);
    setPatchGeo(null);
    setPatchGeoLoading(true);
    setPatchImageLoading(true);

    try {
      const geoResp = await fetch(
        `${apiBase}/patch_geo/${encodeURIComponent(patchId)}?zoom_factor=${encodeURIComponent(
          zoom
        )}`
      );
      if (!geoResp.ok) {
        const txt = await geoResp.text().catch(() => "");
        throw new Error(txt || `Geo failed: ${geoResp.status}`);
      }
      const geo = await geoResp.json();
      setPatchGeo(geo);
    } catch (e) {
      setPatchGeoError(e?.message || String(e));
    } finally {
      setPatchGeoLoading(false);
    }

    // Image: just set URL; <img> onLoad will clear the spinner
    setPatchImageUrl(`${apiBase}/patch_image/${encodeURIComponent(patchId)}?_=${Date.now()}`);
  }

  async function handleRowClick(patchId) {
    setSelectedPatchId(patchId);
    setZoomFactor(1.0);
    setPatchGeoError(null);

    // ADDED: ensure attribute state exists for selected patch (does not affect UI)
    ensureAttrs(patchId);

    const patch = patches.find((p) => p.id === patchId);
    if (!patch) return;

    try {
      await loadPatchIntoBackend(patch);
      await loadPatchDetails(patchId, 1.0);
    } catch (e) {
      setPatchGeoError(e?.message || String(e));
      setPatchGeo(null);
      setPatchImageUrl(null);
      setPatchImageLoading(false);
    }
  }

  function handleToggleKeep(patchId) {
    setSelectedPatchIds((prev) => {
      const s = new Set(prev || []);
      if (s.has(patchId)) s.delete(patchId);
      else s.add(patchId);
      return Array.from(s);
    });
  }

  async function handleZoomChange(newZoom) {
    const z = Math.max(0.2, Math.min(5.0, Number(newZoom)));
    setZoomFactor(z);
    if (!selectedPatchId) return;

    try {
      await loadPatchDetails(selectedPatchId, z);
    } catch {
      // geo error state already handled inside loadPatchDetails
    }
  }

  function handleExportSelected() {
    const lines = selectedPatchesForExport.map((p) => JSON.stringify(p));
    const blob = new Blob([lines.join("\n") + (lines.length ? "\n" : "")], {
      type: "application/x-ndjson",
    });

    const a = document.createElement("a");
    const url = URL.createObjectURL(blob);
    a.href = url;

    const base = fileName ? fileName.replace(/\.(jsonl|ndjson)$/i, "") : "selected_patches";
    a.download = `${base}_selected.jsonl`;

    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function handleFilePicked(file) {
    if (!file) return;
    setLoadError(null);
    setFileName(file.name);
    setSelectedPatchId(null);
    setSelectedPatchIds([]);
    setPatchGeo(null);
    setPatchImageUrl(null);

    // ADDED: keep separate per file/session (simple + safe)
    setAttrsByPatch({});

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = String(reader.result || "");
        const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
        const parsed = lines.map((l, idx) => safeParseJson(l, idx + 1));
        // Minimal validation
        const cleaned = parsed.filter((p) => p && typeof p.id === "string" && p.id.length);
        if (!cleaned.length) {
          throw new Error("No valid patch records found (expected one JSON object per line).");
        }
        setPatches(cleaned);
        setSelectedPatchId(cleaned[0].id);
        // auto-load first patch
        setTimeout(() => handleRowClick(cleaned[0].id), 0);
      } catch (e) {
        setLoadError(e?.message || String(e));
        setPatches([]);
      }
    };
    reader.onerror = () => setLoadError("Failed to read file.");
    reader.readAsText(file);
  }

  const exportAttrsDisabled = useMemo(() => {
    // disable if no patch has valid attrs
    return !patches.some((p) => isAttrsValid(attrsByPatch[p.id]));
  }, [patches, attrsByPatch]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", minWidth: 0 }}>
      <section style={{ border: "1px solid #ddd", borderRadius: "4px", padding: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 600 }}>Browse benchmark (JSONL)</div>

          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "4px 8px",
              border: "1px solid #aaa",
              borderRadius: "4px",
              background: "#f8f8f8",
              cursor: "pointer",
              fontSize: "0.85rem",
            }}
          >
            <input
              type="file"
              accept=".jsonl,.ndjson,.txt"
              style={{ display: "none" }}
              onChange={(e) => handleFilePicked(e.target.files?.[0] || null)}
            />
            Load JSONL…
          </label>

          <div style={{ fontSize: "0.85rem", color: "#444" }}>
            {fileName ? (
              <>
                <strong>File:</strong> {fileName} · <strong>Patches:</strong> {patches.length} ·{" "}
                <strong>Selected:</strong> {selectedPatchIds.length}
              </>
            ) : (
              "No file loaded."
            )}
          </div>

          <div style={{ marginLeft: "auto", display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button
              type="button"
              disabled={selectedPatchesForExport.length === 0}
              onClick={handleExportSelected}
              style={{
                padding: "6px 10px",
                borderRadius: "4px",
                border: "1px solid #0077cc",
                background: selectedPatchesForExport.length ? "#0077cc" : "#c7d9ea",
                color: "#fff",
                cursor: selectedPatchesForExport.length ? "pointer" : "not-allowed",
                fontSize: "0.85rem",
              }}
            >
              Export selected → JSONL
            </button>

            {/* ADDED: Export patches with attributes (JSONL) */}
            <button
              type="button"
              disabled={exportAttrsDisabled}
              onClick={handleExportPatchesWithAttributes}
              style={{
                padding: "6px 10px",
                borderRadius: "4px",
                border: "1px solid #444",
                background: exportAttrsDisabled ? "#e6e6e6" : "#444",
                color: exportAttrsDisabled ? "#777" : "#fff",
                cursor: exportAttrsDisabled ? "not-allowed" : "pointer",
                fontSize: "0.85rem",
              }}
              title={
                exportAttrsDisabled
                  ? "No patches currently have attributes (area/rain/intensity/notes)."
                  : "Exports only patches that have at least one attribute."
              }
            >
              Export patches with attributes (JSONL)
            </button>
          </div>
        </div>

        {loadError && (
          <div
            style={{
              marginTop: "8px",
              padding: "8px",
              background: "#ffe4e4",
              border: "1px solid #ffb3b3",
              borderRadius: "4px",
              fontSize: "0.85rem",
            }}
          >
            <strong>Load error:</strong> {loadError}
          </div>
        )}

        {patchGeoError && (
          <div
            style={{
              marginTop: "8px",
              padding: "8px",
              background: "#fff7d6",
              border: "1px solid #ffe08a",
              borderRadius: "4px",
              fontSize: "0.85rem",
            }}
          >
            <strong>View error:</strong> {patchGeoError}
          </div>
        )}
      </section>

      <div style={{ display: "flex", gap: "8px", minHeight: "70vh", minWidth: 0 }}>
        <div
          style={{
            width: "420px",
            minWidth: "320px",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <PatchList
            patches={patches}
            selectedPatchId={selectedPatchId}
            selectedPatchIds={selectedPatchIds}
            onRowClick={handleRowClick}
            onToggleExportSelection={handleToggleKeep}
            detecting={false}
          />
        </div>

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ display: "flex", gap: "8px", minHeight: 0, flex: 1 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <PatchDetail patch={selectedPatch} imageUrl={patchImageUrl} loading={patchImageLoading} />
              {patchImageUrl && (
                <img
                  src={patchImageUrl}
                  alt="patch"
                  style={{ display: "none" }}
                  onLoad={() => setPatchImageLoading(false)}
                  onError={() => setPatchImageLoading(false)}
                />
              )}

              {/* ADDED: Attributes editor (additive; does not remove existing UI) */}
              {selectedPatchId && selectedAttrs && (
                <section
                  style={{
                    marginTop: "8px",
                    border: "1px solid #ddd",
                    borderRadius: "4px",
                    padding: "8px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <button
                      type="button"
                      onClick={() => setAttrsOpen((v) => !v)}
                      style={{
                        padding: "4px 8px",
                        borderRadius: "4px",
                        border: "1px solid #aaa",
                        background: "#f8f8f8",
                        cursor: "pointer",
                        fontSize: "0.85rem",
                      }}
                    >
                      {attrsOpen ? "Hide" : "Show"} attributes
                    </button>
                    <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>
                      Patch attributes: <span style={{ fontFamily: "monospace" }}>{selectedPatchId}</span>
                    </div>
                  </div>

                  {attrsOpen && (
                    <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      <div style={{ fontSize: "0.85rem", color: "#333" }}>
                        <div style={{ fontWeight: 600, marginBottom: "4px" }}>Area type</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          {AREA_TYPES.map((t) => (
                            <label key={t} style={{ display: "inline-flex", gap: "6px", alignItems: "center" }}>
                              <input
                                type="checkbox"
                                checked={(selectedAttrs.area_type || []).includes(t)}
                                onChange={() => toggleAttr(selectedPatchId, "area_type", t)}
                              />
                              {t}
                            </label>
                          ))}
                        </div>
                      </div>

                      <div style={{ fontSize: "0.85rem", color: "#333" }}>
                        <div style={{ fontWeight: 600, marginBottom: "4px" }}>Rain type</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          {RAIN_TYPES.map((t) => (
                            <label key={t} style={{ display: "inline-flex", gap: "6px", alignItems: "center" }}>
                              <input
                                type="checkbox"
                                checked={(selectedAttrs.rain_type || []).includes(t)}
                                onChange={() => toggleAttr(selectedPatchId, "rain_type", t)}
                              />
                              {t}
                            </label>
                          ))}
                        </div>
                      </div>

                      <div style={{ fontSize: "0.85rem", color: "#333" }}>
                        <div style={{ fontWeight: 600, marginBottom: "4px" }}>Intensity (optional)</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          <label style={{ display: "inline-flex", gap: "6px", alignItems: "center" }}>
                            <input
                              type="radio"
                              name={`intensity-${selectedPatchId}`}
                              checked={!selectedAttrs.intensity}
                              onChange={() => setAttrField(selectedPatchId, "intensity", "")}
                            />
                            —
                          </label>
                          {INTENSITIES.map((t) => (
                            <label key={t} style={{ display: "inline-flex", gap: "6px", alignItems: "center" }}>
                              <input
                                type="radio"
                                name={`intensity-${selectedPatchId}`}
                                checked={selectedAttrs.intensity === t}
                                onChange={() => setAttrField(selectedPatchId, "intensity", t)}
                              />
                              {t}
                            </label>
                          ))}
                        </div>
                      </div>

                      <div style={{ fontSize: "0.85rem", color: "#333" }}>
                        <div style={{ fontWeight: 600, marginBottom: "4px" }}>Notes</div>
                        <textarea
                          value={selectedAttrs.notes || ""}
                          onChange={(e) => setAttrField(selectedPatchId, "notes", e.target.value)}
                          rows={3}
                          style={{ width: "100%", resize: "vertical", padding: "6px", borderRadius: "4px" }}
                          placeholder="Optional notes…"
                        />
                      </div>

                      {!selectedAttrsValid && (
                        <div
                          style={{
                            padding: "8px",
                            background: "#ffe4e4",
                            border: "1px solid #ffb3b3",
                            borderRadius: "4px",
                            fontSize: "0.85rem",
                          }}
                        >
                          <strong>Validation:</strong> Add at least one attribute
                        </div>
                      )}

                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                        <div style={{ fontSize: "0.85rem", color: "#444" }}>
                          <div style={{ fontWeight: 600, marginBottom: "2px" }}>Summary</div>
                          <div style={{ fontFamily: "monospace" }}>{attrsSummary}</div>
                        </div>

                        <label style={{ display: "inline-flex", gap: "8px", alignItems: "center", fontSize: "0.9rem" }}>
                          <input
                            type="checkbox"
                            checked={Boolean(selectedAttrs.approved)}
                            disabled={!selectedAttrsValid}
                            onChange={(e) => setApproved(selectedPatchId, e.target.checked)}
                          />
                          Approved
                        </label>
                      </div>
                    </div>
                  )}
                </section>
              )}
              {/* END ADDED */}
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <MapPanel
                geo={patchGeo}
                loading={patchGeoLoading}
                zoomFactor={zoomFactor}
                onZoomChange={handleZoomChange}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
