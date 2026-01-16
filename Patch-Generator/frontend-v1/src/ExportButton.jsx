
export default function ExportButton({
  selectedPatches,
  detectionParams,
  onImportPatchIds,
}) {
  const hasSelection = selectedPatches && selectedPatches.length > 0;

  const handleExportCsv = () => {
    if (!hasSelection) return;

    const headers = [
      "id",
      "source_file",
      "timestamp",
      "width_km",
      "height_km",
      "area_km2",
      "center_lat",
      "center_lon",
      "max_rainfall",
      "mean_rainfall",
      "nearest_city",
      "x_min",
      "x_max",
      "y_min",
      "y_max",
    ];

    const rows = selectedPatches.map((p) => {
      const area =
        p.area_km2 ??
        (p.width_km && p.height_km ? p.width_km * p.height_km : "");
      return [
        p.id ?? "",
        p.source_file ?? "",
        p.timestamp ?? "",
        p.width_km ?? "",
        p.height_km ?? "",
        area ?? "",
        p.center_lat ?? "",
        p.center_lon ?? "",
        p.max_rainfall ?? "",
        p.mean_rainfall ?? "",
        p.nearest_city ?? "",
        p.x_min ?? "",
        p.x_max ?? "",
        p.y_min ?? "",
        p.y_max ?? "",
      ];
    });

    const csvLines = [
      headers.join(","),
      ...rows.map((r) =>
        r
          .map((field) => {
            const value =
              field === null || field === undefined ? "" : String(field);
            const needsQuotes = /[",\n]/.test(value);
            if (needsQuotes) {
              return `"\${value.replace(/"/g, '""')}"`;
            }
            return value;
          })
          .join(",")
      ),
    ];

    const blob = new Blob([csvLines.join("\n")], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "selected_patches.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportJson = () => {
    if (!hasSelection) return;

    const payload = {
      detection_params: detectionParams || {},
      patches: selectedPatches || [],
    };

    const text = JSON.stringify(payload, null, 2);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "selected_patches.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleFileChange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      // accept either CSV (IDs only) or JSON benchmark
      if (file.name.toLowerCase().endsWith(".json")) {
        try {
          const json = JSON.parse(text);
          const patches = Array.isArray(json.patches) ? json.patches : [];
          const ids = patches.map((p) => p.id).filter(Boolean);
          if (ids.length && typeof onImportPatchIds === "function") {
            onImportPatchIds(ids);
          }
        } catch (err) {
          console.error("Failed to parse JSON benchmark", err);
        }
      } else {
        const ids = parseIdsFromCsv(text);
        if (Array.isArray(ids) && typeof onImportPatchIds === "function") {
          onImportPatchIds(ids);
        }
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: "4px",
        padding: "6px 8px",
        background: "#fff",
        fontSize: "0.8rem",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: "6px",
          marginBottom: "4px",
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={handleExportCsv}
          disabled={!hasSelection}
          style={buttonStyle(hasSelection)}
        >
          Export selected (CSV)
        </button>

        <button
          type="button"
          onClick={handleExportJson}
          disabled={!hasSelection}
          style={buttonStyle(hasSelection)}
        >
          Export selected (JSON)
        </button>

        <label
          style={{
            padding: "6px 8px",
            borderRadius: "4px",
            border: "1px solid #555",
            background: "#fff",
            cursor: "pointer",
          }}
        >
          Load selection (CSV/JSON)
          <input
            type="file"
            accept=".csv,text/csv,application/json,.json"
            onChange={handleFileChange}
            style={{ display: "none" }}
          />
        </label>
      </div>

      <p style={{ margin: "2px 0", fontSize: "0.7rem", color: "#555" }}>
        CSV includes bbox (x_min, x_max, y_min, y_max) so you can reconstruct
        patches from HDF5. JSON stores detection params + full patch metadata.
      </p>
      <p style={{ margin: "2px 0", fontSize: "0.7rem", color: "#555" }}>
        Selected: {selectedPatches?.length ?? 0}
      </p>
    </section>
  );
}

function buttonStyle(enabled) {
  return {
    padding: "6px 8px",
    fontSize: "0.8rem",
    borderRadius: "4px",
    border: "1px solid #555",
    background: enabled ? "#444" : "#eee",
    color: "#fff",
    cursor: enabled ? "pointer" : "default",
  };
}

function parseIdsFromCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length < 2) return [];

  const header = lines[0].split(",");
  const idIndex = header.findIndex(
    (h) => h.trim().toLowerCase() === "id"
  );
  if (idIndex === -1) return [];

  const ids = [];
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    const raw = parts[idIndex] ?? "";
    const value = raw.replace(/^"(.*)"$/, "$1").replace(/""/g, '"').trim();
    if (value) ids.push(value);
  }
  return ids;
}
