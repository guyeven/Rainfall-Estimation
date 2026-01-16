import React, { useState } from "react";

const COLORS = [
  "#1f77b4",
  "#ff7f0e",
  "#2ca02c",
  "#d62728",
  "#9467bd",
  "#8c564b",
  "#e377c2",
  "#7f7f7f",
  "#bcbd22",
  "#17becf",
];

const parseList = (s) =>
  s
    .split(",")
    .map((x) => Number(x.trim()))
    .filter((x) => !isNaN(x));

export default function LinkDashboard() {
  const [inputs, setInputs] = useState({
    W: 10,
    H: 10,
    N: 100,
    C: 10,
    pmst: 0.5,
    frequencies: "10,20,40",
    Rmax: 25,
    attenuation_max: 5,
    polarization: "horizontal",
  });

  const [data, setData] = useState(null);
  const [status, setStatus] = useState("");

  const update = (name, value) => {
    setInputs((i) => ({ ...i, [name]: value }));
  };

  const generate = async () => {
    setStatus("Generating...");
    setData(null);

    const body = {
      W: Number(inputs.W),
      H: Number(inputs.H),
      N: Number(inputs.N),
      C: Number(inputs.C),
      pmst: Number(inputs.pmst),
      frequencies: parseList(inputs.frequencies),
      Rmax: Number(inputs.Rmax),
      attenuation_max: Number(inputs.attenuation_max),
      polarization: inputs.polarization,
    };

    try {
      const res = await fetch("/generate_links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) throw new Error("Bad response");

      const json = await res.json();
      setData(json);
      const nCenters = json.points.filter((p) => p.is_center).length;
      const nMst = json.points.filter((p) => p.is_mst_node).length;
      setStatus(
        `Generated ${json.links.length} links, ${nCenters} centers, ${nMst} MST nodes`
      );
    } catch (err) {
      console.error(err);
      setStatus("Error generating links");
    }
  };

  const exportJSON = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "links_points.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const colorForFreq = (freq, freqs) => {
    if (freq == null) return "#888";
    const idx = freqs.indexOf(freq);
    return COLORS[idx % COLORS.length];
  };

  const renderSVG = () => {
    if (!data) return null;

    const W = data.W;
    const H = data.H;
    const w = 400;
    const h = 400;

    const sx = (x) => (x / W) * w;
    const sy = (y) => ((H - y) / H) * h;

    return (
      <svg
        width={w}
        height={h}
        style={{ border: "1px solid #ccc", marginTop: 10 }}
      >
        <rect x={0} y={0} width={w} height={h} fill="none" stroke="black" />

        {data.links.map((ln) => {
          const [x1, y1] = ln.from_coord;
          const [x2, y2] = ln.to_coord;
          const color = colorForFreq(ln.max_allowed_frequency, data.frequencies);
          const strokeWidth = ln.type === "mst" ? 2.5 : 1.5;
          const dash = ln.type === "mst" ? "" : "2,2";
          return (
            <line
              key={ln.link_id}
              x1={sx(x1)}
              y1={sy(y1)}
              x2={sx(x2)}
              y2={sy(y2)}
              stroke={color}
              strokeWidth={strokeWidth}
              strokeDasharray={dash}
            />
          );
        })}

        {data.points.map((p) => {
          const r = p.is_center ? (p.is_mst_node ? 5 : 4) : 3;
          const fill = p.is_center ? "#000" : "#bbb";
          const stroke = p.is_mst_node ? "#ff0000" : "none";
          return (
            <circle
              key={p.index}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={r}
              fill={fill}
              stroke={stroke}
              strokeWidth={p.is_mst_node ? 1.5 : 0}
            />
          );
        })}
      </svg>
    );
  };

  const renderLegend = () => {
    if (!data) return null;

    return (
      <div style={{ marginTop: 10 }}>
        <strong>Link frequency legend (GHz):</strong>
        {data.frequencies.map((f, i) => (
          <div key={f} style={{ display: "flex", alignItems: "center" }}>
            <div
              style={{
                width: 14,
                height: 14,
                background: COLORS[i % COLORS.length],
                marginRight: 6,
              }}
            />
            {f}
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center" }}>
          <div
            style={{
              width: 14,
              height: 14,
              background: "#888",
              marginRight: 6,
            }}
          />
          no feasible frequency
        </div>
        <div style={{ marginTop: 6, fontSize: 12 }}>
          <div>
            <b>Nodes:</b> grey = non-center, black = center, red outline = MST
            node
          </div>
          <div>
            <b>Links:</b> dashed = access (point→center), solid = MST
            (center↔center)
          </div>
        </div>
      </div>
    );
  };

  const renderTable = () => {
    if (!data) return null;

    return (
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          marginTop: 20,
          fontSize: 12,
        }}
      >
        <thead>
          <tr>
            <th>id</th>
            <th>type</th>
            <th>from</th>
            <th>to</th>
            <th>length</th>
            <th>max freq</th>
          </tr>
        </thead>
        <tbody>
          {data.links.map((ln) => (
            <tr key={ln.link_id}>
              <td>{ln.link_id}</td>
              <td>{ln.type}</td>
              <td>{ln.from_index}</td>
              <td>{ln.to_index}</td>
              <td>{ln.length.toFixed(3)}</td>
              <td>{ln.max_allowed_frequency ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>Link Generator Dashboard</h2>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: 10,
          maxWidth: 700,
        }}
      >
        <div>
          <label>
            Patch width W (km)
            <input
              type="number"
              value={inputs.W}
              onChange={(e) => update("W", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Horizontal extent of the rectangular patch in kilometers.
          </div>
        </div>

        <div>
          <label>
            Patch height H (km)
            <input
              type="number"
              value={inputs.H}
              onChange={(e) => update("H", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Vertical extent of the rectangular patch in kilometers.
          </div>
        </div>

        <div>
          <label>
            Number of points N
            <input
              type="number"
              value={inputs.N}
              onChange={(e) => update("N", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Total number of random points sampled uniformly in the patch.
          </div>
        </div>

        <div>
          <label>
            Approx. number of centers C
            <input
              type="number"
              value={inputs.C}
              onChange={(e) => update("C", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Target number of centers. The patch is split into a k×k grid with
            k = ceil(sqrt(C)) and at most one random point in each cell is
            chosen as a center.
          </div>
        </div>

        <div>
          <label>
            MST center fraction pmst
            <input
              type="number"
              step="0.01"
              value={inputs.pmst}
              onChange={(e) => update("pmst", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Probability that each center becomes an MST node. MST links are
            built only between these nodes.
          </div>
        </div>

        <div>
          <label>
            Frequencies (GHz)
            <input
              type="text"
              value={inputs.frequencies}
              onChange={(e) => update("frequencies", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Comma-separated list of candidate link frequencies in GHz, e.g.
            "10,20,40".
          </div>
        </div>

        <div>
          <label>
            Rmax (mm/h)
            <input
              type="number"
              value={inputs.Rmax}
              onChange={(e) => update("Rmax", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Maximum rain rate used in the ITU-R rain attenuation model.
          </div>
        </div>

        <div>
          <label>
            Attenuation max (dB)
            <input
              type="number"
              value={inputs.attenuation_max}
              onChange={(e) => update("attenuation_max", e.target.value)}
              style={{ width: "100%" }}
            />
          </label>
          <div style={{ fontSize: 11 }}>
            Maximum allowed rain attenuation per link. Only frequencies with
            γ(f,Rmax)·length ≤ this threshold are accepted.
          </div>
        </div>

        <div>
          <label>
            Polarization
            <select
              value={inputs.polarization}
              onChange={(e) => update("polarization", e.target.value)}
              style={{ width: "100%" }}
            >
              <option value="horizontal">horizontal</option>
              <option value="vertical">vertical</option>
              <option value="circular">circular</option>
            </select>
          </label>
          <div style={{ fontSize: 11 }}>
            Polarization used by the ITU-R model for specific rain attenuation.
          </div>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <button onClick={generate}>Generate</button>
        <button
          onClick={exportJSON}
          disabled={!data}
          style={{ marginLeft: 10 }}
        >
          Export JSON
        </button>
        <div style={{ marginTop: 6 }}>{status}</div>
      </div>

      {renderSVG()}
      {renderLegend()}
      {renderTable()}
    </div>
  );
}
