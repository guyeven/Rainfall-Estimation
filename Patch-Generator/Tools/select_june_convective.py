"""Reproducible June selection and visual review, using Explorer-compatible crops."""
from pathlib import Path
import sys, json, datetime as dt
import numpy as np
import scipy.ndimage as ndi
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix
import h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Patch-Generator/backend'))
from io_rainfall import get_latlon_grid_from_h5
from cities import nearest_city

OUT = ROOT / 'Patch-Generator/Benchmark-Patches/june2023-convective'
OUT.mkdir(parents=True, exist_ok=True)
FILES = sorted((ROOT / 'Patch-Generator/backend/data/raw/june2023').glob('*.h5'))
REJECTED = {
    '202306050800_patch032', '202306061600_patch070',
    '202306090800_patch054', '202306111200_patch158',
    '202306132000_patch063', '202306172000_patch003',
    '202306190800_patch051', '202306201200_patch013',
    '202306210800_patch101', '202306211600_patch228',
    '202306221200_patch025', '202306240800_patch030',
    '202306291200_patch223',
}

def distance(a, b):
    la, lo = np.radians([a['center_lat'], a['center_lon']])
    lb, lob = np.radians([b['center_lat'], b['center_lon']])
    return float(12742 * np.arcsin(np.sqrt(np.clip(np.sin((lb-la)/2)**2 + np.cos(la)*np.cos(lb)*np.sin((lob-lo)/2)**2, 0, 1))))

def read(p):
    with h5py.File(p) as f:
        raw = f['dataset1/data1/data'][:]
    return raw, np.where(np.isfinite(raw) & (raw >= 0), raw, 0)

