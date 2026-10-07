
import React, { useEffect, useState } from "react";

function clamp01(x) {
  const v = Number(x);
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function parseNumberOrNull(s) {
  if (s == null) return null;
  const t = String(s).trim();
  if (t === "") return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

function parseFrequencyList(s) {
  const t = String(s ?? "").trim();
  if (t === "") return [];
  return t
    .split(",")
    .map((x) => Number(String(x).trim()))
    .filter((x) => Number.isFinite(x) && x > 0);
}

/**
 * A "regular" editable input:
 * - stores draft string while typing (allows 0, 0., .25, 50, etc.)
 * - commits on blur / Enter / Tab
 * - reverts on invalid commit
 */
function ParamInput({
  label,
  unit,
  help,
  value, // committed number
  onCommit, // (number) => void
}) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    // If upstream value changed (e.g., load defaults), update draft.
    setDraft(String(value));
  }, [value]);

  const commit = () => {
    const parsed = parseNumberOrNull(draft);
    if (parsed == null) {
      setDraft(String(value));
      return;
    }
    onCommit(parsed);
  };

  return (
    <div>
      <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>
        <b>{label}</b> {unit ? <span style={{ color: "#666" }}>({unit})</span> : null}
      </label>
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setDraft(String(value));
        }}
        style={{
          width: "100%",
          padding: "8px 10px",
          border: "1px solid #ccc",
          borderRadius: 6,
          fontSize: 14,
        }}
      />
      {help ? (
        <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>{help}</div>
      ) : null}
    </div>
  );
}

