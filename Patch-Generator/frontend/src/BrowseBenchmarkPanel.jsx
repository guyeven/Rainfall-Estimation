import { API_BASE } from "./apiBase";
import { useMemo, useState } from "react";
import PatchDetail from "./PatchDetail";
import MapPanel from "./MapPanel";

function normalizeApiBase(maybeBase) {
  const fallback = "http://127.0.0.1:8200";
  let b = (maybeBase ?? fallback);
  if (typeof b !== "string") b = String(b ?? "");
  b = b.trim();
  // If env/config produced an "undefined" string, fall back safely.
  if (!b || b === "undefined" || b.startsWith("undefined/") || b.includes("/undefined")) b = fallback;
  // Remove trailing slashes.
  b = b.replace(/\/+$/, "");
  // If someone passed ".../benchmark" as the base, strip it (we add /benchmark/... ourselves).
  b = b.replace(/\/benchmark\/?$/, "");
  return b;
}


import BenchmarkToolbar from "./BenchmarkToolbar";
import PatchListVirtual from "./PatchListVirtual";
import AttributesBox, { defaultAttrs, isAttrsValid } from "./AttributesBox";
import { downloadTextFile, toNdjsonLines } from "./jsonl";
import { parsePatchesNdjsonFromFile } from "./patchFile";
import { importAttributesNdjsonFromFile } from "./attrsImport";

