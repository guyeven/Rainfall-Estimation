import React, { useEffect, useMemo, useState } from "react";
import { API_BASE } from "./apiBase";

function fmtNum(v) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e4 || (Math.abs(n) > 0 && Math.abs(n) < 1e-3)) return n.toExponential(3);
  return n.toFixed(3);
}

function chooseTickStep(n) {
  if (!n || n <= 0) return 1;
  if (n <= 96) return 16;
  if (n <= 192) return 32;
  if (n <= 384) return 64;
  return 128;
}

function makeTicks(n) {
  const step = chooseTickStep(n);
  const ticks = [];
  for (let t = 0; t <= n - 1; t += step) ticks.push(t);
  if (ticks.length === 0 || ticks[ticks.length - 1] !== n - 1) ticks.push(n - 1);
  return ticks;
}

function StatBlock({ title, stats }) {
  const l1 = stats?.l1;
  const linf = stats?.linf;
  const l1hw = stats?.l1_per_hw ?? stats?.l1_per_area; // be robust
  const shape = stats?.shape_refined;

  return (
    <div style={{ fontSize: 12, lineHeight: 1.35 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div>L¹: <span style={{ fontFamily: "monospace" }}>{fmtNum(l1)}</span></div>
      <div>L∞: <span style={{ fontFamily: "monospace" }}>{fmtNum(linf)}</span></div>
      <div>L¹/(h·w): <span style={{ fontFamily: "monospace" }}>{fmtNum(l1hw)}</span></div>
      <div>shape: <span style={{ fontFamily: "monospace" }}>{shape ? `${shape[0]}×${shape[1]}` : "—"}</span></div>
    </div>
  );
}

function Legend({ vmin, vmax }) {
  // Approximate viridis gradient
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
      <span style={{ fontFamily: "monospace" }}>{fmtNum(vmin)}</span>
      <div
        style={{
          height: 10,
          width: 220,
          borderRadius: 4,
          border: "1px solid #ccc",
          background: "linear-gradient(90deg, #440154, #3b528b, #21918c, #5ec962, #fde725)",
        }}
      />
      <span style={{ fontFamily: "monospace" }}>{fmtNum(vmax)}</span>
      <span style={{ marginLeft: 8, color: "#555" }}>mm</span>
    </div>
  );
}

function AxisY({ heightPx, n, ticks }) {
  // Render tick labels in a separate column, aligned to the image height
  return (
    <div style={{ width: 34, position: "relative", height: heightPx }}>
      {ticks.map((t) => {
        const y = (t / Math.max(1, n - 1)) * heightPx;
        return (
          <div
            key={t}
            style={{
              position: "absolute",
              top: y - 6,
              right: 0,
              fontSize: 10,
              color: "#333",
              fontFamily: "monospace",
              lineHeight: "12px",
              userSelect: "none",
            }}
          >
            {t}
          </div>
        );
      })}
      {/* axis label */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          color: "#555",
          fontSize: 10,
          writingMode: "vertical-rl",
          transform: "rotate(180deg)",
          userSelect: "none",
        }}
      >
        y (refined-px)
      </div>
    </div>
  );
}

function AxisX({ widthPx, n, ticks }) {
  return (
    <div style={{ marginLeft: 34, width: widthPx, position: "relative", height: 18 }}>
      {ticks.map((t) => {
        const x = (t / Math.max(1, n - 1)) * widthPx;
        return (
          <div
            key={t}
            style={{
              position: "absolute",
              left: x - 6,
              top: 0,
              fontSize: 10,
              color: "#333",
              fontFamily: "monospace",
              userSelect: "none",
            }}
          >
            {t}
          </div>
        );
      })}
      <div style={{ position: "absolute", right: 0, bottom: 0, color: "#555", fontSize: 10, userSelect: "none" }}>
        x (refined-px)
      </div>
    </div>
  );
}

