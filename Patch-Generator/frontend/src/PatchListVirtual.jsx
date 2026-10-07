import React, { useMemo, useState } from "react";

const ROOT = "__root__";

export default function PatchListVirtual({ patches, selectedPatchId, selectedPatchIds, onRowClick, onToggleExportSelection }) {
  const keep = useMemo(() => new Set(selectedPatchIds || []), [selectedPatchIds]);
  const [collapsed, setCollapsed] = useState({});
  const groups = useMemo(() => {
    const map = new Map();
    for (const patch of patches || []) {
      const parts = String(patch.source_file || "").split("/").filter(Boolean);
      const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : ROOT;
      if (!map.has(folder)) map.set(folder, []);
      map.get(folder).push(patch);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a === ROOT ? -1 : b === ROOT ? 1 : a.localeCompare(b));
  }, [patches]);
  const displayId = (id) => {
    const last = String(id || "").split("/").filter(Boolean).pop() || String(id || "");
    const match = last.match(/(\d{8,14}_patch\d+)/);
    return match ? match[1] : last.split(/[:|#]/).pop().trim();
  };
  return <div style={{ border: "1px solid #ddd", borderRadius: 4, overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
    <div style={{ padding: "6px 8px", borderBottom: "1px solid #eee", fontWeight: 600, fontSize: 13 }}>Patches ({patches.length})</div>
    <div style={{ height: 340, overflowY: "auto" }}>
      {groups.map(([folder, folderPatches]) => {
        const closed = Boolean(collapsed[folder]);
        return <div key={folder}>
          <button type="button" onClick={() => setCollapsed((prev) => ({ ...prev, [folder]: !prev[folder] }))} style={{ width: "100%", border: 0, borderBottom: "1px solid #ddd", padding: "7px 8px", textAlign: "left", background: "#f4f6f8", cursor: "pointer", fontWeight: 700, fontSize: 12 }}>
            {closed ? "▸" : "▾"} {folder === ROOT ? "(root files)" : folder} ({folderPatches.length})
          </button>
          {!closed && folderPatches.map((p, index) => <div key={p.id} onClick={() => onRowClick?.(p.id)} title={p.source_file || p.id} style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 34, padding: "4px 8px 4px 20px", background: p.id === selectedPatchId ? "#eef6ff" : index % 2 ? "#fafafa" : "#fff", borderBottom: "1px solid #f0f0f0", cursor: "pointer", fontSize: 13 }}>
            <input type="checkbox" checked={keep.has(p.id)} onChange={(e) => { e.stopPropagation(); onToggleExportSelection?.(p.id); }} />
            <span style={{ fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{displayId(p.id)}</span>
          </div>)}
        </div>;
      })}
    </div>
    <div style={{ padding: "6px 8px", borderTop: "1px solid #eee", fontSize: 12, color: "#555" }}>Tip: click a folder to collapse · click a patch to view · checkbox to mark for export</div>
  </div>;
}
