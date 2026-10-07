"""Rebuild report data and figures from saved runs; no solvers are executed."""
from pathlib import Path
import os, json, csv, hashlib
from collections import Counter
os.environ.setdefault('MPLCONFIGDIR', '/tmp/rainfall-report-mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
P = ROOT / 'Compute-Link-Attenuations/HundredPatches/pipeline'
CACHE = P / 'batch_analyze_output_gmz_roy_dct_ildw/stats_report_cache.json'
cache = json.loads(CACHE.read_text())
METHODS = [
 ('IDW','idw','IDW','#687386'),
 ('ILDW','ildw','ILDW','#46a1b8'),
 ('Solver(ILDW)','opt_norm_ildw_mult_ildw_init_light_jtotal_long','OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG','#21865b'),
 ('Convex','opt_norm_virtual_convex_const_init_long_light_jtotal','OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL','#dc8a25'),
 ('Homotopy','opt_norm_virtual_homotopy_const_init_long_light_jtotal','OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL','#9e519d'),
 ('GMZ','gmz_itu','GMZ (ITU adaptation)','#aa6147'),
 ('Roy DCT (ILDW)','roy_dct_ildw_outer300','Roy DCT (ILDW init, 300 outer cap)','#2754b5'),
]
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
 'axes.titleweight':'semibold','savefig.facecolor':'white','font.family':'DejaVu Sans'})
def save(fig, name):
 fig.savefig(OUT/'figures'/f'{name}.pdf', bbox_inches='tight')
 fig.savefig(OUT/'figures'/f'{name}.png', dpi=150, bbox_inches='tight')
 plt.close(fig)
def tab(name, header, rows, align=None):
 align=align or 'l'+'r'*(len(header)-1)
 text='\\begin{tabular}{'+align+'}\\toprule\n'+' & '.join(header)+r' \\ \midrule'+'\n'
 text+='\n'.join(' & '.join(map(str,row))+r' \\' for row in rows)
 (OUT/'tables'/f'{name}.tex').write_text(text+'\n'+r'\bottomrule\end{tabular}'+'\n')
def summary(a):
 a=np.asarray(a,float)
 return dict(n=len(a),mean=float(np.mean(a)),median=float(np.median(a)),sd=float(np.std(a,ddof=1)),
             q1=float(np.quantile(a,.25)),q3=float(np.quantile(a,.75)),min=float(a.min()),max=float(a.max()))
def f(x):return f'{x:.3f}'

gtfiles=sorted((P.parent/'gt_dir').glob('gt_*.npz'))
patches=[p.stem.removeprefix('gt_') for p in gtfiles]
assert len(patches)==100
assert set(cache['solvers']['order'])=={m[2] for m in METHODS}
metrics={}; diagnostics={}; traces={}; timing={}; provenance={}
cachepatch={(r['solver'],r['patch_key']):r for r in cache['ordered_sheets']['PatchMapMetrics_ByPatch']}
for name,slug,label,color in METHODS:
 rows=[]; infos=[]; tt=[]
 folder=P/'solutions'/f'sol_dir_{slug}'
 assert {p.stem.removeprefix('est_input_').removesuffix('_solution') for p in folder.glob('*_solution.npz')}==set(patches)
 for path,patch in zip(gtfiles,patches):
  with np.load(path) as z:g=z['R_gt'].astype(float)
  with np.load(folder/f'est_input_{patch}_solution.npz') as z:
   a=z['R_hat'].astype(float)
   assert a.shape==g.shape and np.isfinite(a).all() and np.isfinite(g).all()
  gc=g-g.mean(); ac=a-a.mean(); vg=float(np.mean(gc**2)); va=float(np.mean(ac**2)); cov=float(np.mean(gc*ac))
  r=cov/np.sqrt(vg*va); bias=float(np.mean(a-g)); rmse=float(np.sqrt(np.mean((a-g)**2)))
  cr=float(np.sqrt(np.mean((ac-gc)**2)))
  assert np.isclose(rmse**2,cr**2+bias**2)
  crw=cachepatch[(label,patch)]
  assert np.isclose(rmse,crw['rmse_mmph']) and np.isclose(r,crw['pearson_corr']) and np.isclose(bias,crw['bias_mmph'])
  wet=g>=.6; pred=a>=.6
  rows.append(dict(patch=patch,pixels=g.size,rmse=rmse,mae=float(np.mean(np.abs(a-g))),bias=bias,
   correlation=r,vg=vg,va=va,cov=cov,crmse=cr,tn=float(np.mean(~wet & ~pred)),
   fp=float(np.mean(~wet & pred)),fn=float(np.mean(wet & ~pred)),tp=float(np.mean(wet & pred))))
  info=folder/f'est_input_{patch}_solution_optinfo.json'
  if info.exists():
   diag=json.loads(info.read_text());infos.append(diag)
   if slug=='roy_dct_ildw_outer300':
    with np.load(P/'solutions/sol_dir_ildw'/f'est_input_{patch}_solution.npz') as z: initial=z['R_hat'].astype('<f8')
    assert hashlib.sha256(initial.ravel().tobytes()).hexdigest()==diag['initial_field_summary']['sha256']
  trace=folder/f'est_input_{patch}_solution_itertrace.json'
  if trace.exists():tt.append(json.loads(trace.read_text()))
 metrics[name]=rows;diagnostics[name]=infos;traces[name]=tt
 print('Verified fields:',name,flush=True)

