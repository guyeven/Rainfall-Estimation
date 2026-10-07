from pathlib import Path
import json, csv, hashlib, shutil, re
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
P=ROOT/'Compute-Link-Attenuations/HundredPatches/pipeline'
files=sorted((P/'solutions/sol_dir_roy_dct_nonlinear').glob('*optinfo.json'))
def stats(v):
 a=np.array(v,dtype=float)
 return dict(n=len(a),mean=float(a.mean()),median=float(np.median(a)),min=float(a.min()),max=float(a.max()),q1=float(np.quantile(a,.25)),q3=float(np.quantile(a,.75)),total=float(a.sum()))
rows=[]; hist=[]
for p in files:
 d=json.loads(p.read_text()); h=d['history'][-1]; i=h['inner']
 rows.append(dict(patch=p.name.removesuffix('_solution_optinfo.json').removeprefix('est_input_'),seconds=d['optimizer_seconds'],outer=d['nit'],inner=d['inner_iterations'],cg=d['cg_iterations'],relative_step=h['relative_full_step'],outer_ratio=h['relative_full_step']/d['settings']['outer_rtol'],primal_ratio=i['primal_residual']/i['primal_tolerance'],dual_ratio=i['dual_residual']/i['dual_tolerance'],objective_initial=d['history'][0]['objective'],objective_final=d['fun'],objective_reduction=1-d['fun']/d['history'][0]['objective'],final_relative_objective_decrease=(d['history'][-2]['objective']-d['fun'])/max(1,abs(d['history'][-2]['objective'])),data_term=d['data_term'],penalty=d['lam']*d['coefficient_l1'],pixels=d['num_pixels'],links=d['num_valid_links']))
 hist.extend(d['history'][1:])
s={k:stats([r[k] for r in rows]) for k in rows[0] if k!='patch'}
s['all_inner_solves']=len(hist);s['inner_converged']=sum(h['inner']['success'] for h in hist)
s['accepted_steps']=dict(__import__('collections').Counter(str(h['step']) for h in hist))
s['max_all_primal_ratio']=max(h['inner']['primal_residual']/h['inner']['primal_tolerance'] for h in hist)
s['max_all_dual_ratio']=max(h['inner']['dual_residual']/h['inner']['dual_tolerance'] for h in hist)
runtime={}
for name in ['idw','ildw','convex_solver']:
 f=P/f'timing/all_methods/{name}_runtime_summary.json';runtime[name]=json.loads(f.read_text())
 with (P/f'timing/all_methods/{name}_runtime_per_patch.csv').open() as fp: timed=list(csv.DictReader(fp))
 assert {r['patch_id'] for r in timed}=={r['patch'] for r in rows}
s['runtime_benchmarks']=runtime
s['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'Compute-Link-Attenuations/cml_attenuation/solvers/solve_rain_roy_dct.py',P/'batch_solve_roy_dct.yaml',ROOT/'output/journal_roy_dct/Journal_with_Roy_DCT.tex']}
(OUT/'run_summary.json').write_text(json.dumps(s,indent=2))
with (OUT/'per_patch_diagnostics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
text=(ROOT/'output/journal_roy_dct/Journal_with_Roy_DCT.tex').read_text()
for i,chunk in enumerate(re.findall(r'\\begin\{table\}\[!htbp\].*?\\end\{table\}',text,re.S)):
 if any(l in chunk for l in ['tab:patch_map_metrics','tab:paired-rmse-t-test','tab:wet-dry-confusion-merged','tab:attenuation-fit-summary']):
  label=re.search(r'\\label\{([^}]+)\}',chunk)[1]
  (OUT/(label.replace(':','_')+'.tex')).write_text(chunk.replace('[!htbp]','[H]'))
shutil.copytree(ROOT/'output/journal_roy_dct/images/taylor',OUT/'figures',dirs_exist_ok=True)
shutil.copy2(ROOT/'output/journal_roy_dct/taylor_statistics.json',OUT/'taylor_statistics.json')
lines=[r'\begin{tabular}{lrrrr}\toprule Quantity & Minimum & Median & Mean & Maximum\\\midrule']
for k,label in [('relative_step','Final relative full step'),('outer_ratio','Step / outer tolerance'),('primal_ratio','Final primal / tolerance'),('dual_ratio','Final dual / tolerance'),('inner','ADMM iterations per patch'),('cg','CG iterations per patch')]:
 a=s[k];lines.append(label+' & '+' & '.join(f'{a[j]:.5g}' for j in ['min','median','mean','max'])+r' \\')
lines.append(r'\bottomrule\end{tabular}');(OUT/'convergence_table.tex').write_text('\n'.join(lines))
lines=[r'\begin{tabular}{llrrrr}\toprule Method & Scope & Mean & Median & Min--max & Total\\\midrule']
for name,label in [('idw','IDW'),('ildw','ILDW'),('convex_solver','Convex')]:
 for key,scope in [('end_to_end_seconds','End-to-end'),('optimizer_seconds','Optimizer')]:
  a=runtime[name][key]
  if a['count']: lines.append(f"{label} & {scope} & {a['mean']:.2f} & {a['median']:.2f} & {a['min']:.2f}--{a['max']:.2f} & {a['total']/3600:.3f} h"+r' \\')
a=s['seconds'];lines.append(f"Roy DCT & Optimizer & {a['mean']:.2f} & {a['median']:.2f} & {a['min']:.2f}--{a['max']:.2f} & {a['total']/3600:.3f} h"+r' \\')
for name in ['Solver(ILDW)','Solver(GT)','Homotopy']:lines.append(name+r' & Not recorded & -- & -- & -- & -- \\')
lines.append(r'\bottomrule\end{tabular}');(OUT/'runtime_table.tex').write_text('\n'.join(lines))
print(json.dumps({k:v for k,v in s.items() if k not in ['runtime_benchmarks','source_hashes']},indent=2))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
arr=[]; obj=[]
for p in files:
 d=json.loads(p.read_text());arr.append([h['relative_full_step']/1e-5 for h in d['history'][1:]])
 obj.append([h['objective']/d['history'][0]['objective'] for h in d['history']])
fig,axs=plt.subplots(1,2,figsize=(10,3.3),layout='constrained')
for ax,a,x,title in [(axs[0],np.array(arr),np.arange(1,51),'Outer step / stopping tolerance'),(axs[1],np.array(obj),np.arange(51),'Objective / initial objective')]:
 lo,med,hi=np.quantile(a,[.1,.5,.9],axis=0);ax.fill_between(x,lo,hi,color='#3568a6',alpha=.18,label='10th--90th percentile');ax.plot(x,med,color='#3568a6',label='Median');ax.set_yscale('log');ax.set_xlabel('Outer iteration');ax.set_title(title,fontsize=11);ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
axs[0].axhline(1,color='#a33c32',ls='--',label='Stopping threshold');axs[0].legend(fontsize=8);axs[1].legend(fontsize=8)
fig.savefig(OUT/'figures/convergence.png',dpi=180);plt.close(fig)