function ImageCard({ title, src, shape, stats, showLegend, legendVmin, legendVmax }) {
  const h = shape?.[0] || 0;
  const w = shape?.[1] || 0;
  // We display the image scaled, but ticks align to the displayed box.
  // Choose a max display size so small patches are still visible.
  const maxW = 340;
  const maxH = 340;
  const scale = w > 0 && h > 0 ? Math.min(maxW / w, maxH / h, 1.0) : 1.0;
  const dispW = Math.max(1, Math.round(w * scale));
  const dispH = Math.max(1, Math.round(h * scale));

  const xTicks = useMemo(() => makeTicks(w || 0), [w]);
  const yTicks = useMemo(() => makeTicks(h || 0), [h]);

  return (
    <div
      style={{
        flex: 1,
        border: "1px solid #ddd",
        borderRadius: 6,
        padding: 10,
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minWidth: 260,
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 14 }}>{title}</div>

      {showLegend && (
        <div style={{ marginTop: 2, marginBottom: 2 }}>
          <Legend vmin={legendVmin} vmax={legendVmax} />
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "row", alignItems: "stretch", gap: 6 }}>
        <AxisY heightPx={dispH} n={h} ticks={yTicks} />
        <div style={{ width: dispW, height: dispH, border: "1px solid #eee", borderRadius: 4, overflow: "hidden" }}>
          {src ? (
            <img
              src={src}
              alt={title}
              style={{ width: "100%", height: "100%", objectFit: "fill", imageRendering: "pixelated" }}
            />
          ) : (
            <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "#777" }}>
              —
            </div>
          )}
        </div>
      </div>
      <AxisX widthPx={dispW} n={w} ticks={xTicks} />

      <div style={{ marginTop: 6 }}>
        <StatBlock title="Stats" stats={stats} />
      </div>
    </div>
  );
}