stats={n:{k:summary([r[k] for r in rows]) for k in ['rmse','mae','bias','correlation']} for n,rows in metrics.items()}
tab('rainfall',['Method','RMSE mean $\\pm$ SD','RMSE median','MAE mean','Bias mean','Corr. mean'],[
 [n,f"{stats[n]['rmse']['mean']:.3f} $\\pm$ {stats[n]['rmse']['sd']:.3f}",f(stats[n]['rmse']['median']),f(stats[n]['mae']['mean']),f(stats[n]['bias']['mean']),f(stats[n]['correlation']['mean'])] for n,*_ in METHODS])
tab('classification',['Method','TN (\\%)','FP (\\%)','FN (\\%)','TP (\\%)','Accuracy (\\%)'],[
 [n]+[f(100*np.mean([r[k] for r in metrics[n]])) for k in ['tn','fp','fn','tp']]+[f(100*np.mean([r['tn']+r['tp'] for r in metrics[n]]))] for n,*_ in METHODS])
attrows=[]
for n,slug,label,col in METHODS:
 rr=[r for r in cache['ordered_sheets']['LinkStats_GTvs'+label] if r['patch_key']!='AVERAGE']
 assert {r['patch_key'] for r in rr}==set(patches)
 attrows.append([n]+[f'{np.mean([r[k] for r in rr]):.6f}' for k in ['mean_abs_attn_err_per_km_all','length_weighted_abs_attn_err_per_km_all']])
tab('attenuation',['Method','Mean link error (dB/km)','Length-weighted error (dB/km)'],attrows)
fig,axs=plt.subplots(1,3,figsize=(11,4.3),layout='constrained')
for ax,key,title in zip(axs,['rmse','bias','correlation'],['Rainfall RMSE (mm/h)','Mean bias (mm/h)','Spatial correlation']):
 vals=[[r[key] for r in metrics[n]] for n,*_ in METHODS]
 bp=ax.boxplot(vals,patch_artist=True,showfliers=False,tick_labels=[m[0].replace(' (ILDW)','\n(ILDW)') for m in METHODS])
 for box,m in zip(bp['boxes'],METHODS):box.set_facecolor(m[3]);box.set_alpha(.25)
 rng=np.random.default_rng(17)
 for i,(v,m) in enumerate(zip(vals,METHODS),1):ax.scatter(i+rng.uniform(-.17,.17,len(v)),v,s=5,c=m[3],alpha=.4)
 ax.tick_params(axis='x',labelrotation=65,labelsize=8);ax.set_title(title);ax.grid(axis='y',alpha=.2)
