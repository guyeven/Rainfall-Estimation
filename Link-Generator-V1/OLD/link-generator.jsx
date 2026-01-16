// @ts-nocheck
import { useEffect, useMemo, useState } from "react";

// ==== helpers ====
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function randn() { let u = 0, v = 0; while (u === 0) u = Math.random(); while (v === 0) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }

// ==== ITU-R P.838-3 coefficient param tables (H/V) ====
const kH = { a: [-5.33980, -0.35351, -0.23789, -0.94158], b: [-0.10008, 1.26970, 0.86036, 0.64552], c: [1.13098, 0.45400, 0.15354, 0.16817], m: -0.18961, c0: 0.71147 };
const kV = { a: [-3.80595, -3.44965, -0.39902, 0.50167], b: [0.56934, -0.22911, 0.73042, 1.07319], c: [0.81061, 0.51059, 0.11899, 0.27195], m: -0.16398, c0: 0.63297 };
const aH = { a: [-0.14318, 0.29591, 0.32177, -5.37610, 16.1721], b: [1.82442, 0.77564, 0.63773, -0.96230, -3.29980], c: [-0.55187, 0.19822, 0.13164, 1.47828, 3.43990], m: 0.67849, c0: -1.95537 };
const aV = { a: [-0.07771, 0.56727, -0.20238, -48.2991, 48.5833], b: [2.33840, 0.95545, 1.14520, 0.791669, 0.791459], c: [-0.76284, 0.54039, 0.26809, 0.116226, 0.116479], m: -0.053739, c0: 0.83433 };

function sumExp(x, A, B, C) {
  let s = 0;
  for (let j = 0; j < A.length; j++) {
    const t = (x - B[j]) / C[j];
    s += A[j] * Math.exp(-(t * t));
  }
  return s;
}
function k_from_params(fGHz, P) { const x = Math.log10(fGHz); const log10k = sumExp(x, P.a, P.b, P.c) + P.m * x + P.c0; return Math.pow(10, log10k); }
function alpha_from_params(fGHz, P) { const x = Math.log10(fGHz); return sumExp(x, P.a, P.b, P.c) + P.m * x + P.c0; }
function combineLinear(kHval, kVval, aHval, aVval, thetaDeg, tauDeg) { const th = (thetaDeg * Math.PI) / 180; const tau = (tauDeg * Math.PI) / 180; const c = Math.cos(th) * Math.cos(th) * Math.cos(2 * tau); const k = (kHval + kVval + (kHval - kVval) * c) / 2; const alpha = (kHval * aHval + kVval * aVval + (kHval * aHval - kVval * aVval) * c) / (2 * k); return { k, alpha }; }

