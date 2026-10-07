from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path('/Users/isoto/Projects/Rainfall-Estimation'); P=ROOT/'Compute-Link-Attenuations/June2023HundredPatches/pipeline'; OUT=P/'report_june_full/images/taylor'; OUT.mkdir(parents=True,exist_ok=True)
methods=[('IDW','sol_dir_idw'),('ILDW','sol_dir_ildw'),('Solver(ILDW) light shrinkage','sol_dir_solver_ildw_timing'),('Solver(ILDW) no shrinkage','sol_dir_solver_ildw_no_shrinkage'),('Convex light shrinkage','sol_dir_convex_light_shrinkage'),('Convex no shrinkage','sol_dir_convex_no_shrinkage'),('Homotopy light shrinkage','sol_dir_homotopy_light_shrinkage'),('Homotopy no shrinkage','sol_dir_homotopy_no_shrinkage'),('ILDW-init Roy DCT','sol_dir_roy_dct_ildw_outer50')]
rec={n:[] for n,_ in methods}
for gp in sorted((P.parent/'gt_dir').glob('gt_*.npz')):
    with np.load(gp) as z: gt=np.asarray(z['R_gt'],float).ravel()
    sd=np.std(gt)
    if sd==0: continue
    for n,d in methods:
        sp=P/'solutions'/d/f'est_input_{gp.stem[3:]}_solution.npz'
        if sp.exists():
            with np.load(sp) as z: pr=np.asarray(z['R_hat'],float).ravel()
            rec[n].append((np.std(pr)/sd,float(np.corrcoef(gt,pr)[0,1])))
fig,ax=plt.subplots(figsize=(8,7),subplot_kw={'projection':'polar'}); ax.set_thetamin(0); ax.set_thetamax(90); ax.set_ylim(0,1.2); ax.set_title('Taylor diagram - June 2023, all solvers',pad=25,weight='bold')
for (n,_),col in zip(methods,plt.cm.tab10(np.linspace(0,1,len(methods)))):
    a=np.asarray(rec[n]);
    if len(a):
        s=np.sqrt(np.mean(a[:,0]**2)); r=np.mean(a[:,0]*a[:,1])/s; ax.scatter([np.arccos(np.clip(r,0,1))],[s],label=n,color=col,s=70)
ax.scatter([0],[1],marker='*',s=160,c='black',label='Ground truth'); ax.legend(loc='upper left',bbox_to_anchor=(1.02,1)); fig.tight_layout(); fig.savefig(OUT/'combined_all_solvers.png',dpi=180,bbox_inches='tight'); plt.close(fig)
