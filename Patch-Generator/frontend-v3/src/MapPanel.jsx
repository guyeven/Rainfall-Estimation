import { API_BASE } from "./apiBase";
import { MapContainer, TileLayer, Rectangle, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function isValidNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

function SafeFitBounds({ geo }) {
  const map = useMap();
  if (!geo) return null;

  const { map_lat_min, map_lat_max, map_lon_min, map_lon_max } = geo;

  if (
    !isValidNum(map_lat_min) ||
    !isValidNum(map_lat_max) ||
    !isValidNum(map_lon_min) ||
    !isValidNum(map_lon_max)
  ) {
    return null;
  }

  const bounds = [
    [map_lat_min, map_lon_min],
    [map_lat_max, map_lon_max],
  ];

  try {
    map.fitBounds(bounds, { padding: [15, 15] });
  } catch (_) {
    // ignore leaflet errors
  }

  return null;
}

export default function MapPanel({ geo, loading, zoomFactor, onZoomChange }) {
  const tileUrl =
    geo?.tile_url_template ||
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  const patchBounds =
    geo &&
    isValidNum(geo.patch_lat_min) &&
    isValidNum(geo.patch_lat_max) &&
    isValidNum(geo.patch_lon_min) &&
    isValidNum(geo.patch_lon_max)
      ? [
          [geo.patch_lat_min, geo.patch_lon_min],
          [geo.patch_lat_max, geo.patch_lon_max],
        ]
      : null;

  const center = [
    isValidNum(geo?.center_lat) ? geo.center_lat : 0,
    isValidNum(geo?.center_lon) ? geo.center_lon : 0,
  ];

  const handleZoomIn = () => onZoomChange(zoomFactor / 1.3);
  const handleZoomOut = () => onZoomChange(zoomFactor * 1.3);

  const disabled = loading || !geo;

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: "4px",
        padding: "8px",
        background: "#fff",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: "4px",
          alignItems: "center",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Map</h2>
        <div style={{ display: "flex", gap: "4px", fontSize: "0.75rem" }}>
          <span>Zoom factor: {zoomFactor.toFixed(2)}</span>
          <button
            onClick={handleZoomIn}
            disabled={disabled}
            style={btnStyle(disabled)}
          >
            +
          </button>
          <button
            onClick={handleZoomOut}
            disabled={disabled}
            style={btnStyle(disabled)}
          >
            –
          </button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        {disabled ? (
          <div
            style={{
              fontSize: "0.8rem",
              color: "#555",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px dashed #ddd",
              borderRadius: "4px",
            }}
          >
            {loading ? "Loading map…" : "Select a patch."}
          </div>
        ) : (
          <MapContainer
            style={{ height: "100%", width: "100%" }}
            center={center}
            zoom={6}
            scrollWheelZoom={true}
          >
            <TileLayer url={tileUrl} />
            <SafeFitBounds geo={geo} />
            {patchBounds && (
              <Rectangle
                bounds={patchBounds}
                pathOptions={{ color: "red", weight: 2 }}
              />
            )}
          </MapContainer>
        )}
      </div>
    </section>
  );
}

function btnStyle(disabled) {
  return {
    padding: "2px 6px",
    borderRadius: "3px",
    border: "1px solid #aaa",
    background: disabled ? "#eee" : "#f8f8f8",
    cursor: disabled ? "default" : "pointer",
  };
}
