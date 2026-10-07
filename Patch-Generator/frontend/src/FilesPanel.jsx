import { API_BASE } from "./apiBase";
import { formatTimestamp } from "./utils/formatters";
import { useState } from "react";

export default function FilesPanel({
  files,
  loading,
  error,
  selectedFiles,
  onToggleFile,
  onSelectNone,
  onSelectLatest,
  onRefresh,
}) {
  const [collapsedFolders, setCollapsedFolders] = useState({});
  const groups = (files || []).reduce((map, f) => {
    const path = f.filepath || f.path || f;
    const parts = String(path).split("/");
    const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : "(root files)";
    if (!map[folder]) map[folder] = [];
    map[folder].push(f);
    return map;
  }, {});

  const toggleFolder = (folder) => {
    const paths = (groups[folder] || []).map((f) => f.filepath || f.path || f);
    const allSelected = paths.every((path) => selectedFiles.includes(path));
    paths.forEach((path) => {
      if (allSelected === selectedFiles.includes(path)) onToggleFile(path);
    });
  };

  const renderBody = () => {
    if (loading) return <div>Loading file list…</div>;
    if (error) return <div style={{ color: "red" }}>Failed to load files.</div>;
    if (!files || !files.length) return <div>No files available.</div>;

    return (
      <div
        style={{
          maxHeight: 220,
          overflow: "auto",
          border: "1px solid #ddd",
          borderRadius: "4px",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f8f8f8", position: "sticky", top: 0 }}>
              <th style={thStyle}>Use</th>
              <th style={thStyle}>File</th>
              <th style={thStyle}>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(groups).flatMap(([folder, folderFiles]) => [
              <tr key={`folder-${folder}`} style={{ background: "#eef3f8" }}>
                <td style={tdStyle}>
                  <button type="button" onClick={() => setCollapsedFolders((prev) => ({ ...prev, [folder]: !prev[folder] }))} style={buttonSm}>
                    {collapsedFolders[folder] ? "▸" : "▾"}
                  </button>{" "}
                  <button type="button" onClick={() => toggleFolder(folder)} style={buttonSm}>Select folder</button>
                </td>
                <td colSpan={2} style={{ ...tdStyle, fontWeight: 700 }}>{folder} ({folderFiles.length})</td>
              </tr>,
              ...(collapsedFolders[folder] ? [] : folderFiles.map((f, idx) => {
              const path = f.filepath || f.path || f;
              const ts = f.timestamp || f.time || null;
              const selected = selectedFiles.includes(path);
              return (
                <tr
                  key={path || idx}
                  style={{
                    background: idx % 2 === 0 ? "#fff" : "#fafafa",
                    fontSize: "0.8rem",
                  }}
                >
                  <td style={tdStyle}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => onToggleFile(path)}
                    />
                  </td>
                  <td style={{ ...tdStyle, wordBreak: "break-all" }}>{path}</td>
                  <td style={tdStyle}>{ts ? formatTimestamp(ts) : "-"}</td>
                </tr>
              );
              })),
            ])}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <section
      style={{
        border: "1px solid #ddd",
        borderRadius: "4px",
        padding: "8px",
        background: "#fff",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: "6px",
          gap: "6px",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Files</h2>
        <div style={{ display: "flex", gap: "4px" }}>
          <button
            type="button"
            onClick={() => onSelectLatest(5)}
            style={buttonSm}
          >
            Latest 5
          </button>
          <button
            type="button"
            onClick={() => onSelectLatest(10)}
            style={buttonSm}
          >
            Latest 10
          </button>
          <button type="button" onClick={onSelectNone} style={buttonSm}>
            Clear (auto)
          </button>
          <button type="button" onClick={onRefresh} style={buttonSm}>
            ↻
          </button>
        </div>
      </div>
      <p style={{ margin: "0 0 6px", fontSize: "0.75rem", color: "#555" }}>
        If you select no files, the backend automatically uses the newest{" "}
        <code>max_files</code> rainfall files.
      </p>
      {renderBody()}
    </section>
  );
}

const thStyle = {
  padding: "4px 6px",
  borderBottom: "1px solid #ddd",
  textAlign: "left",
  fontSize: "0.75rem",
  position: "sticky",
  top: 0,
  zIndex: 1,
};

const tdStyle = {
  padding: "3px 6px",
  borderBottom: "1px solid #eee",
  verticalAlign: "top",
};

const buttonSm = {
  fontSize: "0.7rem",
  padding: "2px 6px",
  borderRadius: "3px",
  border: "1px solid #ccc",
  background: "#f7f7f7",
  cursor: "pointer",
};
