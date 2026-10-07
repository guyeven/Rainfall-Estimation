"""Build an isolated seven-method manuscript from the existing cache and saved fields.
No solver is run. Originals and input caches are read-only.
"""
from pathlib import Path
import collections, hashlib, json, shutil, csv
import numpy as np
from scipy.stats import t as student_t, ttest_rel
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
BASE=ROOT/'output/journal_revision'
DATA=ROOT/'Compute-Link-Attenuations/HundredPatches'
CACHE=DATA/'pipeline/batch_analyze_output_roy_dct/stats_report_cache.json'
REPORT=DATA/'pipeline/report_roy_dct'
METHODS=[
 ('IDW','IDW','sol_dir_idw','#687582','s'),
 ('ILDW','ILDW','sol_dir_ildw','#3297ba','^'),
 ('Solver(ILDW)','OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG','sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long','#278354','D'),
 ('Solver(GT)','OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL','sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal','#245cb2','o'),
 ('Convex solver','OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL','sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal','#d78020','o'),
 ('Homotopy solver','OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL','sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal','#a94899','+'),
 ('Roy DCT (limited)','Roy DCT (nonlinear adaptation)','sol_dir_roy_dct_nonlinear','#c13732','X')]

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
cache=json.loads(CACHE.read_text()); sheets=cache['ordered_sheets']
metrics={(r['solver'],r['patch_key']):r for r in sheets['PatchMapMetrics_ByPatch']}
records={n:[] for n,*_ in METHODS}; stops=collections.Counter();settings=collections.Counter()
paths=sorted((DATA/'gt_dir').glob('gt_*.npz'));assert len(paths)==100
for index,p in enumerate(paths):
 patch=p.stem.removeprefix('gt_')
 with np.load(p) as f: gt=f['R_gt'].astype(float)
 shape=gt.shape; g=gt.ravel(); gc=g-g.mean(); vg=np.mean(gc**2)
 assert vg>0 and np.isfinite(g).all()
 for name,label,folder,_,_ in METHODS:
  sp=DATA/'pipeline/solutions'/folder/f'est_input_{patch}_solution.npz'
  with np.load(sp) as f: field=f['R_hat'].astype(float)
  assert field.shape==shape and np.isfinite(field).all()
  u=field.ravel(); uc=u-u.mean(); vf=np.mean(uc**2); cov=np.mean(gc*uc)
  assert vf>0
  r=float(np.clip(cov/np.sqrt(vf*vg),-1,1)); e=float(np.sqrt(np.mean((uc-gc)**2)))
  bias=float(np.mean(u-g)); rmse=float(np.sqrt(np.mean((u-g)**2)))
  assert np.isclose(rmse**2,e**2+bias**2,atol=1e-9)
  cached=metrics[label,patch]
  np.testing.assert_allclose([rmse,bias,r],[cached['rmse_mmph'],cached['bias_mmph'],cached['pearson_corr']],rtol=1e-7,atol=1e-8)
  records[name].append(dict(patch=patch,reference_sd=float(np.sqrt(vg)),model_sd=float(np.sqrt(vf)),
     covariance=float(cov),correlation=r,centered_rmse=e,bias=bias,rmse=rmse))
  if name.startswith('Roy'):
   d=json.loads(sp.with_name(sp.stem+'_optinfo.json').read_text())
   stops[str(d['success'])+':'+d['stop_reason']]+=1
   settings[json.dumps({k:d.get(k) for k in ['lam','noise_variance','dct_layout','settings']},sort_keys=True)]+=1
 if index%20==0: print('Fields verified:',index+1,flush=True)

img=OUT/'images/taylor'; img.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
summary={}
for normalized in [True,False]:
 rows=[]
 for name,*_ in METHODS:
  rr=records[name]; vg=np.array([x['reference_sd']**2 for x in rr]);vf=np.array([x['model_sd']**2 for x in rr]);cv=np.array([x['covariance'] for x in rr])
  if normalized: vf=vf/vg;cv=cv/vg;vg=np.ones_like(vg)
  G=float(np.sqrt(vg.mean()));F=float(np.sqrt(vf.mean()));C=float(cv.mean());r=C/(F*G)
  E=float(np.sqrt(max(0,F*F+G*G-2*C)))
  rows.append(dict(method=name,reference_sd=G,model_sd=F,correlation=r,centered_rmse=E))
 summary['normalized' if normalized else 'unnormalized']=rows

