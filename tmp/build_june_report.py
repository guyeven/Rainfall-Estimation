from pathlib import Path
import json, math
import numpy as np
from collections import defaultdict
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle

ROOT=Path('/Users/isoto/Projects/Rainfall-Estimation'); PIPE=ROOT/'Compute-Link-Attenuations/June2023HundredPatches/pipeline'
CACHE=PIPE/'batch_analyze_output_all_but_roy_dct/stats_report_cache.json'; PLOT=PIPE/'report_june_combined_d3/images'; TJ=PIPE/'report_june_combined_d3/images/taylor'; ADDED=PIPE/'report_june_added_d3/images'; OUT=ROOT/'output/pdf/june2023_report.pdf'
C=json.loads(CACHE.read_text()); S=getSampleStyleSheet()
TAYLOR=PIPE/'report_june_full/images/taylor'; TAYLOR.mkdir(parents=True,exist_ok=True)
def make_taylor():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    methods=[('IDW','sol_dir_idw'),('ILDW','sol_dir_ildw'),('Solver(ILDW) light shrinkage','sol_dir_solver_ildw_timing'),('Solver(ILDW) no shrinkage','sol_dir_solver_ildw_no_shrinkage'),('Convex light shrinkage','sol_dir_convex_light_shrinkage'),('Convex no shrinkage','sol_dir_convex_no_shrinkage'),('Homotopy light shrinkage','sol_dir_homotopy_light_shrinkage'),('Homotopy no shrinkage','sol_dir_homotopy_no_shrinkage'),('ILDW-init Roy DCT','sol_dir_roy_dct_ildw_outer50')]
    rec={n:[] for n,_ in methods}
    for gp in sorted((PIPE.parent/'gt_dir').glob('gt_*.npz')):
        with np.load(gp) as z: gt=np.asarray(z['R_gt'],float).ravel()
        if np.std(gt)==0: continue
        sd=np.std(gt); gc=gt-gt.mean()
        for n,dn in methods:
            sp=PIPE/'solutions'/dn/f'est_input_{gp.stem[3:]}_solution.npz'
            if not sp.exists(): continue
            with np.load(sp) as z: pr=np.asarray(z['R_hat'],float).ravel()
            pc=pr-pr.mean(); s=np.std(pr)/sd; r=float(np.corrcoef(gt,pr)[0,1]); rec[n].append((s,r))
    fig,ax=plt.subplots(figsize=(8,7),subplot_kw={'projection':'polar'}); ax.set_thetamin(0); ax.set_thetamax(90); ax.set_ylim(0,1.2); ax.set_title('Taylor diagram - June 2023, all solvers',pad=25,weight='bold')
    colors=plt.cm.tab10(np.linspace(0,1,len(methods)))
    for (n,_),col in zip(methods,colors):
        a=rec[n]
        if not a: continue
        arr=np.asarray(a); s=float(np.sqrt(np.mean(arr[:,0]**2))); r=float(np.mean(arr[:,0]*arr[:,1])/s)
        ax.scatter([np.arccos(np.clip(r,0,1))],[s],label=n,color=col,s=70)
    ax.scatter([0],[1],marker='*',s=160,c='black',label='Ground truth'); ax.legend(loc='upper left',bbox_to_anchor=(1.02,1)); fig.tight_layout(); fig.savefig(TAYLOR/'combined_all_solvers.png',dpi=180,bbox_inches='tight'); plt.close(fig)
def im(p,h=5.0*inch):
    x=Image(str(p)); z=min(7*inch/x.imageWidth,h/x.imageHeight); x.drawWidth=x.imageWidth*z; x.drawHeight=x.imageHeight*z; return x
def f(x):
    try: return f'{float(x):.4g}' if math.isfinite(float(x)) else 'n/a'
    except: return 'n/a'
