"""Explore saved benchmark fields; do not rerun or change any solver."""
from pathlib import Path
import json
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path('/Users/isoto/Projects/Rainfall-Estimation/Compute-Link-Attenuations/HundredPatches')
OUT = Path(__file__).parent
METHODS = [
    ('IDW', 'sol_dir_idw', '#667085'),
    ('ILDW', 'sol_dir_ildw', '#56A8C7'),
    ('Solver(ILDW)', 'sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long', '#23835C'),
    ('Solver(GT)', 'sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal', '#2563B0'),
    ('Convex solver', 'sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal', '#D87819'),
    ('Homotopy solver', 'sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal', '#A13D82'),
]
CASE_IDS = ['202301280900_patch000', '202301310900_patch000']
GROUP_COLORS = {False: '#2876A5', True: '#C96C27'}
all_records = {name: [] for name, *_ in METHODS}
pairs = []
paths = sorted((ROOT/'gt_dir').glob('gt_*.npz'))
assert len(paths) == 100
for path in paths:
    patch = path.stem.removeprefix('gt_')
    short = patch.removeprefix('RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_')
    with np.load(path) as z:
        ref = np.asarray(z['R_gt'], dtype=float)
    shape = ref.shape
    assert np.isfinite(ref).all()
    ref = ref.ravel()
    sd = float(np.std(ref))
    assert sd > 0
    u = (ref-ref.mean())/sd
    fields, metrics = {}, {}
    for name, folder, _ in METHODS:
        p = ROOT/'pipeline/solutions'/folder/f'est_input_{patch}_solution.npz'
        with np.load(p) as z:
            field = np.asarray(z['R_hat'], dtype=float)
        assert field.shape == shape and np.isfinite(field).all()
        field = field.ravel()
        fields[name] = field
        v = (field-field.mean())/sd
        s = float(np.std(v))
        assert s > 0
        r = float(np.clip(np.mean(u*v)/s,-1,1))
        e = float(np.sqrt(np.mean((v-u)**2)))
        bias = float(field.mean()-ref.mean())
        rmse = float(np.sqrt(np.mean((field-ref)**2)))
        assert np.isclose(e*e, s*s+1-2*s*r, atol=1e-10)
        assert np.isclose(rmse*rmse, e*e*sd*sd+bias*bias, atol=1e-10)
        rec = dict(patch=short,n_pixels=len(ref),ref_sd=sd,s=s,r=r,e=e,bias=bias,rmse=rmse,
                   x=s*r,y=s*np.sqrt(max(0,1-r*r)))
        all_records[name].append(rec)
        metrics[name] = rec
    a, b = metrics['Solver(GT)'], metrics['Convex solver']
    assert a['rmse'] > 0
    q = b['rmse']/a['rmse']
    D = float(np.sqrt(np.mean((fields['Convex solver']-fields['Solver(GT)'])**2)))
    difference = fields['Convex solver']-fields['Solver(GT)']
    Dc = float(np.std(difference))/sd
    td = float(np.hypot(a['x']-b['x'],a['y']-b['y']))
    assert abs(b['rmse']-a['rmse']) <= D+1e-10 <= b['rmse']+a['rmse']+2e-10
    assert td <= Dc+1e-9  # projection can hide differences in residual directions
    pairs.append(dict(patch=short,q=q,high_ratio=q>2,D_mm_h=D,D_normalized=D/sd,
                      centered_D_normalized=Dc,taylor_point_distance=td,
                      rmse_gt=a['rmse'],rmse_convex=b['rmse'],
                      map_correlation=float(np.corrcoef(fields['Solver(GT)'],fields['Convex solver'])[0,1]),
                      gt=a,convex=b))
assert sum(p['high_ratio'] for p in pairs) == 24

def describe(values):
    vals = np.array(values)
    return dict(zip(['min','q25','median','q75','max'],map(float,np.quantile(vals,[0,.25,.5,.75,1]))))

summary = {}
for flag,label in [(False,'q_le_2'),(True,'q_gt_2')]:
    sub = [p for p in pairs if p['high_ratio']==flag]
    summary[label] = dict(n=len(sub), **{k:describe([p[k] for p in sub]) for k in
                          ['q','D_mm_h','D_normalized','map_correlation','taylor_point_distance']})