save(fig,'rainfall_distributions')

# Paired descriptive differences; no independence-based p-values for nearby patches.
paired=[]
for n,*_ in METHODS:
 if n=='Roy DCT (ILDW)':continue
 d=np.array([r['rmse'] for r in metrics['Roy DCT (ILDW)']])-np.array([r['rmse'] for r in metrics[n]])
 paired.append([n,f(d.mean()),f(np.median(d)),str(int((d<0).sum())),f'{d.min():.3f} / {d.max():.3f}'])
tab('paired',['Comparator','Mean $\\Delta$','Median $\\Delta$','Roy lower / 100','Min / max $\\Delta$'],paired)

# Taylor diagrams: equal-patch moments, centered separately within each patch.
taylor={}
for n,rows in metrics.items():
 G=np.sqrt(np.mean([r['vg'] for r in rows]));F=np.sqrt(np.mean([r['va'] for r in rows]));C=np.mean([r['cov'] for r in rows]);R=C/(G*F)
 E=np.sqrt(np.mean([r['crmse']**2 for r in rows]))
 assert np.isclose(E**2,G**2+F**2-2*G*F*R)
 taylor[n]=dict(reference_sd=float(G),model_sd=float(F),correlation=float(R),crmse=float(E))
def taylor_axes(ax,rmax,reference=1):
 ax.set_thetamin(0);ax.set_thetamax(90);ax.set_ylim(0,rmax)
 corrs=np.array([0,.2,.4,.6,.8,.9,.95,.99,1.])
 ax.set_xticks(np.arccos(corrs));ax.set_xticklabels([f'{v:g}' for v in corrs],fontsize=8)
 ax.set_rlabel_position(70);ax.tick_params(axis='y',labelsize=8);ax.grid(alpha=.25)
 th,rr=np.meshgrid(np.linspace(0,np.pi/2,150),np.linspace(0,rmax,150))
 e=np.sqrt(reference**2+rr**2-2*reference*rr*np.cos(th))
 cs=ax.contour(th,rr,e,levels=np.linspace(0,rmax,6)[1:],colors='#80929c',linewidths=.6,linestyles='dotted')
 ax.clabel(cs,fontsize=7,fmt='%.2g');ax.plot(0,reference,'k*',ms=10,clip_on=False)
fig,axs=plt.subplots(1,2,subplot_kw={'projection':'polar'},figsize=(10,4.5))
for ax,norm in zip(axs,[False,True]):
 G=taylor[METHODS[0][0]]['reference_sd'];taylor_axes(ax,1.15*(1 if norm else G),1 if norm else G)
 for i,(n,slug,label,col) in enumerate(METHODS):
  d=taylor[n];ax.plot(np.arccos(d['correlation']),d['model_sd']/(G if norm else 1),marker=['s','^','D','o','P','v','*'][i],ms=8,color=col,label=n)
 ax.set_title('Normalized by reference SD' if norm else 'Standard deviation in mm/h',pad=26,fontsize=11)
fig.legend(handles=[Line2D([],[],marker=['s','^','D','o','P','v','*'][i],ls='',color=m[3],label=m[0]) for i,m in enumerate(METHODS)],loc='lower center',ncol=4,bbox_to_anchor=(.5,-.09),frameon=False)
fig.subplots_adjust(wspace=.35,bottom=.1);save(fig,'taylor_summary')
rmax=max(np.sqrt(r['va']/r['vg']) for rows in metrics.values() for r in rows)*1.08
for group, subset in enumerate([METHODS[:4],METHODS[4:]],1):
 fig,axs=plt.subplots(2,2,subplot_kw={'projection':'polar'},figsize=(8,7))
 for ax,(n,slug,label,col) in zip(axs.flat,subset):
  taylor_axes(ax,max(1.15,rmax));rr=metrics[n]
  ax.scatter(np.arccos(np.clip([r['correlation'] for r in rr],-1,1)),[np.sqrt(r['va']/r['vg']) for r in rr],s=15,c=col,alpha=.45)
  d=taylor[n];ax.plot(np.arccos(d['correlation']),d['model_sd']/d['reference_sd'],'D',ms=7,c='black')
  ax.set_title(n,pad=19,fontsize=12)
 if len(subset)<4:
  axs.flat[-1].set_axis_off();axs.flat[-1].text(.05,.55,'100 dots per method\nOne dot per patch\n\nBlack diamond: pooled moments\nBlack star: reference\nDotted arcs: centered RMSE',transform=axs.flat[-1].transAxes,fontsize=11)
 fig.subplots_adjust(hspace=.42,wspace=.36);save(fig,f'taylor_clouds_{group}')
