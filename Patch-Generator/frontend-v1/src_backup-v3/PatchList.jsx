
import { formatTimestamp, formatKm, formatMm } from "./utils/formatters";

export default function PatchList({
  patches,
  selectedPatchId,
  selectedPatchIds,
  onRowClick,
  onToggleExportSelection,
  detecting,
}) {
  const safeSelectedIds = Array.isArray(selectedPatchIds)
    ? selectedPatchIds
    : [];

  const handleRowClick = (id) => {
    if (typeof onRowClick === "function") onRowClick(id);
  };

  const handleToggle = (id) => {
    if (typeof onToggleExportSelection === "function") {
      onToggleExportSelection(id);
    }
  };

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
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: "6px",
          alignItems: "baseline",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Patches</h2>
        <span style={{ fontSize: "0.75rem", color: "#555" }}>
          {detecting ? "Running detection…" : `${patches.length || 0} patch(es)`}
        </span>
      </div>

      {!patches.length ? (
        <div style={{ fontSize: "0.8rem", color: "#555" }}>
          No patches loaded. Run detection to see results.
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            border: "1px solid #eee",
            borderRadius: "4px",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8f8f8", fontSize: "0.75rem" }}>
                <th style={thStyle}>Keep</th>
                <th style={thStyle}>Time</th>
                <th style={thStyle}>Size</th>
                <th style={thStyle}>Max (mm)</th>
                <th style={thStyle}>Avg (mm)</th>
                <th style={thStyle}>City</th>
              </tr>
            </thead>
            <tbody>
              {patches.map((p, idx) => {
                const isActive = p.id === selectedPatchId;
                const isMarked = safeSelectedIds.includes(p.id);
                const area =
                  p.area_km2 ??
                  (p.width_km && p.height_km
                    ? p.width_km * p.height_km
                    : null);
                const city = p.nearest_city || "-";
                const maxVal =
                  p.max_rainfall !== undefined ? p.max_rainfall : null;
                const meanVal =
                  p.mean_rainfall !== undefined ? p.mean_rainfall : null;

                return (
                  <tr
                    key={p.id || idx}
                    onClick={() => handleRowClick(p.id)}
                    style={{
                      background: isActive
                        ? "#e6f3ff"
                        : idx % 2 === 0
                        ? "#fff"
                        : "#fafafa",
                      fontSize: "0.78rem",
                      cursor:
                        typeof onRowClick === "function" ? "pointer" : "default",
                    }}
                  >
                    <td style={tdStyle}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggle(p.id);
                        }}
                        style={{
                          fontSize: "0.7rem",
                          padding: "2px 6px",
                          borderRadius: "3px",
                          border: "1px solid #0077cc",
                          background: isMarked ? "#0077cc" : "#fff",
                          color: isMarked ? "#fff" : "#0077cc",
                          cursor:
                            typeof onToggleExportSelection === "function"
                              ? "pointer"
                              : "default",
                        }}
                      >
                        {isMarked ? "✓" : "Select"}
                      </button>
                    </td>
                    <td style={tdStyle}>
                      {p.timestamp ? formatTimestamp(p.timestamp) : "-"}
                    </td>
                    <td style={tdStyle}>
                      {p.width_km && p.height_km
                        ? `${formatKm(p.width_km)} × ${formatKm(p.height_km)}${
                            area ? ` (${area.toFixed(0)} km²)` : ""
                          }`
                        : "-"}
                    </td>
                    <td style={tdStyle}>
                      {maxVal !== null && maxVal !== undefined
                        ? formatMm(maxVal)
                        : "-"}
                    </td>
                    <td style={tdStyle}>
                      {meanVal !== null && meanVal !== undefined
                        ? formatMm(meanVal)
                        : "-"}
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        maxWidth: 140,
                        wordBreak: "break-all",
                      }}
                    >
                      {city}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const thStyle = {
  padding: "4px 6px",
  borderBottom: "1px solid #ddd",
  textAlign: "left",
};

const tdStyle = {
  padding: "3px 6px",
  borderBottom: "1px solid #eee",
  verticalAlign: "top",
};