def tab(d,w):
    t=Table(d,colWidths=w,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#172033')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#CBD5E1')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F8FAFC')])]))
    return t
story=[Spacer(1,1.5*inch),Paragraph('June 2023 Hundred-Patch Benchmark',S['Title']),Paragraph('Metrics, plots, Taylor diagrams, optimization behavior, and runtimes',S['Heading2']),Paragraph('100 June 2023 patches. Supplementary Solver(ILDW) no-shrinkage, timed Solver(ILDW), and Roy DCT outputs are included from their complete June solution directories.',S['BodyText']),PageBreak(),Paragraph('1. Summary metrics',S['Heading1'])]
ks=['rmse_mmph_mean','rmse_mmph_min','rmse_mmph_max','bias_mmph_mean','bias_mmph_min','bias_mmph_max','pearson_corr_mean','pearson_corr_min','pearson_corr_max']; d=[['Solver','N','RMSE mean','RMSE min','RMSE max','Bias mean','Bias min','Bias max','Pearson mean','Pearson min','Pearson max']]
for r in C['ordered_sheets'].get('PatchMapMetrics_BySolver',[]):
    label=r.get('solver_name',r.get('solver',''))
    if label=='Solver(ILDW)':
        continue
    d.append([label,r.get('n_patches','')]+[f(r.get(k)) for k in ks])

def extra_metrics(label, dirname):
    vals=json.loads(Path('/tmp/extra_metrics.json').read_text()).get(label)
    if vals is None and label == 'ILDW-init Roy DCT':
        vals=json.loads(Path('/tmp/extra_metrics.json').read_text()).get('Roy DCT')
    if vals: d.append([label]+[str(vals[0])]+[f(x) for x in vals[1:]])
extra_metrics('Solver(ILDW) light shrinkage','sol_dir_solver_ildw_timing')
extra_metrics('Solver(ILDW) no shrinkage','sol_dir_solver_ildw_no_shrinkage')
extra_metrics('ILDW-init Roy DCT','sol_dir_roy_dct_ildw_outer50')
story += [tab(d,[1.5*inch]+[.55*inch]*10),PageBreak(),Paragraph('2. Taylor diagrams',S['Heading1'])]
for p in [TAYLOR/'combined_all_solvers.png']+[x for x in sorted(TJ.glob('*.png')) if x.name not in ('patch_clouds_normalized.png','combined_normalized.png')]:
    if p.exists(): story += [im(p),Paragraph(p.stem.replace('_',' '),S['BodyText']),PageBreak()]
story += [Paragraph('3. Wet/dry summary table',S['Heading1']),Paragraph('The wet/dry information is presented as a table rather than separate wet/dry images. Values are aggregated over all coverage bins and patches.',S['BodyText']),Paragraph('Intentional clutter note: the closely overlapping light-shrinkage and no-shrinkage traces are retained deliberately to show that the light-shrinkage term has negligible effect in this comparison.',S['BodyText'])]
wet=[['Solver','Mask','N pixels','Mean abs','Mean signed','Median abs']]
for name in sorted(k for k in C['ordered_sheets'] if k.startswith('CoverageStats_GTvs')):
    rr=C['ordered_sheets'][name]; label=name.replace('CoverageStats_GTvs','')
    for mask in ['rainy','nonrainy']:
        x=[z for z in rr if z.get('mask_type')==mask]
        if x:
            n=sum(float(z.get('n_pixels',0)) for z in x)
            wet.append([label,mask,f'{n:.0f}',f(sum(float(z.get('mean_abs',0))*float(z.get('n_pixels',0)) for z in x)/n),f(sum(float(z.get('mean_signed',0))*float(z.get('n_pixels',0)) for z in x)/n),f(sum(float(z.get('median_abs',0))*float(z.get('n_pixels',0)) for z in x)/n)])
story += [tab(wet,[2.1*inch, .8*inch, .8*inch, .9*inch, .9*inch, .9*inch]),PageBreak(),Paragraph('4. All-patch optimization behavior',S['Heading1']),Paragraph('Faint lines are individual patches; the thick orange line is the arithmetic mean per iteration.',S['BodyText'])]
for p in sorted((PLOT/'j_behavior').glob('*/all_patches.png')): story += [im(p,4.2*inch),Paragraph(p.parent.name.replace('_',' '),S['BodyText']),PageBreak()]
story += [Paragraph('5. D3 distance summaries',S['Heading1'])]
for n in ['distance_profiles_box_whisker']:
    ps=sorted((PLOT/n).glob('linear/k3/*.png'))
    if ps: story.append(Paragraph(n.replace('_',' ').title()+' - d3 (third-closest link)',S['Heading2']))
    for p in ps: story += [im(p,4.2*inch),Paragraph(p.stem.replace('_',' '),S['BodyText'])]
    if ps: story.append(PageBreak())
story += [Paragraph('6. Solver runtimes',S['Heading1'])]
rt=defaultdict(list)
for p in PIPE.glob('solutions/*/*_solution_optinfo.json'):
    if p.parent.name in {'sol_dir_solver_ildw', 'sol_dir_roy_dct_ildw_outer300'}:
        continue
    try: rt[p.parent.name].append(float(json.loads(p.read_text())['optimizer_seconds']))
    except: pass
r=[['Solver directory','N','Mean s','Median s','Total h']]
for n,v in sorted(rt.items()):
    if v:
        label=n.replace('sol_dir_solver_ildw_timing','Solver(ILDW) light shrinkage').replace('sol_dir_solver_ildw_no_shrinkage','Solver(ILDW) no shrinkage').replace('sol_dir_roy_dct_ildw_outer50','ILDW-init Roy DCT').replace('sol_dir_roy_dct_ildw_outer300','Roy DCT outer300')
        r.append([label,len(v),f(sum(v)/len(v)),f(sorted(v)[len(v)//2]),f(sum(v)/3600)])
story.append(tab(r,[3*inch,.5*inch,1*inch,1*inch,1*inch]) if len(r)>1 else Paragraph('No runtime metadata found.',S['BodyText']))
OUT.parent.mkdir(parents=True,exist_ok=True); SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=.55*inch,leftMargin=.55*inch,topMargin=.55*inch,bottomMargin=.55*inch).build(story); print(OUT)