export default function BenchmarkPanel({ apiBase = API_BASE }) {
  const [fileContent, setFileContent] = useState(null);
  const [patchIds, setPatchIds] = useState([]);
  const [selectedPatchId, setSelectedPatchId] = useState(null);
  const [method, setMethod] = useState("gaussian");
  const [bsplineIterations, setBsplineIterations] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [rawUrl, setRawUrl] = useState("");
  const [smoothUrl, setSmoothUrl] = useState("");
  const [diffUrl, setDiffUrl] = useState("");

  const [stats, setStats] = useState(null);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const json = JSON.parse(String(evt.target.result || ""));
        setFileContent(json);
        setError("");
      } catch (err) {
        setError("JSON parse error: " + (err?.message || String(err)));
      }
    };
    reader.readAsText(file);
  };

  const handleLoadPatches = async () => {
    if (!fileContent) {
      setError("Please choose a selected_patches.json file first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${apiBase}/benchmark/load_patches`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fileContent),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(`HTTP ${res.status} – ${msg}`);
      }
      const data = await res.json();
      const ids = data.patch_ids || [];
      setPatchIds(ids);
      setSelectedPatchId(ids[0] || null);
      setStats(null);
    } catch (err) {
      setError("Backend /benchmark/load_patches failed: " + (err?.message || String(err)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedPatchId) {
      setRawUrl("");
      setSmoothUrl("");
      setDiffUrl("");
      setStats(null);
      return;
    }

    const id = encodeURIComponent(selectedPatchId);
    const ts = Date.now();

    // For Gaussian there is no sigma parameter in UI; for B-spline send iterations
    const param = method === "bspline" ? `&max_components=${encodeURIComponent(bsplineIterations)}` : "";

    setRawUrl(`${apiBase}/benchmark/patch_image/${id}?method=${encodeURIComponent(method)}${param}&t=${ts}`);
    setSmoothUrl(`${apiBase}/benchmark/smooth_image/${id}?method=${encodeURIComponent(method)}${param}&t=${ts}`);
    setDiffUrl(`${apiBase}/benchmark/diff_image/${id}?method=${encodeURIComponent(method)}${param}&t=${ts}`);

    const fetchStats = async () => {
      try {
        const res = await fetch(`${apiBase}/benchmark/stats/${id}?method=${encodeURIComponent(method)}${param}`);
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(`HTTP ${res.status} – ${msg}`);
        }
        const data = await res.json();
        setStats(data);
      } catch (err) {
        console.error(err);
        setStats(null);
      }
    };

    fetchStats();
  }, [selectedPatchId, method, bsplineIterations, apiBase]);

  const meta = stats?.meta || {};
  const vmin = meta.vmin;
  const vmax = meta.vmax;

  const rawStats = stats?.raw || null;
  const smoothStats = stats?.smooth || null;
  const diffStats = stats?.diff || null;

  // Shapes are on refined grid for all three (backend contract)
  const rawShape = rawStats?.shape_refined;
  const smoothShape = smoothStats?.shape_refined;
  const diffShape = diffStats?.shape_refined;

  return (
    <div style={{ display: "flex", gap: 16, height: "100%", boxSizing: "border-box" }}>
      {/* Sidebar */}
      <div style={{ width: 280, borderRight: "1px solid #ddd", padding: 10, boxSizing: "border-box", overflowY: "auto" }}>
        <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 8 }}>Smoothing benchmark</div>

        <div style={{ fontSize: 12, color: "#555", marginBottom: 8 }}>
          Load <span style={{ fontFamily: "monospace" }}>selected_patches.json</span> from the main app.
        </div>

        <input type="file" accept=".json" onChange={handleFileChange} style={{ marginBottom: 8 }} />
        <div>
          <button
            onClick={handleLoadPatches}
            disabled={!fileContent || loading}
            style={{ padding: "6px 10px", border: "1px solid #888", borderRadius: 6, background: "#f4f4f4", cursor: "pointer" }}
          >
            {loading ? "Loading..." : "Load patches"}
          </button>
        </div>

        <div style={{ marginTop: 10, fontSize: 12 }}>Loaded patches: {patchIds.length}</div>

        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Method</div>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #ccc" }}
          >
            <option value="gaussian">Gaussian Filter (server σ=1 refined-px)</option>
            <option value="bspline">B-spline</option>
          </select>

          {method === "bspline" && (
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 700 }}># iterations</div>
              <input
                type="number"
                min={1}
                max={20}
                step={1}
                value={bsplineIterations}
                onChange={(e) => {
                  const v = Math.round(Number(e.target.value) || 1);
                  setBsplineIterations(Math.max(1, Math.min(20, v)));
                }}
                style={{ width: 70, padding: "6px 8px", borderRadius: 6, border: "1px solid #ccc" }}
              />
            </div>
          )}
        </div>

        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Patches</div>
          <div style={{ maxHeight: "50vh", overflowY: "auto", border: "1px solid #eee", borderRadius: 6, padding: 6 }}>
            {patchIds.length === 0 && <div style={{ fontSize: 12, color: "#777" }}>No patches loaded.</div>}
            {patchIds.map((pid) => (
              <div
                key={pid}
                onClick={() => setSelectedPatchId(pid)}
                style={{
                  padding: "6px 8px",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: 12,
                  marginBottom: 4,
                  background: pid === selectedPatchId ? "#e6f0ff" : "transparent",
                  wordBreak: "break-all",
                }}
              >
                {pid}
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ marginTop: 12, padding: 8, border: "1px solid #ffb3b3", background: "#ffe6e6", borderRadius: 6, fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>

      {/* Main */}
      <div style={{ flex: 1, padding: 10, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ fontSize: 13 }}>
            Selected: <span style={{ fontFamily: "monospace" }}>{selectedPatchId || "—"}</span>
          </div>
          {/* Shared legend for this patch */}
          {vmin !== undefined && vmax !== undefined && <Legend vmin={vmin} vmax={vmax} />}
        </div>

        <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0, overflowX: "auto" }}>
          <ImageCard
            title={meta.raw_title || "Raw (refined grid)"}
            src={rawUrl}
            shape={rawShape}
            stats={rawStats}
            showLegend={false}
          />
          <ImageCard
            title={meta.smooth_title || "Smoothed (sigma=1 refined-px)"}
            src={smoothUrl}
            shape={smoothShape}
            stats={smoothStats}
            showLegend={false}
          />
          <ImageCard
            title={meta.diff_title || "Difference (SMOOTH - refinedRAW)"}
            src={diffUrl}
            shape={diffShape}
            stats={diffStats}
            showLegend={false}
          />
        </div>
      </div>
    </div>
  );
}
