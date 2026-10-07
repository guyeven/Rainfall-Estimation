from pathlib import Path
import sys,json,numpy as np
from scipy.sparse import csr_matrix
sys.path.insert(0,'Compute-Link-Attenuations')
from cml_attenuation.solvers.solve_rain_roy_dct import DCTBasis,LinkModel
from cml_attenuation.solvers.solve_rain_lbfgsb import load_est_input_json
base=Path('Compute-Link-Attenuations/HundredPatches');sol=base/'pipeline/solutions/sol_dir_roy_dct_nonlinear'
fs=sorted(sol.glob('*optinfo.json')); ds=[json.loads(p.read_text()) for p in fs]
order=np.argsort([d['fun'] for d in ds]);chosen=[order[10],order[50],order[90]]
for idx in chosen:
 d=ds[idx]; stem=fs[idx].name.removesuffix('_solution_optinfo.json'); patch=stem.removeprefix('est_input_');prob=load_est_input_json(base/'est_dir'/f'{stem}.json',warn=False)
 A=csr_matrix((prob.ds_km,(prob.link_idx,prob.pix_idx)),shape=(prob.L,prob.P)); model=LinkModel(A,prob.k,prob.alpha);D=DCTBasis((prob.H,prob.W)); covered=np.asarray(A.sum(axis=0)).ravel()>0
 vals={}; fields={}
 for name,path,key in [('Roy',sol/f'{stem}_solution.npz','R_hat'),('GT',base/'gt_dir'/f'gt_{patch}.npz','R_gt'),('ILDW',base/'pipeline/solutions/sol_dir_ildw'/f'{stem}_solution.npz','R_hat')]:
  u=np.load(path)[key].ravel().astype(float);r=model.forward(u)-prob.A_obs
  fields[name]=u; vals[name]=dict(data=float(r@r/1e-5),penalty=float(2*np.abs(D.analysis(u)).sum()),mean_uncovered=float(u[~covered].mean()),mean=float(u.mean()))
 print(json.dumps(dict(patch=patch,coverage=float(covered.mean()),values=vals,damping_cost_to_truth=float(.001/2*np.sum((fields['GT']-fields['Roy'])**2)),scaled_objective_improvement_to_truth=float(1e-5/2*(vals['Roy']['data']+vals['Roy']['penalty']-vals['GT']['data']-vals['GT']['penalty'])))),flush=True)
