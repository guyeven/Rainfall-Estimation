"""Generate short numerical interpretations from verified report summaries."""
from pathlib import Path
import json

OUT=Path(__file__).resolve().parent
d=json.loads((OUT/'results_summary.json').read_text())
s=d['statistics'];r=d['roy'];g=d['gmz'];c=d['convergence']
def mean(n,k='rmse'):return s[n][k]['mean']
macros={
 'mainFindings':f"Convex and Homotopy have the lowest mean patch RMSE (both about {mean('Convex'):.3f} mm/h). "
  f"ILDW-init Roy has mean RMSE {mean('Roy DCT (ILDW)'):.3f} mm/h versus {mean('ILDW'):.3f} for ILDW, "
  f"while GMZ has {mean('GMZ'):.3f} mm/h. Roy fits real-link attenuation most closely, but this does not translate into the lowest rainfall-map error.",
 'rainFindings':f"The mean patch RMSE reduction from ILDW to ILDW-init Roy is "
  f"{100*(1-mean('Roy DCT (ILDW)')/mean('ILDW')):.2f}\\%. "
  f"GMZ's mean RMSE is {100*(mean('GMZ')/mean('ILDW')-1):.2f}\\% higher than ILDW's. "
  f"Convex and Homotopy are very close at the reported precision: their mean RMSEs are {mean('Convex'):.6f} and {mean('Homotopy'):.6f} mm/h, respectively. "
  "The difference between mean and median RMSE reflects a tail of difficult patches; the plot retains all of them.",
 'attenFindings':"Roy has the smallest mean link-normalized error and the smallest length-weighted error in this seven-method comparison. "
  "The map-error ranking is different: Convex and Homotopy lead the rainfall RMSE table. Link measurements constrain path integrals, so close attenuation agreement still allows different spatial rainfall patterns.",
 'referenceSD':f"{d['taylor']['IDW']['reference_sd']:.3f}",
 'royFindings':f"The diagnostics report {c['Roy DCT (ILDW)']['success']}/100 successful outer stops; "
  f"the recorded reasons are " + ', '.join(f"{v} {k.replace('_',' ')}" for k,v in c['Roy DCT (ILDW)']['reasons'].items()) + '. '
  f"Median outer iterations are {c['Roy DCT (ILDW)']['iterations']['median']:.0f}. "
  f"Across all patches, {r['inner_success']:,} of {r['inner_calls']:,} inner calls report success, with {r['total_inner']:,} ADMM iterations and {r['total_cg']:,} CG iterations. "
  f"The median final objective ratio is {r['final_objective_ratio']['median']:.4f}; the median final full-step/tolerance ratio is {r['final_step_ratio']['median']:.3f}. "
  "Convergence of the inner solves does not establish convergence of every nonlinear outer run.",
 'gmzFindings':f"There are {g['num_gauges']['min']:,.0f}--{g['num_gauges']['max']:,.0f} gauges per patch "
  f"(median {g['num_gauges']['median']:,.0f}). The median logged virtual-gauge attenuation RMSE is "
  f"{g['virtual_attenuation_rmse_db']['median']:.2e} dB, while the median final-raster attenuation RMSE is "
  f"{g['raster_attenuation_rmse_db']['median']:.4f} dB. "
  f"The number of gauges without other-link neighbors ranges from {g['num_isolated_gauges']['min']:.0f} to {g['num_isolated_gauges']['max']:.0f} per patch."
}
(OUT/'report_numbers.tex').write_text('\n'.join('\\newcommand{\\'+k+'}{'+v+'}' for k,v in macros.items())+'\n')
print('Wrote numerical report text.')
