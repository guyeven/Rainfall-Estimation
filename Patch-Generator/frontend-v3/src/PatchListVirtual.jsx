import { API_BASE } from "./apiBase";
import React, { useEffect, useMemo, useRef, useState } from "react";

const ROW_H = 34;
const VISIBLE_ROWS = 10;
const OVERSCAN = 4;

export default function PatchListVirtual({
  patches,
  selectedPatchId,
  selectedPatchIds,
  onRowClick,
  onToggleExportSelection,
}) {
  const keep = useMemo(() => new Set(selectedPatchIds || []), [selectedPatchIds]);
  const [scrollTop, setScrollTop] = useState(0);
  const scRef = useRef(null);

  // keep the selected patch roughly in view when it changes
  useEffect(() => {
    const el = scRef.current;
    if (!el || !selectedPatchId) return;
    const idx = patches.findIndex((p) => p.id === selectedPatchId);
    if (idx < 0) return;
    const top = idx * ROW_H;
    const bot = top + ROW_H;
    const viewTop = el.scrollTop;
    const viewBot = el.scrollTop + el.clientHeight;
    if (top < viewTop) el.scrollTop = top;
    else if (bot > viewBot) el.scrollTop = Math.max(0, bot - el.clientHeight);
  }, [selectedPatchId, patches]);

  const totalH = patches.length * ROW_H;
  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
  const end = Math.min(patches.length, start + VISIBLE_ROWS + OVERSCAN * 2);
  const slice = patches.slice(start, end);

  // Prefer showing a short suffix (e.g. "202301312000_patch000") instead of a
  // long/common prefix that is identical across many patches.
  const displayId = (id) => {
    const s = String(id || "");
    // If id looks like a path, keep only the last segment.
    const lastSeg = s.split("/").filter(Boolean).pop() || s;
    // If it contains a recognizable "<timestamp>_patch<nnn>" pattern, use that.
    const m = lastSeg.match(/(\d{8,14}_patch\d+)/);
    if (m) return m[1];
    // Otherwise, try to drop a common prefix delimiter.
    const parts = lastSeg.split(/[:|#]/);
    return (parts[parts.length - 1] || lastSeg).trim();
  };

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 4, overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "6px 8px", borderBottom: "1px solid #eee", fontWeight: 600, fontSize: 13 }}>
        Patches ({patches.length})
      </div>

      <div
        ref={scRef}
        style={{ height: ROW_H * VISIBLE_ROWS, overflowY: "auto", position: "relative" }}
        onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      >
        <div style={{ height: totalH, position: "relative" }}>
          {slice.map((p, i) => {
            const idx = start + i;
            const isSel = p.id === selectedPatchId;
            const isKeep = keep.has(p.id);
            return (
              <div
                key={p.id}
                style={{
                  position: "absolute",
                  top: idx * ROW_H,
                  left: 0,
                  right: 0,
                  height: ROW_H,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "0 8px",
                  background: isSel ? "#eef6ff" : idx % 2 ? "#fafafa" : "#fff",
                  borderBottom: "1px solid #f0f0f0",
                  cursor: "pointer",
                  fontSize: 13,
                }}
                onClick={() => onRowClick?.(p.id)}
                title={p.id}
              >
                <input
                  type="checkbox"
                  checked={isKeep}
                  onChange={(e) => {
                    e.stopPropagation();
                    onToggleExportSelection?.(p.id);
                  }}
                />
                <span style={{ fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {displayId(p.id)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ padding: "6px 8px", borderTop: "1px solid #eee", fontSize: 12, color: "#555" }}>
        Tip: scroll to browse · click to view · checkbox to mark for export
      </div>
    </div>
  );
}
