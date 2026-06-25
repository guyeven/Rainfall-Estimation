// App.jsx
import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API_BASE = "http://127.0.0.1:8000";

const polarizations = [
  { id: "horizontal", label: "Horizontal" },
  { id: "vertical", label: "Vertical" },
  { id: "circular", label: "Circular" },
];

function App() {
  const [freq, setFreq] = useState(10); // GHz
  const [rain, setRain] = useState(10); // mm/h
  const [pol, setPol] = useState("horizontal");

  const [k, setK] = useState(null);
  const [alpha, setAlpha] = useState(null);
  const [gammaCurrent, setGammaCurrent] = useState(null);

  const [freqData, setFreqData] = useState([]);
  const [rainData, setRainData] = useState([]);

  const [hoverFreqPoint, setHoverFreqPoint] = useState(null);
  const [hoverRainPoint, setHoverRainPoint] = useState(null);

  // Fetch gamma(f,R), k(f), alpha(f)
  useEffect(() => {
    const url = new URL(`${API_BASE}/itu/gamma`);
    url.searchParams.set("f_ghz", freq);
    url.searchParams.set("R_mm_per_h", rain);
    url.searchParams.set("pol", pol);

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        setK(data.k);
        setAlpha(data.alpha);
        setGammaCurrent(data.gamma);
      })
      .catch((err) => console.error("Error fetching gamma:", err));
  }, [freq, rain, pol]);

  // gamma vs frequency at fixed R
  useEffect(() => {
    const url = new URL(`${API_BASE}/itu/gamma-freq`);
    url.searchParams.set("R_mm_per_h", rain);
    url.searchParams.set("pol", pol);
    url.searchParams.set("f_min", 1);
    url.searchParams.set("f_max", 100);
    url.searchParams.set("n_points", 100);

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        const points = data.points.map((p) => ({
          f: p.x,
          gamma: p.gamma,
        }));
        setFreqData(points);
      })
      .catch((err) => console.error("Error fetching freq curve:", err));
  }, [rain, pol]);

  // gamma vs rain at fixed f
  useEffect(() => {
    const url = new URL(`${API_BASE}/itu/gamma-rain`);
    url.searchParams.set("f_ghz", freq);
    url.searchParams.set("pol", pol);
    url.searchParams.set("R_min", 0.1);
    url.searchParams.set("R_max", 100);
    url.searchParams.set("n_points", 100);

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        const points = data.points.map((p) => ({
          R: p.x,
          gamma: p.gamma,
        }));
        setRainData(points);
      })
      .catch((err) => console.error("Error fetching rain curve:", err));
  }, [freq, pol]);

  return (
    <div
      style={{
        fontFamily: "system-ui, sans-serif",
        padding: "1.5rem",
        maxWidth: "1200px",
        margin: "0 auto",
      }}
    >
      <h1>ITU Rain Attenuation (Rec. P.838-3)</h1>

      {/* Controls */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "2fr 1fr",
          gap: "1.5rem",
          marginTop: "1rem",
          marginBottom: "1.5rem",
          alignItems: "center",
        }}
      >
        <div>
          <div style={{ marginBottom: "1rem" }}>
            <label>
              <strong>Frequency f (GHz):</strong> {freq.toFixed(1)} GHz
            </label>
            <input
              type="range"
              min={1}
              max={100}
              step={0.5}
              value={freq}
              onChange={(e) => setFreq(parseFloat(e.target.value))}
              style={{ width: "100%" }}
            />
          </div>

          <div>
            <label>
              <strong>Rainfall R (mm/h):</strong> {rain.toFixed(2)} mm/h
            </label>
            <input
              type="range"
              min={0.1}
              max={100}
              step={0.1}
              value={rain}
              onChange={(e) => setRain(parseFloat(e.target.value))}
              style={{ width: "100%" }}
            />
          </div>
        </div>

        <div>
          <div style={{ marginBottom: "0.5rem" }}>
            <strong>Polarization:</strong>
          </div>
          <div style={{ display: "flex", gap: "0.75rem" }}>
            {polarizations.map((p) => (
              <label key={p.id} style={{ cursor: "pointer" }}>
                <input
                  type="radio"
                  name="pol"
                  value={p.id}
                  checked={pol === p.id}
                  onChange={() => setPol(p.id)}
                  style={{ marginRight: "0.35rem" }}
                />
                {p.label}
              </label>
            ))}
          </div>
        </div>
      </section>

      {/* Equation and numbers */}
      <section
        style={{
          padding: "1rem",
          border: "1px solid #ccc",
          borderRadius: "0.5rem",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ marginBottom: "0.5rem" }}>
          <strong>Model:</strong>{" "}
          <code>γ(f,R) = k(f) · R^α(f)</code>, γ in dB/km
        </div>
        <div>
          <strong>At current sliders:</strong>{" "}
          f = {freq.toFixed(2)} GHz,&nbsp; R = {rain.toFixed(2)} mm/h,&nbsp;
          pol = {pol}.
        </div>
        <div>
          k(f) ≈{" "}
          {k !== null ? k.toExponential(4) : "…"}{" "}
          dB / (km · (mm/h)^α)
        </div>
        <div>α(f) ≈ {alpha !== null ? alpha.toFixed(4) : "…"}</div>
        <div>
          γ(f,R) ≈{" "}
          {gammaCurrent !== null ? gammaCurrent.toFixed(4) : "…"}{" "}
          dB/km
        </div>
      </section>

      {/* Plots */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1.5rem",
        }}
      >
        {/* 1: gamma vs frequency */}
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: "0.5rem",
            padding: "0.75rem",
            display: "flex",
            flexDirection: "row",
            gap: "0.75rem",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ marginTop: 0 }}>γ(f,R) vs f @ R = {rain.toFixed(2)} mm/h</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart
                data={freqData}
                margin={{ top: 10, right: 10, left: 0, bottom: 35 }}
                onMouseMove={(state) => {
                  if (
                    state &&
                    state.activePayload &&
                    state.activePayload.length > 0
                  ) {
                    const p = state.activePayload[0].payload;
                    setHoverFreqPoint({ f: p.f, gamma: p.gamma });
                  }
                }}
                onMouseLeave={() => setHoverFreqPoint(null)}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="f"
                  label={{ value: "Frequency (GHz)", position: "insideBottom", offset: -20 }}
                  tickLine
                />
                <YAxis
                  scale="log"
                  domain={["auto", "auto"]}
                  label={{
                    value: "γ(f,R) [dB/km]",
                    angle: -90,
                    position: "insideLeft",
                  }}
                  tickLine
                />
                <Tooltip
                  formatter={(value) => value.toExponential(3)}
                  labelFormatter={(label) => `f = ${label.toFixed(2)} GHz`}
                />
                <Line
                  type="monotone"
                  dataKey="gamma"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Coordinate box */}
          <div
            style={{
              width: "160px",
              borderLeft: "1px solid #ddd",
              paddingLeft: "0.75rem",
              fontSize: "0.9rem",
            }}
          >
            <strong>Point under cursor</strong>
            <div style={{ marginTop: "0.5rem" }}>
              {hoverFreqPoint ? (
                <>
                  <div>f ≈ {hoverFreqPoint.f.toFixed(2)} GHz</div>
                  <div>
                    γ ≈ {hoverFreqPoint.gamma.toExponential(3)} dB/km
                  </div>
                </>
              ) : (
                <div>Move cursor over plot.</div>
              )}
            </div>
          </div>
        </div>

        {/* 2: gamma vs rain */}
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: "0.5rem",
            padding: "0.75rem",
            display: "flex",
            flexDirection: "row",
            gap: "0.75rem",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{ marginTop: 0 }}>γ(f,R) vs R @ f = {freq.toFixed(2)} GHz</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart
                data={rainData}
                margin={{ top: 10, right: 10, left: 0, bottom: 35 }}
                onMouseMove={(state) => {
                  if (
                    state &&
                    state.activePayload &&
                    state.activePayload.length > 0
                  ) {
                    const p = state.activePayload[0].payload;
                    setHoverRainPoint({ R: p.R, gamma: p.gamma });
                  }
                }}
                onMouseLeave={() => setHoverRainPoint(null)}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="R"
                  type="number"
                  scale="log"
                  domain={["auto", "auto"]}
                  label={{ value: "Rain rate R (mm/h)", position: "insideBottom", offset: -20 }}
                  tickLine
                />
                <YAxis
                  scale="log"
                  domain={["auto", "auto"]}
                  label={{
                    value: "γ(f,R) [dB/km]",
                    angle: -90,
                    position: "insideLeft",
                  }}
                  tickLine
                />
                <Tooltip
                  formatter={(value) => value.toExponential(3)}
                  labelFormatter={(label) =>
                    `R = ${Number(label).toFixed(2)} mm/h`
                  }
                />
                <Line
                  type="monotone"
                  dataKey="gamma"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Coordinate box */}
          <div
            style={{
              width: "160px",
              borderLeft: "1px solid #ddd",
              paddingLeft: "0.75rem",
              fontSize: "0.9rem",
            }}
          >
            <strong>Point under cursor</strong>
            <div style={{ marginTop: "0.5rem" }}>
              {hoverRainPoint ? (
                <>
                  <div>R ≈ {hoverRainPoint.R.toFixed(2)} mm/h</div>
                  <div>
                    γ ≈ {hoverRainPoint.gamma.toExponential(3)} dB/km
                  </div>
                </>
              ) : (
                <div>Move cursor over plot.</div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;

