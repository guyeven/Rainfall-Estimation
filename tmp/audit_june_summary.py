from pathlib import Path
import csv,json,math
import numpy as np
import pdfplumber
root=Path('/Users/isoto/Projects/Rainfall-Estimation')
p=root/'Compute-Link-Attenuations/June2023HundredPatches/pipeline'
rows=list(csv.reader((root/'output/pdf/june2023_summary_corrected.csv').open()))[1:]
dirs=['sol_dir_idw','sol_dir_ildw','sol_dir_convex_light_shrinkage','sol_dir_convex_no_shrinkage','sol_dir_homotopy_light_shrinkage','sol_dir_homotopy_no_shrinkage','sol_dir_solver_ildw_timing','sol_dir_solver_ildw_no_shrinkage','sol_dir_roy_dct_ildw_outer50']
gts={x.stem[3:]:x for x in (p.parent/'gt_dir').glob('gt_*.npz')}
assert len(gts)==100
with pdfplumber.open(root/'output/pdf/june2023_report_corrected.pdf') as doc: text=doc.pages[1].extract_text()
audit=[]
for row,directory in zip(rows,dirs):
 sol={x.name[len('est_input_'):-len('_solution.npz')]:x for x in (p/'solutions'/directory).glob('*_solution.npz')}
 assert set(sol)==set(gts),(directory,len(sol),set(sol)^set(gts))
 values=[]; excluded=0; shapes=set()
 for key,gpath in sorted(gts.items()):
  with np.load(gpath) as z: gt=z['R_gt'].astype(np.float64)
  with np.load(sol[key]) as z: pred=z['R_hat'].astype(np.float64)
  assert gt.shape==pred.shape
  shapes.add(gt.shape)
  valid=np.isfinite(gt)&np.isfinite(pred); excluded+=int(valid.size-valid.sum())
  x,y=gt[valid],pred[valid]
  assert x.size>1 and np.ptp(x)>0 and np.ptp(y)>0
  error=y-x
  rmse=math.sqrt(float(np.dot(error,error))/len(error))
  bias=math.fsum(error)/len(error)
  xc=x-math.fsum(x)/len(x); yc=y-math.fsum(y)/len(y)
  corr=float(np.dot(xc,yc)/math.sqrt(float(np.dot(xc,xc))*float(np.dot(yc,yc))))
  assert -1<=corr<=1
  values.append((rmse,bias,corr))
 summary=[]
 for column in zip(*values):
  triple=[math.fsum(column)/len(column),min(column),max(column)]
  assert triple[1]<=triple[0]<=triple[2]
  summary.extend(triple)
 expected=[format(v,'.4g') for v in summary]
 assert expected==row[2:],(directory,expected,row[2:])
 assert (' '.join([row[0],row[1]]+expected)) in text,(directory,'PDF mismatch')
 audit.append(dict(solver=row[0],patches=len(values),shapes=sorted(shapes),excluded_pixels=excluded,summary_full_precision=summary,all_nine_pdf_cells_match=True))
 print(row[0], 'PASS', 'patches=',len(values),'excluded=',excluded,flush=True)
(root/'output/pdf/june2023_summary_audit.json').write_text(json.dumps(audit,indent=2))
print('All 81 summary cells independently verified.')