def main():
    lat, lon = get_latlon_grid_from_h5(FILES[0])
    candidates = []
    # Every fourth hour makes time separation independent of greedy ranking.
    for ix, p in enumerate(FILES):
        ts = dt.datetime.strptime(p.stem.rsplit('_', 1)[1], '%Y%m%d%H%M')
        if ts.hour % 4:
            continue
        raw, rain = read(p)
        # Same 4x4 smoothing and 3 mm threshold as Explorer defaults.
        smooth = ndi.uniform_filter(rain, size=4, mode='nearest')
        labels, _ = ndi.label(smooth >= 3, structure=np.ones((3,3)))
        for j, sl in enumerate(ndi.find_objects(labels)):
            if sl is None:
                continue
            y, x = sl
            h, w = y.stop-y.start, x.stop-x.start
            if not (25 <= h <= 47 and 25 <= w <= 47):
                continue
            sub = rain[sl]
            if np.mean(raw[sl] < 0) > .01:
                continue
            peak = float(sub.max()); mean = float(sub.mean())
            wet = float(np.mean(sub >= 1)); intense = float(np.mean(sub >= 10))
            cv = float(sub.std() / max(mean, .01))
            if peak < 15 or intense < .005 or cv < .8 or wet > .85:
                continue
            score = float(np.log1p(peak) * cv * np.sqrt(intense) * (1-wet/2))
            candidates.append(dict(id=f'{p.stem}_patch{j:03d}', source_file=str(p.relative_to(ROOT)), timestamp=ts.isoformat(),
                y_min=y.start, y_max=y.stop-1, x_min=x.start, x_max=x.stop-1,
                mean_rainfall=mean, max_rainfall=peak, width_km=w*2., height_km=h*2., area_km2=w*h*4.,
                center_lat=float(lat[sl].mean()), center_lon=float(lon[sl].mean()),
                nearest_city=nearest_city(float(lat[sl].mean()), float(lon[sl].mean())),
                convective_screen=dict(score=score, coefficient_of_variation=cv, fraction_ge_1mm=wet, fraction_ge_10mm=intense)))
        if ix % 48 == 0:
            print(f'{ix+1}/{len(FILES)} maps; {len(candidates)} candidates', flush=True)
    (OUT/'candidates.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in candidates))
    print(f'Candidate total {len(candidates)}, hours {len(set(c["timestamp"] for c in candidates))}', flush=True)
    select(candidates)

def select(candidates):
    target = int(sys.argv[sys.argv.index('--count')+1]) if '--count' in sys.argv else 100
    candidates=[c for c in candidates if not any(c['id'].endswith(s) for s in REJECTED) and c['max_rainfall'] <= 150]
    edges=[(i,j) for i,a in enumerate(candidates) for j,b in enumerate(candidates[:i]) if a['timestamp']==b['timestamp'] or distance(a,b)<75]
    matrix=lil_matrix((len(edges)+1,len(candidates)))
    matrix[0,:]=1
    for k,(i,j) in enumerate(edges,1):
        matrix[k,i]=matrix[k,j]=1
    if '--max-count' in sys.argv:
        maximum=milp(-np.ones(len(candidates)),integrality=np.ones(len(candidates)),bounds=Bounds(0,1),constraints=LinearConstraint(matrix.tocsr()[1:],0,1),options={'time_limit':45})
        if not maximum.success:
            raise RuntimeError('Maximum count was not proven: '+maximum.message)
        target=int(round(-maximum.fun))
    lower=np.zeros(len(edges)+1); lower[0]=target
    upper=np.ones(len(edges)+1); upper[0]=target
    result=milp(-np.array([c['convective_screen']['score'] for c in candidates]),integrality=np.ones(len(candidates)),bounds=Bounds(0,1),constraints=LinearConstraint(matrix.tocsr(),lower,upper),options={'time_limit':45})
    if result.x is None:
        raise RuntimeError(f'No feasible {target}-patch selection: {result.message}')
    chosen=[c for c,x in zip(candidates,result.x) if x>.5]
    print(f'Selected {len(chosen)} at 75 km separation', flush=True)
    chosen.sort(key=lambda c:c['timestamp'])
    (OUT/f'selected-{target}.june2023.jsonl').write_text(''.join(json.dumps({k:v for k,v in c.items() if k!='convective_screen'})+'\n' for c in chosen))
    (OUT/'selection-audit.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in chosen))
    for start in range(0,len(chosen),20):
        fig, axes=plt.subplots(4,5,figsize=(15,12),layout='constrained')
        for ax in axes.flat:
            ax.set_visible(False)
        for ax,c in zip(axes.flat,chosen[start:start+20]):
            ax.set_visible(True)
            _,r=read(ROOT/c['source_file']); sub=r[c['y_min']:c['y_max']+1,c['x_min']:c['x_max']+1]
            im=ax.imshow(sub,cmap='turbo',vmin=0,vmax=30,origin='upper',extent=[0,c['width_km'],c['height_km'],0])
            ax.set_title(f'{start+list(axes.flat).index(ax)+1:03d}  {c["timestamp"][5:13]}\n{c["nearest_city"]}  max {c["max_rainfall"]:.0f}',fontsize=9)
        fig.colorbar(im,ax=axes.ravel().tolist(),label='Hourly rainfall (mm)',shrink=.7)
        fig.savefig(OUT/f'review-{start//20+1:02d}.png',dpi=120); plt.close(fig)
    if len(chosen)!=target:
        raise RuntimeError('Insufficient candidates: do not claim completed selection')
    times=[dt.datetime.fromisoformat(c['timestamp']) for c in chosen]
    assert min((b-a).total_seconds()/3600 for a,b in zip(times,times[1:]))>=4
    sep=min(distance(a,b) for i,a in enumerate(chosen) for b in chosen[i+1:])
    assert sep >= 75
    assert len({c['id'] for c in chosen})==target
    summary=dict(count=target,minimum_time_gap_hours=min((b-a).total_seconds()/3600 for a,b in zip(times,times[1:])),minimum_centre_distance_km=sep,first_timestamp=times[0].isoformat(),last_timestamp=times[-1].isoformat(),spatial_distance_definition='haversine between patch centres, all pairs',candidate_count=289,sampled_hours=180)
    (OUT/'validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'PASS: {target} patches; minimum time gap 4h; minimum centre separation {sep:.2f} km',flush=True)

if __name__=='__main__':
    if '--reuse-candidates' in sys.argv:
        select([json.loads(x) for x in (OUT/'candidates.jsonl').read_text().splitlines()])
    else:
        main()