export default function App() {
  // ===== 1) Area & pixels (km) =====
  const [widthKm, setWidthKm] = useState(60);
  const [heightKm, setHeightKm] = useState(40);
  const [pixelKm, setPixelKm] = useState(1);

  // ===== 2) Links (only changes here regenerate geometry) =====
  const [nLinks, setNLinks] = useState(300);
  const [lenMode, setLenMode] = useState('uniform'); // 'uniform' | 'exponential'
  const [Luniform, setLuniform] = useState(5);
  const [LexpMean, setLexpMean] = useState(3);
  const [centerMode, setCenterMode] = useState('uniform'); // 'uniform' | 'gaussian'
  const [cxMean, setCxMean] = useState(30);
  const [cyMean, setCyMean] = useState(20);
  const [cStd, setCStd] = useState(10);

  // ===== 3) Frequency assignment (discrete F + reliability rule) =====
  const [fMin, setFMin] = useState(10);
  const [fMax, setFMax] = useState(100);
  const [fStep, setFStep] = useState(5);
  const [Rstar, setRstar] = useState(10);     // mm/h
  const [alphaStar, setAlphaStar] = useState(3); // dB path budget
  const [freqMode, setFreqMode] = useState('rule'); // 'rule' | 'uniform'
  const [uniformFreq, setUniformFreq] = useState(22);

  // ===== 4) Polarization (for k,alpha) =====
  const [pol, setPol] = useState('H'); // 'H' | 'V' | 'Circular'

  // Derived grid
  const cols = Math.max(1, Math.floor(widthKm / pixelKm));
  const rows = Math.max(1, Math.floor(heightKm / pixelKm));

  // k, alpha for chosen polarization
  function kAlpha(fGHz) {
    const kHval = k_from_params(fGHz, kH), kVval = k_from_params(fGHz, kV);
    const aHval = alpha_from_params(fGHz, aH), aVval = alpha_from_params(fGHz, aV);
    if (pol === 'H') return { k: kHval, alpha: aHval };
    if (pol === 'V') return { k: kVval, alpha: aVval };
    return combineLinear(kHval, kVval, aHval, aVval, 0, 45); // Circular
  }

  // Build F = {fMin + i*fStep}
  function buildFreqSet(min, max, step) {
    const lo = Math.max(10, Math.min(min, max));
    const hi = Math.max(lo, max);
    const st = Math.max(1, step);
    const list = [];
    for (let f = lo; f <= hi + 1e-9; f += st) list.push(Math.round(f));
    return list;
  }
  const F = useMemo(() => buildFreqSet(fMin, fMax, fStep), [fMin, fMax, fStep]);

  // Path attenuation func(d,f,R) = gamma(f,R)*d [dB]
  function pathAtten(dKm, fGHz, Rmmph) {
    const { k, alpha } = kAlpha(fGHz);
    const gamma = k * Math.pow(Rmmph, alpha); // dB/km
    return gamma * dKm; // dB
  }

  // Choose frequency for a given link length d (max f in F s.t. γ(f,R*)·d ≤ α*)
  function chooseFreq(dKm) {
    if (freqMode === 'uniform') {
      // snap uniformFreq to nearest in F
      let best = F[0], mind = Infinity;
      for (const f of F) { const dd = Math.abs(f - uniformFreq); if (dd < mind) { mind = dd; best = f; } }
      return best;
    }
    for (let i = F.length - 1; i >= 0; i--) {
      const f = F[i];
      const att = pathAtten(dKm, f, Rstar);
      if (att <= alphaStar) return f; // highest satisfying f
    }
    return F[0]; // fallback
  }

  // ===== Link geometry generation (only when section 2 changes) =====
  const [links, setLinks] = useState([]); // array of {x1,y1,x2,y2,L}
  useEffect(() => {
    function sampleLink() {
      const Ldraw = (lenMode === 'uniform') ? Luniform : Math.max(0.05, -LexpMean * Math.log(1 - Math.random()));
      let cx, cy;
      if (centerMode === 'uniform') { cx = Math.random() * widthKm; cy = Math.random() * heightKm; }
      else { cx = cxMean + cStd * randn(); cy = cyMean + cStd * randn(); cx = clamp(cx, 0, widthKm); cy = clamp(cy, 0, heightKm); }
      const theta = Math.random() * Math.PI;
      const dx = (Ldraw / 2) * Math.cos(theta), dy = (Ldraw / 2) * Math.sin(theta);
      let x1 = clamp(cx - dx, 0, widthKm), y1 = clamp(cy - dy, 0, heightKm);
      let x2 = clamp(cx + dx, 0, widthKm), y2 = clamp(cy + dy, 0, heightKm);
      const L = Math.hypot(x2 - x1, y2 - y1);
      return { x1, y1, x2, y2, L };
    }
    const arr = [];
    for (let i = 0; i < nLinks; i++) arr.push(sampleLink());
    setLinks(arr);
  }, [nLinks, lenMode, Luniform, LexpMean, centerMode, cxMean, cyMean, cStd, widthKm, heightKm]);

  // ===== View / grid =====
  const viewW = 900, viewH = Math.round(viewW * (heightKm / widthKm));
  const gridLines = useMemo(() => {
    const xs = [], ys = [];
    for (let c = 0; c <= cols; c++) xs.push((c * pixelKm) / widthKm * viewW);
    for (let r = 0; r <= rows; r++) ys.push((r * pixelKm) / heightKm * viewH);
    return { xs, ys };
  }, [cols, rows, pixelKm, widthKm, heightKm, viewW, viewH]);

  function freqColor(f) { const denom = Math.max(1, (fMax - fMin)); const t = (clamp(f, fMin, fMax) - fMin) / denom; const hue = 220 * (1 - t); return `hsl(${hue},70%,45%)`; }

  return (
    <div style={{ padding: 16, fontFamily: 'system-ui, sans-serif', maxWidth: 1200, margin: '0 auto' }}>
      <h1>ITU Dashboard Calculator</h1>

      {/* Controls */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
        {/* 1) Area & pixels */}
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <h3>1) Area & Pixels (km)</h3>
          <div>Width: {widthKm.toFixed(1)} km <input type="range" min={10} max={200} step={0.5} value={widthKm} onChange={e => setWidthKm(parseFloat(e.target.value))} /></div>
          <div>Height: {heightKm.toFixed(1)} km <input type="range" min={10} max={200} step={0.5} value={heightKm} onChange={e => setHeightKm(parseFloat(e.target.value))} /></div>
          <div>Pixel size: {pixelKm.toFixed(2)} km <input type="range" min={0.1} max={5} step={0.1} value={pixelKm} onChange={e => setPixelKm(parseFloat(e.target.value))} /></div>
          <div>Grid: {cols} × {rows} pixels</div>
        </div>

        {/* 2) Links */}
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <h3>2) Links</h3>
          <div>Count: {nLinks} <input type="range" min={10} max={3000} step={10} value={nLinks} onChange={e => setNLinks(parseInt(e.target.value))} /></div>

          <div style={{ marginTop: 8 }}><strong>Length distribution</strong></div>
          <label><input type="radio" checked={lenMode==='uniform'} onChange={()=>setLenMode('uniform')} /> Constant length</label>
          {lenMode==='uniform' && (
            <div>Length L: {Luniform.toFixed(2)} km <input type="range" min={0.1} max={Math.max(widthKm,heightKm)} step={0.1} value={Luniform} onChange={e=>setLuniform(parseFloat(e.target.value))} /></div>
          )}
          <label><input type="radio" checked={lenMode==='exponential'} onChange={()=>setLenMode('exponential')} /> Exponential</label>
          {lenMode==='exponential' && (
            <div>Mean length: {LexpMean.toFixed(2)} km <input type="range" min={0.1} max={Math.max(widthKm,heightKm)} step={0.1} value={LexpMean} onChange={e=>setLexpMean(parseFloat(e.target.value))} /></div>
          )}

          <div style={{ marginTop: 8 }}><strong>Link center placement</strong></div>
          <label><input type="radio" checked={centerMode==='uniform'} onChange={()=>setCenterMode('uniform')} /> Uniform</label>
          <label style={{ marginLeft: 12 }}><input type="radio" checked={centerMode==='gaussian'} onChange={()=>setCenterMode('gaussian')} /> Gaussian</label>
          {centerMode==='gaussian' && (
            <div style={{ marginLeft: 12 }}>
              <div>Mean X: {cxMean.toFixed(1)} km <input type="range" min={0} max={widthKm} step={0.5} value={cxMean} onChange={e=>setCxMean(parseFloat(e.target.value))} /></div>
              <div>Mean Y: {cyMean.toFixed(1)} km <input type="range" min={0} max={heightKm} step={0.5} value={cyMean} onChange={e=>setCyMean(parseFloat(e.target.value))} /></div>
              <div>Std (both): {cStd.toFixed(1)} km <input type="range" min={0.1} max={Math.max(widthKm,heightKm)/2} step={0.5} value={cStd} onChange={e=>setCStd(parseFloat(e.target.value))} /></div>
            </div>
          )}
        </div>

        {/* 3) Link frequency */}
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <h3>3) Link frequency</h3>
          <div style={{ marginBottom: 8 }}>
            <div>f_min: {fMin} GHz <input type="range" min={10} max={95} step={5} value={fMin} onChange={e=>setFMin(Math.min(parseFloat(e.target.value), fMax - 5))} /></div>
            <div>f_max: {fMax} GHz <input type="range" min={Math.max(15, fMin + 5)} max={100} step={5} value={fMax} onChange={e=>setFMax(Math.max(parseFloat(e.target.value), fMin + 5))} /></div>
            <div>f_step: {fStep} GHz <input type="range" min={5} max={20} step={5} value={fStep} onChange={e=>setFStep(parseFloat(e.target.value))} /></div>
          </div>
          <label><input type="radio" checked={freqMode==='uniform'} onChange={()=>setFreqMode('uniform')} /> Uniform frequency</label>
          {freqMode==='uniform' && (
            <div>f: {uniformFreq.toFixed(0)} GHz <input type="range" min={fMin} max={fMax} step={fStep} value={uniformFreq} onChange={e=>setUniformFreq(parseFloat(e.target.value))} /></div>
          )}

          <div style={{ marginTop: 6 }}>
            <label><input type="radio" checked={freqMode==='rule'} onChange={()=>setFreqMode('rule')} /> Reliability rule (max f ∈ F s.t. γ(f,R★)·d ≤ α★)</label>
            {freqMode==='rule' && (
              <>
                <div>R★ (mm/h): {Rstar.toFixed(1)} <input type="range" min={0.1} max={100} step={0.1} value={Rstar} onChange={e=>setRstar(parseFloat(e.target.value))} /></div>
                <div>α★ (dB path): {alphaStar.toFixed(2)} <input type="range" min={0.1} max={30} step={0.1} value={alphaStar} onChange={e=>setAlphaStar(parseFloat(e.target.value))} /></div>
              </>
            )}
          </div>

          <div style={{ display:'flex', alignItems:'center', gap:8, fontSize:12, opacity:0.8, marginTop:6, flexWrap:'wrap' }}>
            <div style={{ marginRight: 8 }}>Frequency legend:</div>
            {F.map((f)=> (
              <div key={f} style={{ display:'flex', alignItems:'center', gap:4, marginRight:8, marginBottom:4 }}>
                <div style={{ width:20, height:12, background: freqColor(f) }} />
                <div>{String(f)} GHz</div>
              </div>
            ))}
          </div>
        </div>

        {/* 4) Link polarization */}
        <div style={{ border:'1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <h3>4) Link polarization</h3>
          <label><input type="radio" checked={pol==='H'} onChange={()=>setPol('H')} /> All Horizontal</label>
          <label style={{ marginLeft: 12 }}><input type="radio" checked={pol==='V'} onChange={()=>setPol('V')} /> All Vertical</label>
          <label style={{ marginLeft: 12 }}><input type="radio" checked={pol==='Circular'} onChange={()=>setPol('Circular')} /> All Circular</label>
        </div>
      </div>

      {/* Area plot */}
      <div style={{ marginTop: 16, border: '1px solid #ddd', borderRadius: 8, padding: 8 }}>
        <h3>Area, Pixels, and Links (color = frequency)</h3>
        <svg width={viewW} height={viewH} style={{ background: '#fff' }}>
          {/* grid */}
          {gridLines.xs.map((x,i)=>(<line key={'vx'+i} x1={x} y1={0} x2={x} y2={viewH} stroke="#eee" strokeWidth={1} />))}
          {gridLines.ys.map((y,i)=>(<line key={'hz'+i} x1={0} y1={y} x2={viewW} y2={y} stroke="#eee" strokeWidth={1} />))}
          {/* border */}
          <rect x={0} y={0} width={viewW} height={viewH} fill="none" stroke="#333" strokeWidth={1.5} />
          {/* links */}
          {links.map((L,i)=>{
            const f = chooseFreq(L.L);
            const x1 = (L.x1/widthKm)*viewW, y1=(L.y1/heightKm)*viewH;
            const x2 = (L.x2/widthKm)*viewW, y2=(L.y2/heightKm)*viewH;
            return (<line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={freqColor(f)} strokeWidth={2} />);
          })}
        </svg>
      </div>
    </div>
  );
}