def axes(ax,lim,G=1):
 ax.set_thetamin(0);ax.set_thetamax(90);ax.set_ylim(0,lim)
 corr=np.array([0,.2,.4,.6,.8,.9,.95,.99,1]);ax.set_thetagrids(np.degrees(np.arccos(corr)),[f'{v:g}' for v in corr])
 ax.set_rlabel_position(118);ax.grid(alpha=.3)
 theta=np.linspace(0,np.pi/2,180);radius=np.linspace(0,lim,180)
 T,R=np.meshgrid(theta,radius);E=np.sqrt(np.maximum(0,R*R+G*G-2*R*G*np.cos(T)))
 levels=np.linspace(0,lim,7)[1:]
 cs=ax.contour(T,R,E,levels=levels,colors='#7c8991',linestyles='--',linewidths=.7,alpha=.7)
 ax.clabel(cs,inline=True,fontsize=8,fmt='%.2g')
 ax.plot([0],[G],'*',color='black',ms=11,clip_on=False)
 ax.set_xlabel('Standard deviation (radius); correlation (outer arc)',labelpad=22)

def save(fig,stem):
 for ext in ['png','svg']:fig.savefig(img/f'{stem}.{ext}',dpi=190,bbox_inches='tight',facecolor='white')
 plt.close(fig)
for mode,rows in summary.items():
 fig=plt.figure(figsize=(9,6));ax=fig.add_axes([.09,.25,.56,.62],projection='polar')
 lim=max(max(r['model_sd'],r['reference_sd']) for r in rows)*1.15
 axes(ax,lim,rows[0]['reference_sd'])
 for row,(_,_,_,color,marker) in zip(rows,METHODS):
  ax.plot(np.arccos(row['correlation']),row['model_sd'],marker=marker,color=color,ms=9,linestyle='none',mew=1.7,label=row['method'])
 handles,labels=ax.get_legend_handles_labels();handles.insert(0,Line2D([],[],marker='*',color='black',linestyle='',markersize=10));labels.insert(0,'Ground truth')
 fig.legend(handles,labels,loc='center left',bbox_to_anchor=(.69,.51),frameon=False)
 fig.suptitle('Taylor diagram: equal patch weights',y=.98)
 unit='Normalized by each patch’s ground-truth SD' if mode=='normalized' else 'Unnormalized: standard deviations and centered RMSE in mm/h'
 fig.text(.08,.075,unit,fontsize=10)
 fig.text(.08,.025,'Dashed contours: centered RMSE. Bias is excluded. Roy: all 100 runs iteration-limited.',fontsize=9)
 save(fig,'combined_'+mode)
fig,axs=plt.subplots(2,4,figsize=(15,8),subplot_kw={'projection':'polar'})
lim=max(x['model_sd']/x['reference_sd'] for rr in records.values() for x in rr)*1.08
for ax,(name,_,_,color,marker) in zip(axs.ravel(),METHODS):
 axes(ax,lim);ax.set_xlabel('');ax.tick_params(labelsize=8)
 rr=records[name];ax.scatter([np.arccos(x['correlation']) for x in rr],[x['model_sd']/x['reference_sd'] for x in rr],color=color,marker=marker,s=17,alpha=.6)
 ax.set_title(name,pad=26,fontsize=11)
axs.ravel()[-1].set_visible(False)
fig.text(.79,.24,'Each dot: one patch\nShared normalized scale\nBlack star: ground truth\nDashed: centered RMSE\nRoy: iteration-limited',fontsize=11)
fig.subplots_adjust(wspace=.42,hspace=.40,top=.88,bottom=.08)
fig.suptitle('Normalized Taylor diagrams: 100 patches per method',fontsize=15)
save(fig,'patch_clouds_normalized')
(OUT/'taylor_statistics.json').write_text(json.dumps({'weighting':'equal patch weights; population moments within patches','summary':summary,'individual':records},indent=2))

# Portable manuscript assets: copied, never linked to writable originals.
for name in ['references.bib','mybibCML.bib','main_paths.tex']:
 shutil.copy2(BASE/name,OUT/name)
shutil.copytree(BASE/'images',OUT/'images',dirs_exist_ok=True)
for relative in ['distance_profiles_box_whisker/linear/distance_iqr_medians_rainy_multi_k3_box_whisker.png',
                 'distance_profiles_box_whisker/linear/distance_iqr_medians_nonrainy_multi_k3_box_whisker.png']:
 source=REPORT/'images'/relative.replace('/linear/', '/linear/k3/')
 if not source.exists(): raise FileNotFoundError(f'Render the seven-method report first: {source}')
 shutil.copy2(source,OUT/'images'/relative)

