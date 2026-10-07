import React, { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Rectangle, Polyline, Tooltip, useMap } from "react-leaflet";

const API_BASE = "http://localhost:8300";

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function FitBounds({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [20, 20] });
  }, [bounds, map]);
  return null;
}

export default function DisplayPatchLinks() {
  const [widthKm, setWidthKm] = useState(95);
  const [heightKm, setHeightKm] = useState(95);

  const [rectBounds, setRectBounds] = useState(null); // [[lat,lon],[lat,lon]] SW/NE
  const [links, setLinks] = useState([]);
  const [count, setCount] = useState(0);
  const [status, setStatus] = useState("Loading…");

  const center = useMemo(() => [52.2, 5.3], []);

  async function fetchPatch(w = widthKm, h = heightKm) {
    setStatus("Loading…");
    try {
      const url = `${API_BASE}/patch?width_km=${encodeURIComponent(w)}&height_km=${encodeURIComponent(h)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const sw = data.rectangle.leaflet_bounds.sw;
      const ne = data.rectangle.leaflet_bounds.ne;

      setRectBounds([[sw.lat, sw.lon], [ne.lat, ne.lon]]);
      setLinks(data.links || []);
      setCount(data.count || 0);
      setStatus(`Loaded ${data.count || 0} links inside the patch.`);
    } catch (e) {
      setStatus(`Error: ${e.message} (is backend running on ${API_BASE}?)`);
      setRectBounds(null);
      setLinks([]);
      setCount(0);
    }
  }

  // Auto-load once on page load
  useEffect(() => {
    fetchPatch(95, 95);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onUpdate() {
    const w = Number(widthKm);
    const h = Number(heightKm);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
      setStatus("Please enter positive numbers for width/height.");
      return;
    }
    fetchPatch(w, h);
  }

  function onDownload() {
    downloadJson("links_in_patch.json", { width_km: widthKm, height_km: heightKm, count, links });
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", height: "100vh" }}>
      <div style={{ padding: 16, borderRight: "1px solid #ddd" }}>
        <h3 style={{ marginTop: 0 }}>Patch Links Viewer</h3>

        <div style={{ marginBottom: 12 }}>
          <label>Width (km)</label>
          <input
            type="number"
            value={widthKm}
            min={0.1}
            step={1}
            onChange={(e) => setWidthKm(e.target.value)}
            style={{ width: "100%", padding: 8 }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label>Height (km)</label>
          <input
            type="number"
            value={heightKm}
            min={0.1}
            step={1}
            onChange={(e) => setHeightKm(e.target.value)}
            style={{ width: "100%", padding: 8 }}
          />
        </div>

        <button onClick={onUpdate} style={{ width: "100%", padding: 10 }}>
          Update patch
        </button>

        <button
          onClick={onDownload}
          style={{ width: "100%", padding: 10, marginTop: 10 }}
          disabled={links.length === 0}
        >
          Download links JSON
        </button>

        <div style={{ marginTop: 12, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap" }}>
          {status}
          {"\n"}Links in patch: {count}
        </div>

        <hr />

        <div style={{ fontSize: 12, color: "#444" }}>
          <b>Anchor (fixed NW corner):</b>
          <div>lat 52.38897</div>
          <div>lon 4.528701910089581</div>
          <div style={{ marginTop: 8 }}>
            Rectangle computed in <b>EPSG:28992 meters</b> (exact) and converted back to WGS84 for display.
          </div>
        </div>
      </div>

      <div style={{ height: "100%", width: "100%" }}>
        <MapContainer center={center} zoom={7} style={{ height: "100vh", width: "100%" }}>
          <TileLayer
            attribution='&copy; OpenStreetMap & CARTO'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />

          {rectBounds && <FitBounds bounds={rectBounds} />}

          {rectBounds && (
            <Rectangle
              bounds={rectBounds}
              pathOptions={{ color: "red", weight: 2, fillColor: "red", fillOpacity: 0.2 }}
            >
              <Tooltip sticky>Patch</Tooltip>
            </Rectangle>
          )}

          {links.map((l, i) => (
            <Polyline
              key={i}
              positions={[
                [l.YStart, l.XStart],
                [l.YEnd, l.XEnd],
              ]}
              pathOptions={{ weight: 1, opacity: 0.6 }}
            />
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