summary['case_studies'] = [p for p in pairs if p['patch'] in CASE_IDS]
near_equal = [p for p in pairs if abs(p['q']-1)<=.05]
summary['within_5_percent_rmse'] = dict(n=len(near_equal),D_normalized=describe([p['D_normalized'] for p in near_equal]),
    largest_disagreement=max(near_equal,key=lambda p:p['D_normalized']))
summary['ranges'] = {name:dict(s=describe([p['s'] for p in rec]),r=describe([p['r'] for p in rec])) for name,rec in all_records.items()}
(OUT/'patch_metrics.json').write_text(json.dumps(dict(methods=all_records,paired_comparisons=pairs),indent=2))
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='ranges'},indent=2))
print('Global s and r ranges:', min(p['s'] for rec in all_records.values() for p in rec),
      max(p['s'] for rec in all_records.values() for p in rec),
      min(p['r'] for rec in all_records.values() for p in rec),max(p['r'] for rec in all_records.values() for p in rec))
if '--stats-only' in sys.argv:
    sys.exit(0)

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                     'text.color':'#253047','axes.labelcolor':'#253047',
                     'xtick.color':'#4B5563','ytick.color':'#4B5563'})

def save(fig, stem):
    for ext in ['png','svg']:
        fig.savefig(OUT/f'{stem}.{ext}',dpi=180,facecolor='white')
    plt.close(fig)

def taylor_axes(ax):
    ax.set_thetamin(0); ax.set_thetamax(90); ax.set_ylim(0,1.12)
    correlations = np.array([0,.4,.6,.8,.9,.95,.99,1])
    ax.set_thetagrids(np.degrees(np.arccos(correlations)),[f'{r:g}' for r in correlations],fontsize=9)
    ax.set_rgrids([.25,.5,.75,1],angle=0,fontsize=8)
    ax.grid(color='#E1E6EC',lw=.7)
    ax.spines['polar'].set_color('#A7B1BE')
    t,rad=np.meshgrid(np.linspace(0,np.pi/2,300),np.linspace(0,1.12,300))
    err=np.sqrt(np.maximum(0,rad*rad+1-2*rad*np.cos(t)))
    cs=ax.contour(t,rad,err,levels=[.1,.25,.5,.75,1],colors='#79A38C',linestyles='--',linewidths=.65)
    ax.clabel(cs,inline=True,fontsize=8,fmt='%g')
    ax.plot(np.linspace(0,np.pi/2,200),np.ones(200),color='#9AA7B8',lw=1)
    ax.scatter([0],[1],marker='*',c='#172033',s=120,zorder=12,clip_on=False)

def highlight_cases(ax, rec):
    for case_id, marker, color, label in zip(CASE_IDS,['o','s'],['#B82E45','#6D38A0'],['I','II']):
        p=next(r for r in rec if r['patch']==case_id)
        theta=np.arccos(p['r'])
        ax.scatter([theta],[p['s']],marker=marker,s=140,facecolors='none',edgecolors=color,lw=1.8,zorder=11)
        ax.annotate(label,(theta,p['s']),xytext=(8,6),textcoords='offset points',color=color,fontsize=9,weight='bold',zorder=13)

fig,axes=plt.subplots(2,3,figsize=(14.3,11.3),subplot_kw={'projection':'polar'})
fig.subplots_adjust(left=.055,right=.94,bottom=.13,top=.80,wspace=.33,hspace=.38)
fig.text(.055,.959,'Where do the 100 patches sit for each method?',fontsize=21,weight='bold')
fig.text(.055,.924,'Six normalized Taylor clouds • identical axes • one dot per patch',fontsize=12,color='#667085')
for ax,(name,_,color) in zip(axes.flat,METHODS):
    taylor_axes(ax)
    rec=all_records[name]
    ax.scatter([np.arccos(p['r']) for p in rec],[p['s'] for p in rec],s=20,c=color,alpha=.62,edgecolors='white',lw=.3,zorder=5)
    S=np.sqrt(np.mean([p['s']**2 for p in rec])); R=np.mean([p['s']*p['r'] for p in rec])/S
    ax.scatter([np.arccos(R)],[S],marker='D',s=55,c='#172033',edgecolors='white',lw=.6,zorder=9)
    highlight_cases(ax,rec)
    ax.set_title(name,fontsize=12,weight='bold',pad=23)
