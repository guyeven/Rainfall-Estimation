import { MapContainer, TileLayer, Rectangle, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function isValidNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

function FitBounds({ geo }) {
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
    map.fitBounds(bounds, { padding: [10, 10] });
  } catch {
    // If Leaflet rejects bounds, just skip fitting
  }

  return null;
}

export default function MapPanel({ geo, loading, zoomFactor, onZoomChange }) {
  const canShow = !!geo && !loading;

  const tileTemplate =
    geo?.tile_url_template ||
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

  let patchBounds = null;
  if (
    geo &&
    isValidNum(geo.patch_lat_min) &&
    isValidNum(geo.patch_lat_max) &&
    isValidNum(geo.patch_lon_min) &&
    isValidNum(geo.patch_lon_max)
  ) {
    patchBounds = [
      [geo.patch_lat_min, geo.patch_lon_min],
      [geo.patch_lat_max, geo.patch_lon_max],
    ];
  }

  const centerLat = isValidNum(geo?.center_lat) ? geo.center_lat : 0;
  const centerLon = isValidNum(geo?.center_lon) ? geo.center_lon : 0;

  const handleZoomOut = () => onZoomChange(zoomFactor * 1.3);
  const handleZoomIn = () => onZoomChange(zoomFactor / 1.3);

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
            type="button"
            onClick={handleZoomIn}
            disabled={!geo || loading}
            style={btnStyle}
          >
            Zoom in
          </button>
          <button
            type="button"
            onClick={handleZoomOut}
            disabled={!geo || loading}
            style={btnStyle}
          >
            Zoom out
          </button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        {!canShow ? (
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
            {loading
              ? "Loading map data…"
              : "Select a patch to view on map."}
          </div>
        ) : (
          <MapContainer
            style={{ height: "100%", width: "100%" }}
            center={[centerLat, centerLon]}
            zoom={6}
            scrollWheelZoom={true}
          >
            <TileLayer url={tileTemplate} />
            <FitBounds geo={geo} />
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

const btnStyle = {
  padding: "2px 6px",
  borderRadius: "3px",
  border: "1px solid #ccc",
  background: "#f8f8f8",
  cursor: "pointer",
};