tab('taylor',['Method','$\\sigma_f$ (mm/h)','$r_{\\rm pooled}$','cRMSE (mm/h)','$\\sigma_f/\\sigma_g$'],[[n,f(taylor[n]['model_sd']),f(taylor[n]['correlation']),f(taylor[n]['crmse']),f(taylor[n]['model_sd']/taylor[n]['reference_sd'])] for n,*_ in METHODS])

for file in (P/'timing').rglob('*_runtime_summary.json'):
 d=json.loads(file.read_text());match=[m for m in METHODS if m[1]==d['solver_name']]
 if not match:continue
 n=match[0][0]
 csvfile=file.with_name(file.name.replace('_summary.json','_per_patch.csv'))
 rr=list(csv.DictReader(csvfile.open()));assert {r['patch_id'] for r in rr}==set(patches)
 a=np.array([float(r['end_to_end_seconds']) for r in rr]);assert np.isclose(a.mean(),d['end_to_end_seconds']['mean'])
 timing[n]=dict(summary=d,records=rr)
 provenance[str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
tab('runtime',['Method','$n$','Mean (s)','Median (s)','IQR (s)','Min--max (s)','Total (h)'],[
 ([n,'100']+[f'{timing[n]["summary"]["end_to_end_seconds"][k]:.2f}' for k in ['mean','median','iqr']]+[f'{timing[n]["summary"]["end_to_end_seconds"]["min"]:.2f}--{timing[n]["summary"]["end_to_end_seconds"]["max"]:.2f}',f'{timing[n]["summary"]["end_to_end_seconds"]["total"]/3600:.2f}']) if n in timing else [n,'0','---','---','---','---','---'] for n,*_ in METHODS])
fig,ax=plt.subplots(figsize=(9,3.7),layout='constrained');rng=np.random.default_rng(6)
for i,(n,slug,label,col) in enumerate(METHODS):
 if n not in timing:ax.text(i,5,'Not\nrecorded',ha='center',fontsize=9,color='#666');continue
 a=[float(r['end_to_end_seconds']) for r in timing[n]['records']]
 ax.scatter(i+rng.uniform(-.18,.18,100),a,s=12,c=col,alpha=.4)
 ax.plot([i-.23,i+.23],[np.median(a)]*2,c=col,lw=3)
ax.set_xticks(range(7),[m[0] for m in METHODS],fontsize=9);ax.set_yscale('log');ax.set_ylabel('End-to-end seconds per patch (log scale)');ax.grid(axis='y',alpha=.2)
save(fig,'runtime')

# Thin traces end at their recorded stopping iteration. Median uses last-observation
# carried forward to keep the same 100-patch cohort; dashed part has stopped runs.
def ensemble(ax,seq,color,title,xlabel='Iteration',log=True,start=0,threshold=None):
 assert len(seq)==100
 arrays=[np.asarray(v,float) for v in seq];assert all(np.isfinite(a).all() for a in arrays)
 size=max(map(len,arrays));mat=np.empty((100,size))
 for i,a in enumerate(arrays):
  mat[i,:len(a)]=a;mat[i,len(a):]=a[-1]
  ax.plot(np.arange(len(a))+start,np.maximum(a,1e-15) if log else a,color=color,alpha=.14,lw=.55,rasterized=True)
 med=np.median(mat,axis=0);first=min(map(len,arrays));x=np.arange(size)+start
 if log:med=np.maximum(med,1e-15)
 ax.plot(x[:first],med[:first],color='black',lw=2.6,label='Median (100 patches)')
 if first<size:ax.plot(x[first-1:],med[first-1:],color='black',lw=2.6,ls='--',label='Median with final values held')
 if threshold is not None:ax.axhline(threshold,color='#ba3939',ls=':',lw=1.4,label='Stopping threshold')
 if log:ax.set_yscale('log')
 ax.set_title(title,fontsize=10);ax.set_xlabel(xlabel);ax.grid(alpha=.2);ax.legend(fontsize=7,frameon=False)

stoprows=[];convergence={}
for n,slug,label,col in METHODS:
 infos=diagnostics[n]
 if not infos:stoprows.append([n,'Direct baseline','---','---','---']);continue
 its=[d.get('nit',d.get('iteration')) for d in infos];reasons=Counter(d['stop_reason'] for d in infos)
 convergence[n]=dict(success=sum(bool(d['success']) for d in infos),iterations=summary(its),reasons=dict(reasons))
 stoprows.append([n,str(convergence[n]['success'])+' / 100',f'{np.median(its):.0f}',f'{min(its)}--{max(its)}',', '.join(f'{k.replace("_"," ")}: {v}' for k,v in reasons.items())])
tab('stopping',['Method','Success flag','Median iter.','Range','Recorded stop reasons'],stoprows,'lrrlp{5.0cm}')
for n,slug,label,col in METHODS[2:5]:
 tt=traces[n];assert len(tt)==100
 fig,axs=plt.subplots(2,2,figsize=(10.5,6.5),layout='constrained')
 keys=['J_weighted_sum','J_atten','J_1d','J_2d']
 titles=['Weighted objective / initial value','Attenuation term / initial value','Along-link roughness (native)','Spatial roughness (native)']
 for ax,key,title in zip(axs.flat,keys,titles):
  seq=[]
  for t in tt:
   a=np.array([r[key] for r in t['iterations']]);seq.append(a/a[0] if key in keys[:2] else a)
  ensemble(ax,seq,col,title,xlabel='Cumulative inner iteration' if n=='Homotopy' else 'L-BFGS-B iteration',log=key in keys[:2])
  if key in keys[2:]:ax.set_yscale('symlog',linthresh=1e-4)
 save(fig,'optimization_'+slug)

roy=diagnostics['Roy DCT (ILDW)'];gmz=diagnostics['GMZ']
assert all(d['init_method']=='ildw' and d['settings']['max_outer']==300 for d in roy)
fig,axs=plt.subplots(2,2,figsize=(10.5,6.5),layout='constrained')
seqs=[[[h['objective']/d['history'][0]['objective'] for h in d['history']] for d in roy],
 [[h['relative_full_step']/d['settings']['outer_rtol'] for h in d['history'][1:]] for d in roy],
 [[h['inner']['nit'] for h in d['history'][1:]] for d in roy],
 [[h['inner']['dual_residual']/h['inner']['dual_tolerance'] for h in d['history'][1:]] for d in roy]]
for i,(ax,seq,title) in enumerate(zip(axs.flat,seqs,['Objective / initial objective','Full relative step / outer tolerance','ADMM iterations per outer step','ADMM dual residual / tolerance'])):
 ensemble(ax,seq,METHODS[-1][3],title,'Outer iteration',start=0 if i==0 else 1,threshold=1 if i in [1,3] else None)
save(fig,'optimization_roy')
fig,axs=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
ensemble(axs[0],[d['max_update_history'] for d in gmz],METHODS[-2][3],'Maximum gauge update (mm/h)','GMZ iteration',start=1)
ensemble(axs[1],[[v/d['max_update_history'][0] for v in d['max_update_history']] for d in gmz],METHODS[-2][3],'Maximum update / first update','GMZ iteration',start=1)
save(fig,'optimization_gmz')
fig,axs=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
hom=traces['Homotopy']
ensemble(axs[0],[[h['beta'] for h in d['iterations']] for d in hom],METHODS[4][3],'Continuation parameter beta','Cumulative inner iteration',log=False)
ensemble(axs[1],[[h['J_atten_real']/d['iterations'][0]['J_atten_real'] for h in d['iterations']] for d in hom],METHODS[4][3],'Real-ITU attenuation term / initial','Cumulative inner iteration')
save(fig,'homotopy_schedule')

royextra=dict(final_objective_ratio=summary([d['fun']/d['history'][0]['objective'] for d in roy]),
 final_step_ratio=summary([d['history'][-1]['relative_full_step']/d['settings']['outer_rtol'] for d in roy]),
 total_inner=sum(d['inner_iterations'] for d in roy),total_cg=sum(d['cg_iterations'] for d in roy),
 inner_calls=sum(len(d['history'])-1 for d in roy),inner_success=sum(h['inner']['success'] for d in roy for h in d['history'][1:]),
 accepted=sum(h['accepted'] for d in roy for h in d['history'][1:]),
 max_objective_increase=max(max(np.diff([h['objective'] for h in d['history']])) for d in roy))
gmzextra={key:summary([d[key] for d in gmz]) for key in ['virtual_attenuation_rmse_db','raster_attenuation_rmse_db','num_gauges','num_isolated_gauges']}
fig,ax=plt.subplots(figsize=(8.5,3.2),layout='constrained')
for i,(key,col) in enumerate([('virtual_attenuation_rmse_db','#21865b'),('raster_attenuation_rmse_db','#aa6147')]):
 a=[d[key] for d in gmz];ax.scatter(np.arange(1,101),a,s=13,c=col,alpha=.6,label='Virtual gauges' if i==0 else 'Final raster')
 ax.axhline(np.median(a),c=col,lw=2)
ax.set_yscale('log');ax.set_xlabel('Patch index (chronological filename order)');ax.set_ylabel('Attenuation RMSE (dB)');ax.legend();ax.grid(alpha=.2);save(fig,'gmz_attenuation_gap')

fpfn=cache['ordered_sheets']['FPFN_ByThreshold']
fig,axs=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
for n,slug,label,col in METHODS:
 rr=sorted([r for r in fpfn if r['solver']==label],key=lambda r:r['threshold_mmph'])
 for ax,key in zip(axs,['fp_rate_all_mean','fn_rate_all_mean']):ax.plot([r['threshold_mmph'] for r in rr],[100*r[key] for r in rr],c=col,label=n)
for ax,title in zip(axs,['False wet: fraction of all pixels','Missed wet: fraction of all pixels']):ax.set_title(title,fontsize=10);ax.set_xlabel('Wet/dry threshold (mm/h)');ax.set_ylabel('Mean patch fraction (%)');ax.grid(alpha=.2)
axs[1].legend(fontsize=7,ncol=2);save(fig,'threshold_sweep')

for p in [CACHE,P/'analyze_gmz_roy_dct_ildw.yaml',ROOT/'Compute-Link-Attenuations/cml_attenuation/solvers/solve_rain_gmz.py',ROOT/'Compute-Link-Attenuations/cml_attenuation/solvers/solve_rain_roy_dct.py']:
 provenance[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(patch_count=100,statistics=stats,taylor=taylor,convergence=convergence,roy=royextra,gmz=gmzextra,
 timing={n:d['summary'] for n,d in timing.items()},provenance_sha256=provenance)
(OUT/'results_summary.json').write_text(json.dumps(result,indent=2))
with (OUT/'per_patch_metrics.csv').open('w') as fp:
 writer=csv.DictWriter(fp,fieldnames=['method']+list(metrics['IDW'][0]));writer.writeheader()
 for n,rr in metrics.items():writer.writerows(dict(method=n,**r) for r in rr)
print(json.dumps({k:v for k,v in result.items() if k not in ['timing','provenance_sha256']},indent=2))