names={label:name for name,label,*_ in METHODS}
def fmt(v):return f'{v:.3f}'
def pm(vals):return '$'+fmt(np.mean(vals))+r'\pm '+fmt(np.std(vals,ddof=1))+'$'
def table(headers,rows,caption,label):
 return '\n'.join([r'\begin{table}[!htbp]',r'\centering\small',r'\begin{tabular}{l'+'r'*(len(headers)-1)+'}',r'\toprule',' & '.join(headers)+r' \\',r'\midrule',*[' & '.join(row)+r' \\' for row in rows],r'\bottomrule',r'\end{tabular}',r'\caption{'+caption+'}',r'\label{'+label+'}',r'\end{table}'])+'\n'
rows=[]
for name,*_ in METHODS:
 rr=records[name];rows.append([name,pm([r['rmse'] for r in rr]),pm([r['bias'] for r in rr]),pm([r['correlation'] for r in rr])])
global_table=table(['Method','RMSE','Signed bias','Pearson $r$'],rows,
 'Whole-patch metrics: mean $\\pm$ sample standard deviation across 100 patches, with equal patch weights. RMSE and bias are in mm/h. Roy DCT denotes the nonlinear adaptation at its iteration limit; Solver(GT) uses privileged ground-truth initialization.','tab:patch_map_metrics')
paired=[];paired_json=[]
idw=records['IDW'];idw_rmse=np.array([r['rmse'] for r in idw])
for name,*_ in METHODS[1:]:
 vals=np.array([r['rmse'] for r in records[name]]);diff=vals-idw_rmse
 t,p=ttest_rel(vals,idw_rmse,alternative='less'); upper=diff.mean()+student_t.ppf(.99,99)*diff.std(ddof=1)/10
 paired.append([name,str(int(np.sum(diff<0)))+':'+str(int(np.sum(diff>0))),fmt(diff.mean()),f'{p:.2g}',fmt(upper)])
 paired_json.append(dict(method=name,mean_difference=float(diff.mean()),p_one_sided=float(p),upper_99=float(upper)))
paired_table=table(['Method vs. IDW','Wins:losses',r'$\overline{\Delta}$',r'$p$ (one-sided)',r'99\% upper bound'],paired,
 'Paired patchwise RMSE comparison, with $\\Delta=\\mathrm{RMSE}_{s}-\\mathrm{RMSE}_{IDW}$. Negative differences favor the method. Tests use the alternative $E[\\Delta]<0$; values are unadjusted for multiple comparisons. Iteration-limited Roy outputs are retained.','tab:paired-rmse-t-test')
wetrows=[]
for name,label,*_ in METHODS:
 r=next(r for r in sheets['FPFN_ByThreshold'] if r.get('solver')==label and np.isclose(r.get('threshold_mmph',-1),.6))
 wetrows.append([name,*[f'{100*r[k]:.2f}' for k in ['fp_rate_all_mean','fn_rate_all_mean','fp_rate_dry_mean','fn_rate_wet_mean']]])
wettable=table(['Method',r'FP/all (\%)',r'FN/all (\%)',r'FP/dry (\%)',r'FN/wet (\%)'],wetrows,
 'Mean patchwise wet/dry error rates at 0.6 mm/h. False positive: predicted wet, observed dry; false negative: predicted dry, observed wet. Conditional rates use their respective ground-truth classes.','tab:wet-dry-confusion-merged')
linkrows=[]
for name,label,*_ in METHODS:
 rows=sheets['LinkStats_GTvs'+label]
 def sci(v):return f'{np.mean(v):.3g}'
 linkrows.append([name,sci([r['mean_abs_attn_err_per_km_all'] for r in rows]),sci([r['J_atten_all'] for r in rows])])
linktable=table(['Method','Attenuation MAE (dB/km)',r'$J_{\mathrm{atten}}$ (dB$^2$/km)'],linkrows,
 'Mean patchwise attenuation errors, evaluated consistently for all methods using the actual ITU forward model. $J_{\\mathrm{atten}}=M^{-1}\\sum_\\ell(\\widehat A_\\ell-A_\\ell)^2/L_\\ell$. This comparison metric is not the full native objective of Roy DCT.','tab:attenuation-fit-summary')