handles=[Line2D([],[],marker='*',color='#172033',linestyle='None',markersize=11,label='Ground truth'),
         Line2D([],[],marker='D',color='#172033',linestyle='None',markersize=7,label='Combined point'),
         Line2D([],[],marker='o',color='#B82E45',mfc='none',linestyle='None',markersize=9,label='Case study I'),
         Line2D([],[],marker='s',color='#6D38A0',mfc='none',linestyle='None',markersize=9,label='Case study II')]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.05,.894),ncol=4,frameon=False,columnspacing=2.2)
fig.text(.055,.065,'Radius = reconstructed SD / ground-truth SD. Outer arc = correlation. Green contours = normalized centered RMSE.',fontsize=10)
fig.text(.055,.033,'Each patch uses its own reference normalization. Cloud spread is variation between patches; mean bias is excluded.',fontsize=10,color='#667085')
save(fig,'solver_taylor_clouds')

def detail_axes(ax):
    # Same Euclidean Taylor geometry, enlarged around the paired points.
    xlo,xhi,ylo,yhi=.55,1.055,-.025,.60
    xx,yy=np.meshgrid(np.linspace(xlo,xhi,350),np.linspace(ylo,yhi,350))
    cs=ax.contour(xx,yy,np.hypot(xx-1,yy),levels=[.1,.2,.3,.4,.5,.6],colors='#79A38C',linestyles='--',linewidths=.7)
    ax.clabel(cs,inline=True,fontsize=8,fmt='%g')
    ax.contour(xx,yy,np.hypot(xx,yy),levels=[.6,.7,.8,.9,1],colors='#D3DAE3',linewidths=.8)
    for r in [.85,.9,.95,.99,1]:
        t=np.linspace(0,1.3,300)
        ax.plot(t*r,t*np.sqrt(1-r*r),color='#DDE3EB',lw=.7,zorder=0)
    ax.set(xlim=(xlo,xhi),ylim=(ylo,yhi),aspect='equal')
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_color('#B4BECC')
    ax.scatter([1],[0],marker='*',c='#172033',s=150,zorder=12)

fig,axes=plt.subplots(1,3,figsize=(14.8,7.4))
fig.subplots_adjust(left=.05,right=.96,bottom=.22,top=.74,wspace=.24)
fig.text(.05,.95,'Do the same patches move differently between solvers?',fontsize=20,weight='bold')
fig.text(.05,.904,'Magnified Taylor geometry • each segment joins Solver(GT) and convex results for one patch',fontsize=11,color='#667085')
for ax,flag,title in zip(axes,[None,False,True],['All 100 patch pairs','Ratio ≤ 2: 76 patch pairs','Ratio > 2: 24 patch pairs']):
    detail_axes(ax)
    sub=pairs if flag is None else [p for p in pairs if p['high_ratio']==flag]
    for p in sub:
        a,b=p['gt'],p['convex']; color=GROUP_COLORS[p['high_ratio']]
        ax.plot([a['x'],b['x']],[a['y'],b['y']],color=color,alpha=.23 if flag is None else .42,lw=.9,zorder=2)
        ax.scatter(a['x'],a['y'],s=19,marker='o',c=color,alpha=.7,edgecolors='white',lw=.25,zorder=4)
        ax.scatter(b['x'],b['y'],s=23,marker='^',c=color,alpha=.7,edgecolors='white',lw=.25,zorder=5)
    for p in sub:
        if p['patch'] not in CASE_IDS: continue
        a,b=p['gt'],p['convex']; label='I' if p['patch']==CASE_IDS[0] else 'II'
        ax.plot([a['x'],b['x']],[a['y'],b['y']],color='#172033',lw=1.8,zorder=7)
        ax.scatter([a['x'],b['x']],[a['y'],b['y']],s=68,facecolors='none',edgecolors='#172033',lw=1.1,zorder=8)
        ax.annotate(f'Case {label}',(b['x'],b['y']),xytext=(8,12 if label=='II' else -18),textcoords='offset points',fontsize=9,weight='bold',zorder=12)
    ax.set_title(title,loc='left',fontsize=12,weight='bold',pad=14)
handles=[Line2D([],[],marker='o',color='#485467',linestyle='None',markersize=6,label='Solver(GT)'),
         Line2D([],[],marker='^',color='#485467',linestyle='None',markersize=7,label='Convex solver'),
         Line2D([],[],color=GROUP_COLORS[False],lw=2,label='q ≤ 2'),
         Line2D([],[],color=GROUP_COLORS[True],lw=2,label='q > 2')]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.045,.861),ncol=4,frameon=False,columnspacing=2.0)
