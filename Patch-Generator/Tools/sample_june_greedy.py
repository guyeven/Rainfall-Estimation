"""Random-order sequential selection from every June hour; no solver outcomes."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np
import scipy.ndimage as ndi
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Patch-Generator/backend'))
from cities import nearest_city
from io_rainfall import get_latlon_grid_from_h5
from patches import smooth_rain

def write_jsonl(path, records):
    path.write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in records), encoding='utf-8')

def distance(a, b):
    la,lo,lb,lob=np.radians([a['center_lat'],a['center_lon'],b['center_lat'],b['center_lon']])
    return float(12742*np.arcsin(np.sqrt(np.clip(np.sin((lb-la)/2)**2+np.cos(la)*np.cos(lb)*np.sin((lob-lo)/2)**2,0,1))))

def read(path):
    with h5py.File(path) as f:
        raw=f['dataset1/data1/data'][:]
    valid=np.isfinite(raw)&(raw>=0)
    return np.where(valid,raw,0),valid

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=202306)
    parser.add_argument('--cap',type=int,default=300)
    parser.add_argument('--reuse-candidates',action='store_true')
    args=parser.parse_args()
    if args.cap<1: parser.error('--cap must be positive')
    out=ROOT/'Patch-Generator/Benchmark-Patches/june2023-greedy-random'
    out.mkdir(parents=True,exist_ok=True)
    files=sorted((ROOT/'Patch-Generator/backend/data/raw/june2023').glob('*.h5'))
    assert len(files)==720, f'Expected 720 June maps, found {len(files)}'
    candidate_path=out/'eligible-candidates.jsonl'
    if args.reuse_candidates:
        candidates=[json.loads(s) for s in candidate_path.read_text().splitlines()]
    else:
        lat,lon=get_latlon_grid_from_h5(files[0])
        candidates=[]
        for ix,p in enumerate(files):
            rain,valid=read(p)
            timestamp=dt.datetime.strptime(p.stem.rsplit('_',1)[1],'%Y%m%d%H%M')
            assert timestamp.year==2023 and timestamp.month==6
            labels,_=ndi.label(smooth_rain(rain,4,4)>=3,structure=np.ones((3,3)))
            for j,sl in enumerate(ndi.find_objects(labels)):
                if sl is None: continue
                y,x=sl; h,w=y.stop-y.start,x.stop-x.start
                if not(25<=h<=47 and 25<=w<=47): continue
                sub=rain[sl]; missing=float(1-valid[sl].mean())
                mean=float(sub.mean()); peak=float(sub.max())
                cv=float(sub.std()/max(mean,.01)); wet=float(np.mean(sub>=1)); intense=float(np.mean(sub>=10))
                if missing>.01 or not(15<=peak<=150) or cv<.8 or wet>.85 or intense<.005: continue
                clat,clon=float(lat[sl].mean()),float(lon[sl].mean())
                candidates.append(dict(id=f'{p.stem}_patch{j:03d}',source_file=str(p.relative_to(ROOT)),timestamp=timestamp.isoformat(),
                    y_min=y.start,y_max=y.stop-1,x_min=x.start,x_max=x.stop-1,
                    mean_rainfall=mean,max_rainfall=peak,width_km=2.*w,height_km=2.*h,area_km2=4.*w*h,
                    center_lat=clat,center_lon=clon,nearest_city=nearest_city(clat,clon),
                    screening=dict(coefficient_of_variation=cv,fraction_ge_1mm=wet,fraction_ge_10mm=intense,missing_fraction=missing)))
            if (ix+1)%48==0: print(f'Detected {ix+1}/720 maps: {len(candidates)} eligible patches',flush=True)
        write_jsonl(candidate_path,candidates)
    rng=np.random.Generator(np.random.PCG64(args.seed))
    order=rng.permutation(len(candidates))
    chosen=[]; audit=[]
    for rank,idx in enumerate(order,1):
        c=candidates[int(idx)]; t=dt.datetime.fromisoformat(c['timestamp'])
        conflict=next((b for b in chosen if abs((t-dt.datetime.fromisoformat(b['timestamp'])).total_seconds())<14400 or distance(c,b)<75),None)
        audit.append(dict(priority=rank,patch_id=c['id'],accepted=conflict is None,conflicting_patch_id=conflict['id'] if conflict else None))
        if conflict is None: chosen.append(c)
        if len(chosen)==args.cap: break
    # Export order follows random acceptance order, so main.py's first k rows
    # are a reproducible prefix of this same greedy selection.
    write_jsonl(out/'selected-patches.june2023.jsonl',[{k:v for k,v in c.items() if k!='screening'} for c in chosen])
    write_jsonl(out/'selection-audit.jsonl',audit)
    write_jsonl(out/'patch-attributes.june2023.jsonl',[dict(patch_id=c['id'],approved=True,attributes=dict(area_type=[],rain_type=['convective'],intensity='',notes='Objective convective-looking screening; not meteorologically confirmed.')) for c in chosen])
    pairs=[(a,b) for i,a in enumerate(chosen) for b in chosen[:i]]
    min_time=min(abs((dt.datetime.fromisoformat(a['timestamp'])-dt.datetime.fromisoformat(b['timestamp'])).total_seconds())/3600 for a,b in pairs)
    min_space=min(distance(a,b) for a,b in pairs)
    assert min_time>=4 and min_space>=75
    assert len({c['id'] for c in chosen})==len(chosen)
    for start in range(0,len(chosen),20):
        fig,axes=plt.subplots(4,5,figsize=(15,12),layout='constrained')
        for ax in axes.flat: ax.set_visible(False)
        for n,(ax,c) in enumerate(zip(axes.flat,chosen[start:start+20]),start+1):
            ax.set_visible(True); rain,_=read(ROOT/c['source_file'])
            sub=rain[c['y_min']:c['y_max']+1,c['x_min']:c['x_max']+1]
            assert sub.shape==(int(c['height_km']/2),int(c['width_km']/2))
            assert np.isclose(sub.mean(),c['mean_rainfall']) and np.isclose(sub.max(),c['max_rainfall'])
            im=ax.imshow(sub,cmap='turbo',vmin=0,vmax=30,extent=[0,c['width_km'],c['height_km'],0])
            ax.set_title(f'{n:03d} {c["timestamp"][5:16]}\n{c["nearest_city"]} max {c["max_rainfall"]:.0f}',fontsize=9)
        fig.colorbar(im,ax=[a for a in axes.flat if a.get_visible()],label='Hourly rainfall (mm)',shrink=.7)
        fig.savefig(out/f'review-{start//20+1:02d}.png',dpi=120); plt.close(fig)
    manifest=dict(seed=args.seed,random_generator='NumPy PCG64',numpy_version=np.__version__,requested_cap=args.cap,selected_count=len(chosen),
        eligible_count=len(candidates),eligible_hours=len({c['timestamp'] for c in candidates}),source_maps=len(files),
        candidate_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        algorithm='Random permutation, greedy acceptance; conflict if time gap <4 hours OR centre distance <75 km',
        stopped_because='cap_reached' if len(chosen)==args.cap else 'candidate_pool_exhausted',
        minimum_time_gap_hours=min_time,minimum_centre_distance_km=min_space,source_crops_verified=True,
        export_order='random acceptance order',screening=dict(smoothing_pixels=[4,4],threshold_mm=3,size_km=[50,94],peak_mm=[15,150],minimum_cv=.8,maximum_fraction_ge_1mm=.85,minimum_fraction_ge_10mm=.005,maximum_missing_fraction=.01))
    (out/'sampling-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'random-seed.txt').write_text(str(args.seed)+'\n')
    print(json.dumps(manifest,indent=2),flush=True)

if __name__=='__main__': main()