roy=records['Roy DCT (limited)']; roy_rmse=np.mean([r['rmse'] for r in roy]);roy_bias=np.mean([r['bias'] for r in roy]);roy_corr=np.mean([r['correlation'] for r in roy])
# Preserve existing definitions, regenerate results instead of silently leaving six-method claims.
original=(BASE/'Journal.tex').read_text()
start=original.index(r'\section{Experimental Results and Analysis}')
end=original.index(r'\section{Case Study Figures and Objective Evolution}')
notation=original[original.index(r'\subsection{Notation}',start):original.index(r'\subsection{RMSE, Bias, and Pearson Correlation Results and Analysis}',start)]
method=r'''
\subsection{DCT-sparse baseline adapted from Roy et al.}
We additionally evaluate a no-dynamics sparsity baseline motivated by
\citet{roy2016dynamic}. Their Eq.~(26) uses a linear measurement operator,
an orthonormal DCT basis and nonnegative reconstructed rainfall. Here the
measurement term is adapted to the existing nonlinear ITU observations:
\[
 \min_{u\geq0}\;\frac{1}{\sigma_e^2}\|A-F(u)\|_2^2+\lambda\|Du\|_1,
 \qquad F_\ell(u)=k_\ell\sum_j l_{\ell j}u_j^{\alpha_\ell}.
\]
We use an orthonormal separable two-dimensional DCT-II, including the DC
coefficient, $\lambda=2$ and $\sigma_e^2=10^{-5}$. This retains the prior
structure but is not a reproduction of the paper's linear experiment.
The DCT layout is an explicit implementation choice. No temporal information,
learned prior, pixel-count normalization or length-normalized data residual is
used. Fast transforms and sparse operators avoid constructing the dense basis.
Successive linearization yields convex ADMM/CG subproblems; damping and
backtracking control the nonlinear updates. The method starts from a constant
0.6 mm/h field. Settings are transferred rather than tuned to this benchmark.
All 100 saved runs stopped at the outer-iteration limit (50 steps), with
\texttt{success=false}. We therefore label this method ``Roy DCT (limited)''
and retain all runs rather than selecting favorable cases. These results assess
the saved nonlinear implementation and iteration budget, not the attainable
accuracy of a converged Roy estimator.
'''
results=r'''\section{Experimental Results and Analysis}
We compare seven saved reconstruction methods on the same 100 benchmark
patches: IDW, ILDW, Solver(ILDW), Solver(GT), the convex and homotopy solvers,
and the iteration-limited nonlinear Roy DCT adaptation. Ground truth is the
rainfall field used to generate the synthetic link attenuations. Each patch
receives equal weight in the aggregate metrics. Solver(GT) is a privileged
initialization reference, not an operational baseline.
'''+notation+r'''
\subsection{Whole-patch accuracy}
'''+global_table+f'''
The saved Roy DCT outputs have mean RMSE {roy_rmse:.3f} mm/h,
mean signed bias {roy_bias:.3f} mm/h, and mean Pearson correlation
{roy_corr:.3f}. Their strong negative bias and low correlation show that
close attenuation agreement alone does not determine a useful full rainfall
map. The comparison is provisional because none of these runs declared
convergence. Among the operational methods in this cache, the convex and
homotopy solvers have the smallest mean whole-patch RMSE (approximately
0.845 mm/h), compared with 1.307 mm/h for IDW.
'''+r'''
\subsection{Paired comparison with IDW}
'''+paired_table+r'''
These tests describe the saved outcomes; they do not remove the numerical
limitations of the Roy runs or establish a ranking of fully converged methods.
\subsection{Wet/dry classification and attenuation fit}
'''+wettable+linktable+r'''
The Roy adaptation achieves small attenuation residuals despite poorer map
accuracy. Under sparse link coverage, fitting path integrals is insufficient
to determine rainfall between links. Its DCT penalty, initialization, transferred
hyperparameters and finite iteration budget all affect the result. These
experiments do not isolate which of those choices accounts for the observed
underestimation.
\subsection{Distance-conditioned errors}
Pixels are grouped by distance $d_3$ to the third-closest link. Rainy pixels
have ground-truth rainfall at least 0.6 mm/h; for these pixels we use relative
absolute error. For nonrainy pixels we use absolute error. Each patch contributes
one median per nonempty distance bin. The figures below use the same seven-method
cache and binning rules as the numerical summaries.
\begin{figure}[!htbp]\centering
\includegraphics[width=\linewidth]{\distanceboxplot}
\caption{Patchwise median relative absolute errors for rainy pixels, stratified by $d_3$. Roy DCT denotes iteration-limited nonlinear outputs.}
\label{fig:rae_distance_roy}\end{figure}
\begin{figure}[!htbp]\centering
\includegraphics[width=\linewidth]{\nonrainydistanceboxplot}
\caption{Patchwise median absolute errors for nonrainy pixels, stratified by $d_3$. Empty strata do not contribute a patch value.}
\label{fig:ae_distance_roy}\end{figure}
\clearpage
\subsection{Taylor diagrams}
A Taylor diagram summarizes within-patch standard deviation, correlation and
centered RMSE. Let $g_i$ and $f_i$ be the ground-truth and reconstructed
standard deviations for patch $i$, and $c_i$ their covariance, using population
moments over pixels. With equal patch weights, the combined unnormalized point
uses $G=\sqrt{\langle g_i^2\rangle}$, $F=\sqrt{\langle f_i^2\rangle}$ and
$C=\langle c_i\rangle$, with angle $\arccos(C/(GF))$ and radius $F$.
Its centered error is $E_c=\sqrt{F^2+G^2-2C}$, the root mean square of the
patchwise centered errors. It is not the arithmetic mean of patch correlations.
For the normalized diagram, each patch is first divided by its own ground-truth
standard deviation, yielding $G=1$, $F=\sqrt{\langle f_i^2/g_i^2\rangle}$ and
$C=\langle c_i/g_i^2\rangle$. Neither diagram encodes mean bias; for every patch,
$\mathrm{RMSE}_i^2=E_{c,i}^2+\mathrm{Bias}_i^2$.
\begin{figure}[!htbp]\centering
\includegraphics[width=\linewidth]{images/taylor/combined_normalized.png}
\caption{Combined normalized Taylor diagram, with equal patch weights. Dashed contours indicate centered RMSE and the star denotes ground truth. Bias must be read separately from Table~\ref{tab:patch_map_metrics}.}
\label{fig:taylor_normalized}\end{figure}
\begin{figure}[!htbp]\centering
\includegraphics[width=\linewidth]{images/taylor/combined_unnormalized.png}
\caption{Combined unnormalized Taylor diagram in mm/h. Equal patch weights are retained, but patches with larger physical variance contribute more to the variance moments. The convex and homotopy points nearly coincide.}
\label{fig:taylor_unnormalized}\end{figure}
\begin{figure}[!htbp]\centering
\includegraphics[width=\linewidth]{images/taylor/patch_clouds_normalized.png}
\caption{Individual normalized Taylor points: 100 saved patches for each method, on a common scale. Roy DCT points are from nonconverged, iteration-limited nonlinear runs.}
\label{fig:taylor_clouds}\end{figure}
\clearpage
'''
text=original[:start]+method+results+original[end:]
text=text.replace(r'\section{Introduction\editnote{GE:need complete rewrite}}','',1)
text=text.replace('In this section, we present two case studies,', 'The following two case studies retain the original selected methods and figures; they do not include the Roy adaptation. In this section, we present two case studies,',1)
text=text.replace(r'\section{Discussion}',r'\section{Discussion}'+r'''
The added Roy DCT comparison is limited by incomplete nonlinear convergence
in all 100 runs. Its low attenuation residuals and poor map metrics motivate
separate convergence and hyperparameter studies; they do not establish a
negative conclusion about the original linear method of Roy et al.
''',1)
# Existing case-study distance figures now show the seven-method cache as well.
text=text.replace('compare the results with inverse distance weighting.', 'compare the results with interpolation baselines and an iteration-limited nonlinear adaptation of DCT-sparse reconstruction.')
text=text.replace(r'\usepackage{graphicx}',r'\usepackage{graphicx}'+'\n'+r'\usepackage{xurl}')
text=text.replace(r'\begin{document}', r'\renewcommand{\editnote}[1]{}'+'\n'+r'\renewcommand{\inlinenote}[1]{}'+'\n'+r'\begin{document}',1)
(OUT/'Journal_with_Roy_DCT.tex').write_text(text)
metadata={'source_manuscript':str(BASE/'Journal.tex'),'source_sha256':digest(BASE/'Journal.tex'),
 'cache':str(CACHE),'cache_sha256':digest(CACHE),'patches':100,'methods':7,
 'roy_stopping_counts':dict(stops),'roy_settings_counts':dict(settings),
 'paired_rmse_tests':paired_json,'metric_validation':'All 700 raw-field metrics match cache within 1e-7 relative tolerance'}
(OUT/'provenance.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps({'stopping':dict(stops),'summary':summary},indent=2),flush=True)