export default function BrowseBenchmarkPanel({ apiBase }) {
  const base = normalizeApiBase(apiBase || API_BASE);
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

  const [attrsByPatch, setAttrsByPatch] = useState({});
  const [importReport, setImportReport] = useState(null);

  const loadedPatchIds = useMemo(() => new Set(patches.map((p) => p.id)), [patches]);
  const selectedPatch = useMemo(
    () => (selectedPatchId ? patches.find((p) => p.id === selectedPatchId) || null : null),
    [patches, selectedPatchId]
  );
  const selectedAttrs = useMemo(
    () => (selectedPatchId ? attrsByPatch[selectedPatchId] || defaultAttrs() : null),
    [attrsByPatch, selectedPatchId]
  );
  const exportDisabled = selectedPatchIds.length === 0;

  async function loadPatchIntoBackend(patch) {
    const resp = await fetch(`${base}/benchmark/load_patch`, {
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
    if (!resp.ok) throw new Error((await resp.text().catch(() => "")) || `load_patch failed: ${resp.status}`);
  }

  async function loadPatchDetails(patchId, zoom) {
    setPatchGeoError(null);
    setPatchGeo(null);
    setPatchGeoLoading(true);
    setPatchImageLoading(true);
    try {
      const geoResp = await fetch(
        `${base}/patch_geo/${encodeURIComponent(patchId)}?zoom_factor=${encodeURIComponent(zoom)}`
      );
      if (!geoResp.ok) throw new Error((await geoResp.text().catch(() => "")) || `Geo failed: ${geoResp.status}`);
      setPatchGeo(await geoResp.json());
    } catch (e) {
      setPatchGeoError(e?.message || String(e));
    } finally {
      setPatchGeoLoading(false);
    }
    setPatchImageUrl(`${base}/patch_image/${encodeURIComponent(patchId)}?_=${Date.now()}`);
  }

  function ensureAttrs(patchId) {
    setAttrsByPatch((prev) => (prev[patchId] ? prev : { ...prev, [patchId]: defaultAttrs() }));
  }

  async function handleRowClick(patchId) {
    setSelectedPatchId(patchId);
    setZoomFactor(1.0);
    setPatchGeoError(null);
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
      s.has(patchId) ? s.delete(patchId) : s.add(patchId);
      return Array.from(s);
    });
  }

  async function handleZoomChange(newZoom) {
    const z = Math.max(0.2, Math.min(5.0, Number(newZoom)));
    setZoomFactor(z);
    if (selectedPatchId) await loadPatchDetails(selectedPatchId, z);
  }

  function handleExportSelectedWithAttributes() {
    const keep = new Set(selectedPatchIds || []);
    const objs = patches
      .filter((p) => keep.has(p.id))
      .map((p) => {
        const a = attrsByPatch[p.id] || defaultAttrs();
        return {
          patch_id: p.id,
          approved: Boolean(a.approved) && isAttrsValid(a),
          attributes: {
            area_type: Array.isArray(a.area_type) ? a.area_type : [],
            rain_type: Array.isArray(a.rain_type) ? a.rain_type : [],
            intensity: a.intensity || "",
            notes: a.notes || "",
          },
        };
      });
    const base = fileName ? fileName.replace(/\.(jsonl|ndjson)$/i, "") : "patches";
    downloadTextFile({ filename: `${base}_selected_with_attributes.jsonl`, text: toNdjsonLines(objs) });
  }

  async function handlePickPatchesFile(file) {
    if (!file) return;
    setLoadError(null);
    setImportReport(null);
    setFileName(file.name);
    setSelectedPatchId(null);
    setSelectedPatchIds([]);
    setPatchGeo(null);
    setPatchImageUrl(null);
    setAttrsByPatch({});

    const res = await parsePatchesNdjsonFromFile(file);
    if (!res.ok) {
      setLoadError(res.error);
      setPatches([]);
      return;
    }
    setPatches(res.patches);
    if (res.patches[0]?.id) setTimeout(() => handleRowClick(res.patches[0].id), 0);
  }

  async function handlePickAttrsFile(file) {
    if (!file) return;
    const res = await importAttributesNdjsonFromFile({ file, existingByPatch: attrsByPatch, loadedPatchIds });
    setImportReport(res.report);
    setAttrsByPatch((prev) => ({ ...prev, ...res.mergedByPatch }));
    setSelectedPatchIds((prev) => {
      const s = new Set(prev || []);
      for (const pid of res.importedPatchIds) s.add(pid);
      return Array.from(s);
    });
  }

  return (
    <div style={{ height: "100vh", overflowY: "auto", padding: 8, boxSizing: "border-box" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
        <BenchmarkToolbar
          fileName={fileName}
          patchCount={patches.length}
          selectedCount={selectedPatchIds.length}
          onPickFile={handlePickPatchesFile}
          onPickAttrsFile={handlePickAttrsFile}
          exportDisabled={exportDisabled}
          onExportSelectedWithAttrs={handleExportSelectedWithAttributes}
          importReport={importReport}
          loadError={loadError}
          viewError={patchGeoError}
        />

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "420px 1fr 1fr",
            gridTemplateRows: "minmax(0, 1fr) minmax(220px, 0.55fr)",
            gap: 8,
            minHeight: "70vh",
            height: "calc(100vh - 170px)",
            minWidth: 0,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <PatchListVirtual
              patches={patches}
              selectedPatchId={selectedPatchId}
              selectedPatchIds={selectedPatchIds}
              onRowClick={handleRowClick}
              onToggleExportSelection={handleToggleKeep}
            />
          </div>

          <div style={{ minWidth: 0, border: "1px solid #ddd", borderRadius: 4, padding: 8, overflow: "auto" }}>
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
          </div>

          <div style={{ minWidth: 0, border: "1px solid #ddd", borderRadius: 4, padding: 8, overflow: "hidden" }}>
            <MapPanel geo={patchGeo} loading={patchGeoLoading} zoomFactor={zoomFactor} onZoomChange={handleZoomChange} />
          </div>

          <div style={{ gridColumn: "1 / span 3", minWidth: 0, overflow: "auto" }}>
            <AttributesBox
              patchId={selectedPatchId}
              attrs={selectedAttrs}
              onChange={(next) => selectedPatchId && setAttrsByPatch((prev) => ({ ...prev, [selectedPatchId]: next }))}
            />
          </div>
        </div>
      </div>
    </div>
  );
}