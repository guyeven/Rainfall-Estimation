"""Render rainy/non-rainy D3 profiles from the six-method shrinkage-comparison cache, without reruns."""
from pathlib import Path
import json, os, hashlib
os.environ.setdefault('MPLCONFIGDIR','/tmp/rainfall-report-mpl')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
source=ROOT/'Compute-Link-Attenuations/HundredPatches/pipeline/batch_analyze_output_shrinkage_comparison/stats_report_cache.json'
c=json.loads(source.read_text())
methods_full = [
 ('IDW','idw','IDW','#687386'),
 ('ILDW','ildw','ILDW','#46a1b8'),
 ('Solver(ILDW) light','opt_norm_ildw_mult_ildw_init_light_jtotal_long','Solver(ILDW) light shrinkage','#21865b'),
 ('Solver(ILDW) none','solver_ildw_no_shrinkage','Solver(ILDW) no shrinkage','#8e55b5'),
 ('Convex light','opt_norm_virtual_convex_const_init_long_light_jtotal','Convex light shrinkage','#dc8a25'),
 ('Convex none','convex_no_shrinkage','Convex no shrinkage','#c34f59'),
]
methods=[(n,label,col) for n,slug,label,col in methods_full]
bins=c['labels']['dist_labels']
assert len(bins)==8 and set(c['solvers']['order'])=={m[1] for m in methods}
assert c['render']['threshold_mmph']==.6
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
summary={'cache_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'threshold_mmph':.6,'k':3,'bins':bins,'profiles':{}}
for mask in ['rainy','nonrainy']:
 values=c['plot_data']['medians_'+mask]['3']
 counts=c['plot_data']['bin_counts']['3'][mask]
 ns=[sum(float(x)>0 for x in counts[b]) for b in bins]
 fig,(overview,ax)=plt.subplots(2,1,figsize=(10.5,6.2),sharex=True,
                              gridspec_kw={'height_ratios':[1,2.8]},layout='constrained')
 records={}
 for j,(name,label,color) in enumerate(methods):
  rows=[]
  for b,n in zip(bins,ns):
   a=np.asarray(values[label][b],float)
   assert len(a)==n and np.isfinite(a).all() and (a>=0).all()
   q1,med,q3=np.quantile(a,[.25,.5,.75])
   rows.append(dict(bin=b,n=n,q1=float(q1),median=float(med),q3=float(q3),minimum=float(a.min()),maximum=float(a.max())))
  records[name]=rows
  boxes=[{'q1':r['q1'],'med':r['median'],'q3':r['q3'],'whislo':r['minimum'],'whishi':r['maximum'],'fliers':[]} for r in rows]
  for panel in [overview,ax]:
   panel.bxp(boxes,positions=np.arange(8)+(j-2.5)*.13,widths=.105,showfliers=False,
             manage_ticks=False,patch_artist=True,
             boxprops={'facecolor':color,'edgecolor':color,'alpha':.65,'linewidth':.9},
             medianprops={'color':'black','linewidth':1.15},
             whiskerprops={'color':color,'linewidth':.9},capprops={'color':color,'linewidth':.9})
 labels=[b.replace('≤',r'$\leq$').replace(',',',\n')+f'\n$n={n}$' for b,n in zip(bins,ns)]
 ax.set_xticks(np.arange(8),labels,fontsize=9)
 ax.set_xlabel('$d_3$ distance bin (m); $n$ = contributing patches',labelpad=8)
 metric='Rainy-pixel RAE' if mask=='rainy' else 'Absolute error (mm/h)'
 overview.set_ylabel(metric+'\nFull range',fontsize=10)
 ax.set_ylabel(metric+'\nDetail view',fontsize=10)
 detail_max=max(r['q3'] for rows in records.values() for r in rows)*1.1
 ax.set_ylim(0,detail_max)
 overview.set_ylim(0,max(r['maximum'] for rows in records.values() for r in rows)*1.05)
 for panel in [overview,ax]:panel.grid(axis='y',alpha=.22);panel.set_xlim(-.6,7.6)
 overview.tick_params(axis='x',bottom=False)
 overview.legend(handles=[Patch(facecolor=color,edgecolor=color,label=name,alpha=.65) for name,_,color in methods],loc='lower left',bbox_to_anchor=(0,1.02,1,.1),mode='expand',ncol=3,frameon=False,fontsize=9,borderaxespad=0)
 for ext in ['pdf','png']:fig.savefig(OUT/'figures'/f'd3_{mask}.{ext}',dpi=180,bbox_inches='tight')
 plt.close(fig);summary['profiles'][mask]=records
(OUT/'d3_statistics.json').write_text(json.dumps(summary,indent=2))
print('D3 box-and-whisker figures generated: quartile boxes, median lines, min/max whiskers; patch counts verified.')
