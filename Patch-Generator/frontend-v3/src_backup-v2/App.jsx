
import { useEffect, useMemo, useState } from "react";
import FilesPanel from "./FilesPanel";
import DetectionControls from "./DetectionControls";
import PatchList from "./PatchList";
import PatchDetail from "./PatchDetail";
import MapPanel from "./MapPanel";
import ExportButton from "./ExportButton";
import { formatTimestamp } from "./utils/formatters";

const API_BASE = "http://127.0.0.1:8200";

export default function App() {
  const [files, setFiles] = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState(null);

  const [selectedFiles, setSelectedFiles] = useState([]);

  const [detectionParams, setDetectionParams] = useState({
    threshold_mm: 8,
    avg_window_y: 1,
    avg_window_x: 1,
    min_width_km: 50,
    min_height_km: 50,
    max_width_km: 250,
    max_height_km: 250,
    max_files: 20,
  });

  const [patches, setPatches] = useState([]);
  const [detectLoading, setDetectLoading] = useState(false);
  const [detectError, setDetectError] = useState(null);

  const [selectedPatchId, setSelectedPatchId] = useState(null);
  const [selectedPatchIds, setSelectedPatchIds] = useState([]);

  const [patchGeo, setPatchGeo] = useState(null);
  const [patchImageUrl, setPatchImageUrl] = useState(null);
  const [patchGeoLoading, setPatchGeoLoading] = useState(false);
  const [patchImageLoading, setPatchImageLoading] = useState(false);
  const [patchGeoError, setPatchGeoError] = useState(null);
  const [patchImageError, setPatchImageError] = useState(null);

  const [zoomFactor, setZoomFactor] = useState(1.0);

  useEffect(() => {
    const fetchFiles = async () => {
      setFilesLoading(true);
      setFilesError(null);
      try {
        const res = await fetch(`${API_BASE}/files?limit=200`);
        if (!res.ok) throw new Error(`Files request failed: ${res.status}`);
        const data = await res.json();
        setFiles(data || []);
      } catch (err) {
        setFilesError(err.message || "Failed to load files");
      } finally {
        setFilesLoading(false);
      }
    };
    fetchFiles();
  }, []);

  const handleRefreshFiles = async () => {
    setSelectedFiles([]);
    setFiles([]);
    setFilesError(null);
    setFilesLoading(true);
    try {
      const res = await fetch(`${API_BASE}/files?limit=200`);
      if (!res.ok) throw new Error(`Files request failed: ${res.status}`);
      const data = await res.json();
      setFiles(data || []);
    } catch (err) {
      setFilesError(err.message || "Failed to load files");
    } finally {
      setFilesLoading(false);
    }
  };

  const handleToggleFile = (filepath) => {
    setSelectedFiles((prev) =>
      prev.includes(filepath)
        ? prev.filter((f) => f !== filepath)
        : [...prev, filepath]
    );
  };

  const handleSelectNone = () => setSelectedFiles([]);

  const handleSelectLatestN = (n) => {
    if (!Array.isArray(files) || files.length === 0) return;
    const latest = files.slice(0, n).map((f) => f.filepath || f.path || f);
    setSelectedFiles(latest);
  };

  const handleDetectionParamsChange = (next) => setDetectionParams(next);

  const loadPatchDetails = async (patchId, zoom) => {
    setPatchGeoLoading(true);
    setPatchGeoError(null);
    setPatchImageLoading(true);
    setPatchImageError(null);

    try {
      const geoRes = await fetch(
        `${API_BASE}/patch_geo/${encodeURIComponent(
          patchId
        )}?zoom_factor=${zoom}`
      );
      if (!geoRes.ok) throw new Error(`Geo request failed: ${geoRes.status}`);
      const geoData = await geoRes.json();
      setPatchGeo(geoData);
    } catch (err) {
      setPatchGeoError(err.message || "Failed to load patch geo");
      setPatchGeo(null);
    } finally {
      setPatchGeoLoading(false);
    }

    try {
      const imgUrl = `${API_BASE}/patch_image/${encodeURIComponent(
        patchId
      )}?_=${Date.now()}`;
      setPatchImageUrl(imgUrl);
    } catch (err) {
      setPatchImageError(err.message || "Failed to prepare image URL");
      setPatchImageUrl(null);
    } finally {
      setPatchImageLoading(false);
    }
  };

  const handleDetectPatches = async () => {
    setDetectLoading(true);
    setDetectError(null);
    setPatches([]);
    setSelectedPatchId(null);
    setSelectedPatchIds([]);
    setPatchGeo(null);
    setPatchImageUrl(null);
    setPatchGeoError(null);
    setPatchImageError(null);

    const body = { ...detectionParams, files: selectedFiles };

    try {
      const res = await fetch(`${API_BASE}/detect_patches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(
          `Detection failed: ${res.status} ${text || res.statusText}`
        );
      }
      const data = await res.json();
      const arr = Array.isArray(data) ? data : [];
      setPatches(arr);
      if (arr.length > 0) {
        const firstId = arr[0].id;
        setSelectedPatchId(firstId);
        setZoomFactor(1.0);
        await loadPatchDetails(firstId, 1.0);
      }
    } catch (err) {
      setDetectError(err.message || "Failed to detect patches");
    } finally {
      setDetectLoading(false);
    }
  };

  const handleRowClick = async (patchId) => {
    setSelectedPatchId(patchId);
    const newZoom = 1.0;
    setZoomFactor(newZoom);
    await loadPatchDetails(patchId, newZoom);
  };

  const handleToggleExportSelection = (patchId) => {
    setSelectedPatchIds((prev) =>
      prev.includes(patchId)
        ? prev.filter((id) => id !== patchId)
        : [...prev, patchId]
    );
  };

  const handleImportPatchIds = (ids) => {
    if (!Array.isArray(ids)) return;
    const valid = ids.filter((id) => patches.some((p) => p.id === id));
    setSelectedPatchIds(valid);
  };

  const handleZoomChange = async (newZoom) => {
    if (!selectedPatchId) return;
    const clamped = Math.max(0.2, Math.min(newZoom, 5));
    setZoomFactor(clamped);
    await loadPatchDetails(selectedPatchId, clamped);
  };

  const selectedPatch = useMemo(
    () => patches.find((p) => p.id === selectedPatchId) || null,
    [patches, selectedPatchId]
  );

  const selectedPatchesForExport = useMemo(
    () => patches.filter((p) => selectedPatchIds.includes(p.id)),
    [patches, selectedPatchIds]
  );

  const lastTimestamp = useMemo(() => {
    if (!patches.length) return null;
    const times = patches
      .map((p) => (p.timestamp ? new Date(p.timestamp) : null))
      .filter((d) => d && !Number.isNaN(d.getTime()));
    if (!times.length) return null;
    times.sort((a, b) => b - a);
    return times[0].toISOString();
  }, [patches]);

  return (
    <div
      style={{
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        padding: "8px",
        boxSizing: "border-box",
      }}
    >
      <header
        style={{
          marginBottom: "8px",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: "1.2rem" }}>
            Rain Patch Explorer
          </h1>
          <p style={{ margin: 0, fontSize: "0.8rem", color: "#555" }}>
            Backend: {API_BASE}
          </p>
        </div>
        <div style={{ textAlign: "right", fontSize: "0.8rem" }}>
          <div>Patches: {patches.length}</div>
          {lastTimestamp && (
            <div>Latest timestamp: {formatTimestamp(lastTimestamp)}</div>
          )}
        </div>
      </header>

      {(filesError || detectError || patchGeoError || patchImageError) && (
        <div
          style={{
            marginBottom: "8px",
            padding: "8px",
            background: "#ffe4e4",
            border: "1px solid #ffb3b3",
            borderRadius: "4px",
            fontSize: "0.85rem",
          }}
        >
          <strong>Error:</strong>{" "}
          {filesError || detectError || patchGeoError || patchImageError}
        </div>
      )}

      <div style={{ flex: 1, display: "flex", gap: "8px", minHeight: 0 }}>
        <div
          style={{
            flex: "0 0 360px",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            minWidth: 0,
          }}
        >
          <FilesPanel
            files={files}
            loading={filesLoading}
            error={filesError}
            selectedFiles={selectedFiles}
            onToggleFile={handleToggleFile}
            onSelectNone={handleSelectNone}
            onSelectLatest={handleSelectLatestN}
            onRefresh={handleRefreshFiles}
          />

          <DetectionControls
            params={detectionParams}
            onChange={handleDetectionParamsChange}
            onDetect={handleDetectPatches}
            detecting={detectLoading}
            selectedFilesCount={selectedFiles.length}
          />

          <ExportButton
            selectedPatches={selectedPatchesForExport}
            onImportPatchIds={handleImportPatchIds}
          />
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            minWidth: 0,
          }}
        >
          <div style={{ flex: "0 0 40%", minHeight: 0 }}>
            <PatchList
              patches={patches}
              selectedPatchId={selectedPatchId}
              selectedPatchIds={selectedPatchIds}
              onRowClick={handleRowClick}
              onToggleExportSelection={handleToggleExportSelection}
              detecting={detectLoading}
            />
          </div>

          <div
            style={{
              flex: "1 1 auto",
              display: "flex",
              gap: "8px",
              minHeight: 0,
            }}
          >
            <div style={{ flex: "0 0 45%", minWidth: 0 }}>
              <PatchDetail
                patch={selectedPatch}
                imageUrl={patchImageUrl}
                loading={patchImageLoading}
              />
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
