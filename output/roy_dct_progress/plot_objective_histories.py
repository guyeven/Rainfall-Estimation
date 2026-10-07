from pathlib import Path
import json,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path('/Users/isoto/Projects/Rainfall-Estimation')
out=root/'output/roy_dct_progress';out.mkdir(exist_ok=True)
h=[json.loads(p.read_text())['history'] for p in (root/'Compute-Link-Attenuations/HundredPatches/pipeline/solutions/sol_dir_roy_dct_nonlinear').glob('*optinfo.json')]
a=np.array([[r['objective'] for r in x] for x in h]); steps=np.arange(51)
fig,axs=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
series=[(a/a[:,0,None],steps,'Full run','Objective / initial objective'),(a[:,10:]/a[:,10,None],steps[10:],'After the initial drop','Objective / objective at iteration 10'),(100*(a[:,:-1]-a[:,1:])/a[:,:-1],steps[1:],'Improvement per outer iteration','Objective decrease (%)')]
for ax,(v,x,title,ylabel) in zip(axs,series):
 lo,med,hi=np.quantile(v,[.1,.5,.9],axis=0)
 for row in v:ax.plot(x,row,color='#27699c',alpha=.08,lw=.6)
 ax.fill_between(x,lo,hi,color='#27699c',alpha=.18,label='10th–90th percentile');ax.plot(x,med,color='#174b77',lw=2,label='Median')
 ax.set(title=title,xlabel='Outer iteration',ylabel=ylabel);ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
axs[0].set_yscale('log');axs[0].legend(fontsize=9)
axs[1].set_ylim(bottom=0)
axs[2].set_xlim(10,50);axs[2].set_ylim(0,2)
fig.suptitle('Roy DCT: saved objective histories for all 100 patches (50 outer iterations)',fontsize=14)
fig.savefig(out/'objective_histories.png',dpi=180);fig.savefig(out/'objective_histories.pdf');plt.close(fig)
for start,end in [(0,50),(10,50),(40,50),(49,50)]:
 v=100*(a[:,start]-a[:,end])/a[:,start]
 print(start,end,dict(median=np.median(v),min=v.min(),max=v.max(),p10=np.quantile(v,.1),p90=np.quantile(v,.9)))
print('monotonic',bool(np.all(np.diff(a,axis=1)<=0)))
