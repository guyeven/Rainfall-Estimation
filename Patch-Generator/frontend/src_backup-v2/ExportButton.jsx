
export default function ExportButton({ selectedPatches, onImportPatchIds }) {
  const hasSelection = selectedPatches && selectedPatches.length > 0;

  const handleExport = () => {
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

  const handleFileChange = (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const ids = parseIdsFromCsv(text);
      if (Array.isArray(ids) && typeof onImportPatchIds === "function") {
        onImportPatchIds(ids);
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
      <div style={{ display: "flex", gap: "6px", marginBottom: "4px" }}>
        <button
          type="button"
          onClick={handleExport}
          disabled={!hasSelection}
          style={{
            padding: "6px 8px",
            fontSize: "0.8rem",
            borderRadius: "4px",
            border: "1px solid #555",
            background: hasSelection ? "#444" : "#eee",
            color: "#fff",
            cursor: hasSelection ? "pointer" : "default",
          }}
        >
          Export selected (CSV)
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
          Load selection (CSV)
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            style={{ display: "none" }}
          />
        </label>
      </div>

      <p style={{ margin: "2px 0", fontSize: "0.7rem", color: "#555" }}>
        CSV opens in Excel. Exported file includes patch IDs so you can reload
        a benchmark selection later.
      </p>
      <p style={{ margin: "2px 0", fontSize: "0.7rem", color: "#555" }}>
        Selected: {selectedPatches?.length ?? 0}
      </p>
    </section>
  );
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