export default function LinkDashboard() {
  // Committed numeric state (source of truth)
  const [params, setParams] = useState({
    w: 10,
    h: 10,
    l: 2,

    inner_cell_frac: 1 / 3,

    theta_total_min: 30,
    theta_total_max: 360,
    theta_mean: 45,
    theta_dev: Math.sqrt(45),

    link_length_min: 5,
    link_pref_min: 10,
    link_pref_max: 15,
    link_length_max: 27,
    length_noise_sigma: 1.0,

    ring_center_scale: 1.0,

    // Frequency/rain model params (kept)
    frequencies_text: "",
    Rmax: 25,
    attenuation_max: 5,
    polarization: "horizontal",
  });

  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");

  const commitParam = (key, v) => {
    setParams((p) => ({ ...p, [key]: v }));
  };

  const generate = async () => {
    setStatus("Generating...");
    setData(null);

    const body = {
      w: Number(params.w),
      h: Number(params.h),
      l: Number(params.l),

      inner_cell_frac: clamp01(params.inner_cell_frac),

      theta_total_min: Number(params.theta_total_min),
      theta_total_max: Number(params.theta_total_max),
      theta_mean: Number(params.theta_mean),
      theta_dev: Number(params.theta_dev),

      link_length_min: Number(params.link_length_min),
      link_pref_min: Number(params.link_pref_min),
      link_pref_max: Number(params.link_pref_max),
      link_length_max: Number(params.link_length_max),
      length_noise_sigma: Number(params.length_noise_sigma),

      ring_center_scale: Number(params.ring_center_scale),

      frequencies: parseFrequencyList(params.frequencies_text),
      Rmax: Number(params.Rmax),
      attenuation_max: Number(params.attenuation_max),
      polarization: params.polarization,
    };

    try {
      const res = await fetch("/generate_links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || "Bad response");
      }
      const json = await res.json();
      setData(json);
      const nCenters = json.points?.length ?? 0;
      const nStar = (json.links || []).filter((l) => l.type === "star").length;
      const nRing = (json.links || []).filter((l) => l.type === "ring").length;
      setStatus(`Generated ${nStar} star links, ${nRing} ring links, ${nCenters} centers`);
    } catch (err) {
      console.error(err);
      setStatus("Error generating links: " + (err?.message ?? String(err)));
    }
  };

  // ---------- Rendering helpers ----------
  const renderSVG = () => {
    if (!data) return null;

    const W = data.w;
    const H = data.h;

    const svgW = 520;
    const svgH = 520;
    const margin = 20;

    const s = Math.min((svgW - 2 * margin) / W, (svgH - 2 * margin) / H);

    const sx = (x) => margin + x * s;
    const sy = (y) => margin + (H - y) * s;

    // patch rectangle size in px
    const pw = W * s;
    const ph = H * s;

    const grid = data.grid;

    const cells = [];
    if (grid && grid.nx && grid.ny) {
      for (let i = 0; i < grid.nx; i++) {
        for (let j = 0; j < grid.ny; j++) {
          const x0 = i * grid.l_w;
          const y0 = j * grid.l_h;
          const x1 = x0 + grid.l_w;
          const y1 = y0 + grid.l_h;

          // outer cell
          cells.push(
            <rect
              key={`cell-${i}-${j}`}
              x={sx(x0)}
              y={sy(y1)}
              width={(x1 - x0) * s}
              height={(y1 - y0) * s}
              fill="none"
              stroke="#ccc"
              strokeWidth={1}
            />
          );

          // inner cell
          const cx = (x0 + x1) / 2;
          const cy = (y0 + y1) / 2;
          const iw = grid.inner_cell_frac * grid.l_w;
          const ih = grid.inner_cell_frac * grid.l_h;
          const ix0 = cx - iw / 2;
          const iy0 = cy - ih / 2;
          const ix1 = cx + iw / 2;
          const iy1 = cy + ih / 2;

          cells.push(
            <rect
              key={`inner-${i}-${j}`}
              x={sx(ix0)}
              y={sy(iy1)}
              width={(ix1 - ix0) * s}
              height={(iy1 - iy0) * s}
              fill="none"
              stroke="#ddd"
              strokeWidth={1}
            />
          );
        }
      }
    }

    return (
      <svg width={svgW} height={svgH} style={{ border: "1px solid #ddd", marginTop: 12 }}>
        {/* Patch boundary */}
        <rect x={margin} y={margin} width={pw} height={ph} fill="none" stroke="black" strokeWidth={2} />

        {/* Grid */}
        {cells}

        {/* Links */}
        {(data.links || []).map((ln) => {
          const [x1, y1] = ln.from_coord;
          const [x2, y2] = ln.to_coord;
          const stroke = ln.type === "ring" ? "blue" : "green";
          const strokeWidth = ln.type === "ring" ? 2.5 : 1.75;
          return (
            <line
              key={`ln-${ln.id}`}
              x1={sx(x1)}
              y1={sy(y1)}
              x2={sx(x2)}
              y2={sy(y2)}
              stroke={stroke}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />
          );
        })}

        {/* Centers */}
        {(data.points || []).map((p) => (
          <circle
            key={`pt-${p.id}`}
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={3.5}
            fill="none"
            stroke="black"
            strokeWidth={1.5}
          />
        ))}
      </svg>
    );
  };

  const renderTable = () => {
    if (!data) return null;
    const links = data.links || [];

    const thtd = {
      padding: "8px 10px",
      borderBottom: "1px solid #e6e6e6",
      fontSize: 12,
      verticalAlign: "top",
      whiteSpace: "nowrap",
    };

    const th = {
      ...thtd,
      position: "sticky",
      top: 0,
      background: "#fafafa",
      zIndex: 1,
      fontWeight: 600,
      borderBottom: "2px solid #ddd",
    };

    return (
      <div style={{ marginTop: 16, border: "1px solid #e6e6e6", borderRadius: 8, overflow: "hidden" }}>
        <div style={{ padding: "10px 12px", borderBottom: "1px solid #e6e6e6", background: "#fcfcfc" }}>
          <b>Links</b>
          <span style={{ color: "#666", marginLeft: 8, fontSize: 12 }}>
            ({links.length})
          </span>
        </div>
        <div style={{ maxHeight: 340, overflow: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "auto" }}>
            <thead>
              <tr>
                <th style={th}>id</th>
                <th style={th}>type</th>
                <th style={th}>from</th>
                <th style={th}>to</th>
                <th style={th}>length (km)</th>
                <th style={th}>assigned (GHz)</th>
                <th style={th}>max allowed (GHz)</th>
              </tr>
            </thead>
            <tbody>
              {links.map((ln) => (
                <tr key={`row-${ln.id}`}>
                  <td style={thtd}>{ln.id}</td>
                  <td style={thtd}>{ln.type}</td>
                  <td style={thtd}>
                    {ln.from_point_id ?? "—"}{" "}
                    <span style={{ color: "#777" }}>
                      ({ln.from_coord[0].toFixed(2)},{ln.from_coord[1].toFixed(2)})
                    </span>
                  </td>
                  <td style={thtd}>
                    {ln.to_point_id ?? "—"}{" "}
                    <span style={{ color: "#777" }}>
                      ({ln.to_coord[0].toFixed(2)},{ln.to_coord[1].toFixed(2)})
                    </span>
                  </td>
                  <td style={{ ...thtd, textAlign: "right" }}>{Number(ln.length).toFixed(3)}</td>
                  <td style={{ ...thtd, textAlign: "right" }}>{ln.assigned_frequency ?? "—"}</td>
                  <td style={{ ...thtd, textAlign: "right" }}>{ln.max_allowed_frequency ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // ---------- UI ----------
  return (
    <div style={{ padding: 18, maxWidth: 980 }}>
      <h2 style={{ margin: 0 }}>Link Generator</h2>
      <div style={{ color: "#666", marginTop: 6, fontSize: 13 }}>
        Patch boundary is black, grid/inner cells are light gray, star links are green, ring links are blue.
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: 12,
          marginTop: 14,
        }}
      >
        <ParamInput label="Patch width w" unit="km" value={params.w} onCommit={(v) => commitParam("w", v)} />
        <ParamInput label="Patch height h" unit="km" value={params.h} onCommit={(v) => commitParam("h", v)} />
        <ParamInput label="Grid scale l" unit="km" help="Used in grid sizing and star-link length scale." value={params.l} onCommit={(v) => commitParam("l", v)} />

        <ParamInput label="Inner cell scale" unit="fraction" value={params.inner_cell_frac} onCommit={(v) => commitParam("inner_cell_frac", v)} />

        <ParamInput label="Min total star angle" unit="deg" value={params.theta_total_min} onCommit={(v) => commitParam("theta_total_min", v)} />
        <ParamInput label="Max total star angle" unit="deg" value={params.theta_total_max} onCommit={(v) => commitParam("theta_total_max", v)} />

        <ParamInput label="Mean per-segment angle" unit="deg" value={params.theta_mean} onCommit={(v) => commitParam("theta_mean", v)} />
        <ParamInput label="Angle deviation" unit="deg" value={params.theta_dev} onCommit={(v) => commitParam("theta_dev", v)} />

        <ParamInput label="Min link length" unit="km" value={params.link_length_min} onCommit={(v) => commitParam("link_length_min", v)} />
        <ParamInput label="Preferred link min" unit="km" value={params.link_pref_min} onCommit={(v) => commitParam("link_pref_min", v)} />
        <ParamInput label="Preferred link max" unit="km" value={params.link_pref_max} onCommit={(v) => commitParam("link_pref_max", v)} />

        <ParamInput label="Max link length" unit="km" value={params.link_length_max} onCommit={(v) => commitParam("link_length_max", v)} />
        <ParamInput label="Star length noise sigma" unit="unitless" help="In L = l * (1 + N(0,sigma))." value={params.length_noise_sigma} onCommit={(v) => commitParam("length_noise_sigma", v)} />

        <ParamInput label="Ring center scale" unit="scalar" help="Ring centers = round(scale*sqrt(l_w*l_h))." value={params.ring_center_scale} onCommit={(v) => commitParam("ring_center_scale", v)} />

        <div style={{ gridColumn: "span 3" }}>
          <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>
            <b>Frequencies</b> <span style={{ color: "#666" }}>(GHz, comma-separated; empty ⇒ 1..100 step 3)</span>
          </label>
          <input
            type="text"
            value={params.frequencies_text}
            onChange={(e) => commitParam("frequencies_text", e.target.value)}
            style={{
              width: "100%",
              padding: "8px 10px",
              border: "1px solid #ccc",
              borderRadius: 6,
              fontSize: 14,
            }}
            placeholder="e.g. 10, 20, 40"
          />
        </div>

        <ParamInput label="Rmax" unit="mm/h" value={params.Rmax} onCommit={(v) => commitParam("Rmax", v)} />
        <ParamInput label="Attenuation max" unit="dB" value={params.attenuation_max} onCommit={(v) => commitParam("attenuation_max", v)} />

        <div>
          <label style={{ display: "block", fontSize: 12, marginBottom: 4 }}>
            <b>Polarization</b>
          </label>
          <select
            value={params.polarization}
            onChange={(e) => commitParam("polarization", e.target.value)}
            style={{
              width: "100%",
              padding: "8px 10px",
              border: "1px solid #ccc",
              borderRadius: 6,
              fontSize: 14,
              background: "white",
            }}
          >
            <option value="horizontal">horizontal</option>
            <option value="vertical">vertical</option>
            <option value="circular">circular</option>
          </select>
          <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>Used in the ITU rain attenuation model.</div>
        </div>
      </div>

      <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10 }}>
        <button
          onClick={generate}
          style={{
            padding: "10px 14px",
            borderRadius: 8,
            border: "1px solid #ccc",
            background: "#fff",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Generate
        </button>
        <div style={{ color: "#444" }}>{status}</div>
      </div>

      {renderSVG()}
      {renderTable()}
    </div>
  );
}
