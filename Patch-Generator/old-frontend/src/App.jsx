import { useEffect, useState } from "react";
import axios from "axios";

import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, Rectangle, useMap } from "react-leaflet";

const API = "http://127.0.0.1:8200"; // <-- change if backend runs on another port

function MapBoundsSetter({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [map, bounds]);
  return null;
}

function MapPanel({ geo }) {
  if (!geo) return null;

  const mapBounds = [
    [geo.map_lat_min, geo.map_lon_min],
    [geo.map_lat_max, geo.map_lon_max],
  ];

  const patchBounds = [
    [geo.patch_lat_min, geo.patch_lon_min],
    [geo.patch_lat_max, geo.patch_lon_max],
  ];

  return (
    <MapContainer
      bounds={mapBounds}
      style={{ height: "400px", width: "100%" }}
      scrollWheelZoom={true}
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Rectangle bounds={patchBounds} pathOptions={{ color: "red" }} />
      <MapBoundsSetter bounds={mapBounds} />
    </MapContainer>
  );
}

export default function App() {
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [patches, setPatches] = useState([]);
  const [selectedPatchId, setSelectedPatchId] = useState(null);
  const [patchImageUrl, setPatchImageUrl] = useState(null);
  const [geo, setGeo] = useState(null);
  const [zoomFactor, setZoomFactor] = useState(3);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Load available rainfall files once
  useEffect(() => {
    axios
      .get(`${API}/files`)
      .then((res) => setFiles(res.data))
      .catch((err) => {
        console.error(err);
        setErrorMsg("Failed to load file list.");
      });
  }, []);

  function toggleFile(path) {
    setSelectedFiles((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  }

  async function detectPatches() {
    setErrorMsg("");
    setLoading(true);
    setPatches([]);
    setSelectedPatchId(null);
    setPatchImageUrl(null);
    setGeo(null);

    const body = {
      threshold_mm: 3,
      avg_window_y: 10,
      avg_window_x: 10,
      min_width_km: 50,
      min_height_km: 50,
      max_width_km: 250,
      max_height_km: 250,
      max_files: 5,
    };

    if (selectedFiles.length > 0) {
      body.files = selectedFiles;
    }

    try {
      const res = await axios.post(`${API}/detect_patches`, body);
      setPatches(res.data);
      if (res.data.length === 0) {
        setErrorMsg("No patches found for these parameters.");
      }
    } catch (err) {
      console.error(err);
      const detail =
        err.response?.data?.detail || "Error while detecting patches.";
      setErrorMsg(detail);
    } finally {
      setLoading(false);
    }
  }

  async function loadPatch(id, zFactor = zoomFactor) {
    setSelectedPatchId(id);
    setPatchImageUrl(`${API}/patch_image/${id}`);
    setErrorMsg("");

    try {
      const res = await axios.get(
        `${API}/patch_geo/${id}?zoom_factor=${zFactor}`
      );
      setGeo(res.data);
      setZoomFactor(zFactor);
    } catch (err) {
      console.error(err);
      const detail =
        err.response?.data?.detail || "Error while loading patch geo info.";
      setErrorMsg(detail);
    }
  }

  async function zoom(delta) {
    if (!selectedPatchId) return;
    const newFactor = Math.min(10, Math.max(1, zoomFactor + delta));
    await loadPatch(selectedPatchId, newFactor);
  }

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
      <h1>Rainfall Patch Generator</h1>

      {errorMsg && (
        <div
          style={{
            marginBottom: 12,
            padding: 8,
            border: "1px solid #c00",
            background: "#ffe5e5",
          }}
        >
          {errorMsg}
        </div>
      )}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* LEFT PANEL: files & patches */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2>Files</h2>
          <button onClick={detectPatches} disabled={loading}>
            {loading ? "Detecting..." : "Detect patches"}
          </button>

          <table
            cellPadding={4}
            style={{ marginTop: 10, width: "100%", borderCollapse: "collapse" }}
          >
            <thead>
              <tr>
                <th style={{ borderBottom: "1px solid #ccc" }}>Use?</th>
                <th style={{ borderBottom: "1px solid #ccc" }}>Path</th>
                <th style={{ borderBottom: "1px solid #ccc" }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.path}>
                  <td style={{ borderBottom: "1px solid #eee" }}>
                    <input
                      type="checkbox"
                      checked={selectedFiles.includes(f.path)}
                      onChange={() => toggleFile(f.path)}
                    />
                  </td>
                  <td
                    style={{
                      borderBottom: "1px solid #eee",
                      fontSize: 12,
                      wordBreak: "break-all",
                    }}
                  >
                    {f.path}
                  </td>
                  <td style={{ borderBottom: "1px solid #eee", fontSize: 12 }}>
                    {f.timestamp}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2 style={{ marginTop: 20 }}>Patches</h2>
          {patches.length === 0 && <div>No patches yet.</div>}
          <ul style={{ paddingLeft: 16 }}>
            {patches.map((p) => (
              <li key={p.id} style={{ marginBottom: 4 }}>
                <button
                  onClick={() => loadPatch(p.id)}
                  style={{
                    padding: "2px 6px",
                    fontSize: 12,
                    marginRight: 8,
                    background:
                      p.id === selectedPatchId ? "#ddd" : "buttonface",
                  }}
                >
                  Select
                </button>
                <span style={{ fontSize: 12 }}>
                  {p.id} — {p.nearest_city} — {p.area_km2.toFixed(1)} km²
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* RIGHT PANEL: patch image + map */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {patchImageUrl && (
            <div>
              <h2>Patch heatmap</h2>
              <img
                src={patchImageUrl}
                alt="Patch"
                style={{
                  border: "1px solid #888",
                  maxWidth: "100%",
                  display: "block",
                }}
              />
            </div>
          )}

          {geo && (
            <div style={{ marginTop: 20 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <h2 style={{ margin: 0 }}>Geographical map</h2>
                <div>
                  <button onClick={() => zoom(-1)} style={{ marginRight: 4 }}>
                    Zoom out
                  </button>
                  <button onClick={() => zoom(+1)}>Zoom in</button>
                  <span style={{ marginLeft: 8, fontSize: 12 }}>
                    factor: {zoomFactor.toFixed(1)}
                  </span>
                </div>
              </div>

              <MapPanel geo={geo} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
