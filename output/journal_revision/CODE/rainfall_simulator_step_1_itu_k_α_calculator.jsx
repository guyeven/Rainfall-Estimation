import React, { useMemo, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

// --- ITU-R P.838-3 coefficient tables (Tables 1–4) ---
// log10(k) = sum_j a_j * exp(-((log10 f - b_j)/c_j)^2) + m_k * log10 f + c_k
//  alpha   = sum_j a_j * exp(-((log10 f - b_j)/c_j)^2) + m_a * log10 f + c_a
// f in GHz, k in (dB/km)/(mm/h)^alpha

const kH_params = {
  a: [-5.33980, -0.35351, -0.23789, -0.94158],
  b: [-0.10008, 1.26970, 0.86036, 0.64552],
  c: [1.13098, 0.45400, 0.15354, 0.16817],
  m: -0.18961,
  c0: 0.71147,
};

const kV_params = {
  a: [-3.80595, -3.44965, -0.39902, 0.50167],
  b: [0.56934, -0.22911, 0.73042, 1.07319],
  c: [0.81061, 0.51059, 0.11899, 0.27195],
  m: -0.16398,
  c0: 0.63297,
};

const aH_params = {
  a: [-0.14318, 0.29591, 0.32177, -5.37610, 16.1721],
  b: [1.82442, 0.77564, 0.63773, -0.96230, -3.29980],
  c: [-0.55187, 0.19822, 0.13164, 1.47828, 3.43990],
  m: 0.67849,
  c0: -1.95537,
};

const aV_params = {
  a: [-0.07771, 0.56727, -0.20238, -48.2991, 48.5833],
  b: [2.33840, 0.95545, 1.14520, 0.791669, 0.791459],
  c: [-0.76284, 0.54039, 0.26809, 0.116226, 0.116479],
  m: -0.053739,
  c0: 0.83433,
};

function sumExp(log10f: number, a: number[], b: number[], c: number[]) {
  let s = 0;
  for (let j = 0; j < a.length; j++) {
    const t = (log10f - b[j]) / c[j];
    s += a[j] * Math.exp(-(t * t));
  }
  return s;
}

function k_from_params(fGHz: number, P: typeof kH_params) {
  const x = Math.log10(fGHz);
  const log10k = sumExp(x, P.a, P.b, P.c) + P.m * x + P.c0;
  return Math.pow(10, log10k);
}

function alpha_from_params(fGHz: number, P: typeof aH_params) {
  const x = Math.log10(fGHz);
  return sumExp(x, P.a, P.b, P.c) + P.m * x + P.c0;
}

function combineLinear(kH: number, kV: number, aH: number, aV: number, thetaDeg: number, tauDeg: number) {
  const th = (thetaDeg * Math.PI) / 180;
  const tau = (tauDeg * Math.PI) / 180;
  const c = Math.cos(th) ** 2 * Math.cos(2 * tau);
  const k = (kH + kV + (kH - kV) * c) / 2;
  const alpha = (kH * aH + kV * aV + (kH * aH - kV * aV) * c) / (2 * k);
  return { k, alpha };
}

export default function RainSimStep1() {
  const [f, setF] = useState(22.0); // GHz
  const [mode, setMode] = useState<"H" | "V" | "Linear" | "Circular">("H");
  const [theta, setTheta] = useState(0); // path elevation angle in degrees
  const [tau, setTau] = useState(0); // polarization tilt angle (deg), 45 for circular
  const [R, setR] = useState(10); // rainfall rate (mm/h)

  const baseCoeffs = useMemo(() => {
    const kH = k_from_params(f, kH_params);
    const kV = k_from_params(f, kV_params);
    const aH = alpha_from_params(f, aH_params);
    const aV = alpha_from_params(f, aV_params);
    return { kH, kV, aH, aV };
  }, [f]);

  function kAlphaAt(fGHz: number) {
    const kH = k_from_params(fGHz, kH_params);
    const kV = k_from_params(fGHz, kV_params);
    const aH = alpha_from_params(fGHz, aH_params);
    const aV = alpha_from_params(fGHz, aV_params);
    if (mode === "H") return { k: kH, alpha: aH };
    if (mode === "V") return { k: kV, alpha: aV };
    const t = mode === "Circular" ? 45 : tau;
    return combineLinear(kH, kV, aH, aV, theta, t);
  }

  const values = useMemo(() => {
    const { kH, kV, aH, aV } = baseCoeffs;
    if (mode === "H") return { k: kH, alpha: aH, kH, kV, aH, aV };
    if (mode === "V") return { k: kV, alpha: aV, kH, kV, aH, aV };
    const t = mode === "Circular" ? 45 : tau;
    const { k, alpha } = combineLinear(kH, kV, aH, aV, theta, t);
    return { k, alpha, kH, kV, aH, aV };
  }, [baseCoeffs, mode, theta, tau]);

  // Data for plots
  const freqSweepData = useMemo(() => {
    const data = [] as { f: number; gamma: number }[];
    for (let F = 1; F <= 100; F += 1) {
      const { k, alpha } = kAlphaAt(F);
      const gamma = k * Math.pow(R, alpha); // dB/km
      data.push({ f: F, gamma });
    }
    return data;
  }, [R, mode, theta, tau]);

  const rainSweepData = useMemo(() => {
    const { k, alpha } = kAlphaAt(f);
    const rates = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 50, 70, 100];
    return rates.map((r) => ({ R: r, gamma: k * Math.pow(r, alpha) }));
  }, [f, mode, theta, tau]);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">ITU Dashboard and Calculator</h1>
      <p className="opacity-80">Interactive coefficients and specific attenuation (γ = k·R^α) per ITU-R P.838-3. Choose frequency, polarization, geometry, and rainfall.</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 rounded-2xl shadow bg-white/50 space-y-3">
          <label className="block text-sm font-medium">Frequency f (GHz): {f.toFixed(2)}</label>
          <input type="range" min={1} max={100} step={0.1} value={f} onChange={(e) => setF(parseFloat(e.target.value))} />

          <label className="block text-sm font-medium">Polarization</label>
          <div className="flex gap-2 flex-wrap">
            {["H", "V", "Linear", "Circular"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m as any)}
                className={`px-3 py-1 rounded-full border ${mode === m ? "bg-black text-white" : "bg-white"}`}
              >
                {m}
              </button>
            ))}
          </div>

          {mode !== "H" && mode !== "V" && (
            <>
              <label className="block text-sm font-medium">Path elevation θ (deg): {theta}</label>
              <input type="range" min={0} max={90} step={1} value={theta} onChange={(e) => setTheta(parseInt(e.target.value))} />

              {mode === "Linear" && (
                <>
                  <label className="block text-sm font-medium">Tilt τ (deg): {tau}</label>
                  <input type="range" min={-90} max={90} step={1} value={tau} onChange={(e) => setTau(parseInt(e.target.value))} />
                </>
              )}
            </>
          )}

          <label className="block text-sm font-medium mt-2">Rainfall rate R (mm/h): {R}</label>
          <input type="range" min={0.1} max={100} step={0.1} value={R} onChange={(e) => setR(parseFloat(e.target.value))} />
        </div>

        <div className="p-4 rounded-2xl shadow bg-white/50 space-y-2">
          <h2 className="font-semibold">Results</h2>
          <div className="text-sm opacity-80">(k in (dB/km)/(mm/h)^α, γ in dB/km)</div>
          <div className="grid grid-cols-2 gap-2 text-sm mt-2">
            <div className="p-3 rounded-xl bg-white">k: <span className="font-mono">{values.k.toPrecision(6)}</span></div>
            <div className="p-3 rounded-xl bg-white">α: <span className="font-mono">{values.alpha.toFixed(4)}</span></div>
            <div className="p-3 rounded-xl bg-white">k_H: <span className="font-mono">{values.kH.toPrecision(6)}</span></div>
            <div className="p-3 rounded-xl bg-white">k_V: <span className="font-mono">{values.kV.toPrecision(6)}</span></div>
            <div className="p-3 rounded-xl bg-white">α_H: <span className="font-mono">{values.aH.toFixed(4)}</span></div>
            <div className="p-3 rounded-xl bg-white">α_V: <span className="font-mono">{values.aV.toFixed(4)}</span></div>
          </div>
          <p className="text-xs opacity-60 mt-2">Tip: R is rainfall in mm/h. γ is specific attenuation in dB/km.</p>
        </div>
      </div>

      <div className="p-4 rounded-2xl bg-white/50 space-y-4">
        <h3 className="font-semibold mb-1">Attenuation Plots</h3>
        <div className="grid grid-cols-1 gap-6">
          <div className="p-3 rounded-2xl bg-white">
            <h4 className="font-medium mb-1">γ(f) at fixed R = {R} mm/h</h4>
            <div className="h-60">
              <ResponsiveContainer>
                <LineChart data={freqSweepData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="f" label={{ value: "Frequency (GHz)", position: "insideBottom", offset: -2 }} />
                  <YAxis label={{ value: "γ (dB/km)", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(v: any) => [Number(v).toFixed(4), "γ (dB/km)"]} />
                  <Line type="monotone" dataKey="gamma" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="p-3 rounded-2xl bg-white">
            <h4 className="font-medium mb-1">γ(R) at fixed f = {f.toFixed(2)} GHz</h4>
            <div className="h-60">
              <ResponsiveContainer>
                <LineChart data={rainSweepData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="R" label={{ value: "Rain rate (mm/h)", position: "insideBottom", offset: -2 }} />
                  <YAxis label={{ value: "γ (dB/km)", angle: -90, position: "insideLeft" }} />
                  <Tooltip formatter={(v: any) => [Number(v).toFixed(4), "γ (dB/km)"]} />
                  <Line type="monotone" dataKey="gamma" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