fig.text(.05,.14,'q = RMSE(Convex) / RMSE(Solver(GT)). The group panels repeat the pairs from the left panel.',fontsize=11)
fig.text(.05,.09,'Green contours measure distance to ground truth. Segment length compares Taylor statistics, not rainfall fields.',fontsize=10,color='#667085')
fig.text(.05,.048,'All points are inside the displayed region. Mean bias is excluded; the ratio groups use ordinary, uncentered RMSE.',fontsize=10,color='#667085')
for p in pairs:
    for r in [p['gt'],p['convex']]: assert .55<=r['x']<=1.055 and -.025<=r['y']<=.60
save(fig,'paired_taylor_groups')

fig,axes=plt.subplots(1,2,figsize=(12.8,7.3))
fig.subplots_adjust(left=.085,right=.95,bottom=.23,top=.77,wspace=.23)
fig.text(.085,.95,'Do similar RMSE values mean similar rainfall maps?',fontsize=20,weight='bold')
fig.text(.085,.906,'Direct pixelwise disagreement between Solver(GT) and convex reconstructions • includes differences in mean',fontsize=10.5,color='#667085')
for ax,key,title,ylabel,ylim in zip(axes,['D_normalized','D_mm_h'],
        ['Relative to each patch’s rainfall variability','In rainfall units'],
        ['D / ground-truth SD','Direct field disagreement D (mm/h)'],[(.008,.85),(.004,7)]):
    for flag in [False,True]:
        sub=[p for p in pairs if p['high_ratio']==flag]
        ax.scatter([p['q'] for p in sub],[p[key] for p in sub],s=39,color=GROUP_COLORS[flag],
                   marker='^' if flag else 'o',alpha=.85,edgecolors='white',lw=.5,zorder=3)
    ax.set(xscale='log',yscale='log',xlim=(.88,14),ylim=ylim,xlabel='RMSE ratio q',ylabel=ylabel)
    ax.set_xticks([1,2,3,5,10],['1','2','3','5','10'])
    ticks=[.01,.03,.1,.3] if key=='D_normalized' else [.01,.03,.1,.3,1,3]
    ax.set_yticks(ticks,[f'{v:g}' for v in ticks]); ax.minorticks_off()
    ax.axvline(2,color='#485467',ls='--',lw=1.1)
    ax.grid(color='#E1E6EC',lw=.7); ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.set_title(title,loc='left',fontsize=12,weight='bold',pad=13)
    for p in summary['case_studies']:
        label='I' if p['patch']==CASE_IDS[0] else 'II'
        ax.scatter(p['q'],p[key],s=150,marker='*',c='#172033',edgecolors='white',lw=.5,zorder=5)
        ax.annotate(f'Case {label}',(p['q'],p[key]),xytext=(10,-20 if label=='I' else 13),textcoords='offset points',fontsize=10,weight='bold')
handles=[Line2D([],[],marker='o',color=GROUP_COLORS[False],linestyle='None',label='q ≤ 2: 76 patches'),
         Line2D([],[],marker='^',color=GROUP_COLORS[True],linestyle='None',label='q > 2: 24 patches')]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.08,.861),ncol=2,frameon=False,columnspacing=3)
fig.text(.085,.13,'D = √mean[(Convex rainfall − Solver(GT) rainfall)²]. Lower D means more similar reconstructed fields.',fontsize=11)
fig.text(.085,.086,'Both axes use logarithmic scales. The vertical line is the existing ratio threshold; no new D threshold is imposed.',fontsize=10,color='#667085')
fig.text(.085,.043,'The groups have markedly different typical disagreement, but their disagreement ranges overlap.',fontsize=10,color='#667085')
save(fig,'field_disagreement_vs_ratio')

low=[p for p in pairs if not p['high_ratio']]; high=[p for p in pairs if p['high_ratio']]
overlap_low=[p for p in low if p['D_normalized']>=min(a['D_normalized'] for a in high)]
overlap_high=[p for p in high if p['D_normalized']<=max(a['D_normalized'] for a in low)]
summary['normalized_range_overlap'] = dict(low_group_count=len(overlap_low),high_group_count=len(overlap_high),
    low_group_patches=[{k:p[k] for k in ['patch','q','D_mm_h','D_normalized']} for p in overlap_low])
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print('Range overlap:', json.dumps(summary['normalized_range_overlap'],indent=2))
print('Created three PNG/SVG figures and two JSON data files in', OUT)
