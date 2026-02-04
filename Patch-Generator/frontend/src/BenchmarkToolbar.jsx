import React from "react";

export default function BenchmarkToolbar({
  title = "Browse benchmark (JSONL)",
  fileName,
  patchCount,
  selectedCount,
  onPickFile,
  onPickAttrsFile,
  exportDisabled,
  onExportSelectedWithAttrs,
  importReport,
  loadError,
  viewError,
}) {
  return (
    <section style={{ border: "1px solid #ddd", borderRadius: 4, padding: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div style={{ fontWeight: 600 }}>{title}</div>

        <label style={S.picker}>
          <input
            type="file"
            accept=".jsonl,.ndjson,.txt"
            style={{ display: "none" }}
            onChange={(e) => onPickFile?.(e.target.files?.[0] || null)}
          />
          Load JSONL…
        </label>

        <label style={S.picker} title="Merge attributes into the current session">
          <input
            type="file"
            accept=".jsonl,.ndjson,.txt"
            style={{ display: "none" }}
            onChange={(e) => onPickAttrsFile?.(e.target.files?.[0] || null)}
          />
          Read attributes (JSONL)…
        </label>

        <div style={{ fontSize: "0.85rem", color: "#444" }}>
          {fileName ? (
            <>
              <strong>File:</strong> {fileName} · <strong>Patches:</strong> {patchCount} ·{" "}
              <strong>Selected:</strong> {selectedCount}
            </>
          ) : (
            "No file loaded."
          )}
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={exportDisabled}
            onClick={onExportSelectedWithAttrs}
            style={{
              padding: "6px 10px",
              borderRadius: 4,
              border: "1px solid #0077cc",
              background: exportDisabled ? "#c7d9ea" : "#0077cc",
              color: "#fff",
              cursor: exportDisabled ? "not-allowed" : "pointer",
              fontSize: "0.85rem",
            }}
            title={exportDisabled ? "Select at least one patch to export." : ""}
          >
            Save attributes of selected patches (JSONL)
          </button>
        </div>
      </div>

      {importReport && (
        <div
          style={{
            marginTop: 8,
            padding: 8,
            background: importReport.ok ? "#eef7ee" : "#fff7d6",
            border: `1px solid ${importReport.ok ? "#b8e0b8" : "#ffe08a"}`,
            borderRadius: 4,
            fontSize: "0.85rem",
          }}
        >
          <div style={{ fontWeight: 800, marginBottom: 4 }}>
            Read attributes report ({importReport.ok ? "OK" : "ISSUES"})
          </div>
          <div style={{ fontFamily: "monospace", whiteSpace: "pre-wrap" }}>{importReport.summary}</div>
          {importReport.details ? (
            <details style={{ marginTop: 6 }}>
              <summary style={{ cursor: "pointer" }}>Show full details</summary>
              <pre style={S.reportPre}>{importReport.details}</pre>
            </details>
          ) : null}
        </div>
      )}

      {loadError && <div style={{ ...S.banner, ...S.err }}><strong>Load error:</strong> {loadError}</div>}
      {viewError && <div style={{ ...S.banner, ...S.warn }}><strong>View error:</strong> {viewError}</div>}
    </section>
  );
}

const S = {
  picker: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 8px",
    border: "1px solid #aaa",
    borderRadius: 4,
    background: "#f8f8f8",
    cursor: "pointer",
    fontSize: "0.85rem",
  },
  banner: {
    marginTop: 8,
    padding: 8,
    borderRadius: 4,
    fontSize: "0.85rem",
  },
  err: { background: "#ffe4e4", border: "1px solid #ffb3b3" },
  warn: { background: "#fff7d6", border: "1px solid #ffe08a" },
  reportPre: {
    marginTop: 6,
    maxHeight: 260,
    overflow: "auto",
    padding: 8,
    border: "1px solid #ddd",
    borderRadius: 4,
    background: "#fff",
    fontFamily: "monospace",
    fontSize: 12,
    whiteSpace: "pre-wrap",
  },
};
