"""Unnormalized, within-patch-centered Taylor diagrams from saved rainfall fields.

Run: python build_unnormalized_taylor.py [--data-root PATH] [--stats-only]
Requires NumPy and Matplotlib. No solver is executed or modified.
"""
from pathlib import Path
import argparse
import json
import numpy as np

OUT = Path(__file__).resolve().parent
DEFAULT_ROOT = OUT.parents[1] / 'Compute-Link-Attenuations' / 'HundredPatches'
parser = argparse.ArgumentParser()
parser.add_argument('--data-root', type=Path, default=DEFAULT_ROOT)
parser.add_argument('--stats-only', action='store_true')
args = parser.parse_args()
ROOT = args.data_root
METHODS = [
    ('IDW', 'idw', 'sol_dir_idw', '#667085', 's'),
    ('ILDW', 'ildw', 'sol_dir_ildw', '#56A8C7', '^'),
    ('Solver(ILDW)', 'solver_ildw', 'sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long', '#23835C', 'D'),
    ('Solver(GT)', 'solver_gt', 'sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal', '#2563B0', 'o'),
    ('Convex solver', 'convex', 'sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal', '#D87819', 'o'),
    ('Homotopy solver', 'homotopy', 'sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal', '#A13D82', '+'),
]
paths = sorted((ROOT / 'gt_dir').glob('gt_*.npz'))
assert len(paths) == 100, f'Expected 100 patches in {ROOT}, found {len(paths)}'
records = {name: [] for name, *_ in METHODS}
for path in paths:
    patch = path.stem.removeprefix('gt_')
    with np.load(path) as z:
        gt = z['R_gt'].astype(np.float64)
    shape = gt.shape
    gt = gt.ravel()
    assert np.isfinite(gt).all()
    gc = gt - gt.mean()
    vg = float(np.mean(gc**2))
    assert vg > 0
    for name, slug, folder, color, marker in METHODS:
        with np.load(ROOT / 'pipeline' / 'solutions' / folder / f'est_input_{patch}_solution.npz') as z:
            f = z['R_hat'].astype(np.float64)
        assert f.shape == shape and np.isfinite(f).all()
        f = f.ravel()
        fc = f - f.mean()
        vf = float(np.mean(fc**2))
        assert vf > 0
        cov = float(np.mean(gc*fc))
        G, F = np.sqrt(vg), np.sqrt(vf)
        R = cov / (G*F)
        assert -1-1e-12 <= R <= 1+1e-12
        R = float(np.clip(R, -1, 1))
        E = float(np.sqrt(np.mean((fc-gc)**2)))
        bias = float(f.mean()-gt.mean())
        rmse = float(np.sqrt(np.mean((f-gt)**2)))
        X, Y = F*R, F*np.sqrt(max(0,1-R*R))
        assert np.isclose(E*E, vf+vg-2*cov, atol=1e-10)
        assert np.isclose(E, np.hypot(X-G,Y), atol=1e-10)
        assert np.isclose(rmse**2, E**2+bias**2, atol=1e-10)
        records[name].append(dict(patch=patch, pixels=len(gt), reference_sd=float(G),
                                  model_sd=float(F), correlation=R, covariance=cov,
                                  centered_rmse=E, mean_bias=bias, rmse=rmse,
                                  x=float(X), y=float(Y)))

summary = []
for name, *_ in METHODS:
    rows = records[name]
    G = float(np.sqrt(np.mean([p['reference_sd']**2 for p in rows])))
    F = float(np.sqrt(np.mean([p['model_sd']**2 for p in rows])))
    C = float(np.mean([p['covariance'] for p in rows]))
    R = C/(G*F)
    E = float(np.sqrt(np.mean([p['centered_rmse']**2 for p in rows])))
    X, Y = F*R, F*np.sqrt(max(0,1-R*R))
    assert np.isclose(E*E, F*F+G*G-2*F*G*R, atol=1e-10)
    assert np.isclose(E, np.hypot(X-G,Y), atol=1e-10)
    summary.append(dict(method=name, patches=len(rows), reference_sd=G, model_sd=F,
                        correlation=R, centered_rmse=E, x=float(X), y=float(Y)))
G = summary[0]['reference_sd']
assert all(np.isclose(p['reference_sd'],G) for p in summary)
report = dict(normalization='None: rainfall values and all distances remain in mm/h',
              centering='Subtract each field own mean separately within each patch',
              weighting='Equal patch weight 1/100, equal pixel weights 1/N_i within each patch',
              summary=summary, individual=records)
(OUT / 'statistics.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(summary=summary,reference_sd_range=[min(p['reference_sd'] for p in records['IDW']),
                                                        max(p['reference_sd'] for p in records['IDW'])]),indent=2))
if args.stats_only:
    raise SystemExit(0)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import Normalize
from matplotlib.ticker import MaxNLocator

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'text.color':'#253047',
                     'axes.labelcolor':'#253047','xtick.color':'#4B5563','ytick.color':'#4B5563'})
def save(fig, stem):
    for ext in ['png','svg']:
        fig.savefig(OUT/f'{stem}.{ext}',dpi=180,facecolor='white')
    plt.close(fig)

def setup(ax, limit, negative=False, reference=None, fontsize=9):
    maxangle = np.pi if negative else np.pi/2
    ax.set_thetamin(0); ax.set_thetamax(np.degrees(maxangle)); ax.set_ylim(0,limit)
    corr=np.array([0,.4,.6,.8,.9,.95,.99,1])
    if negative:
        corr=np.r_[-1,-.8,-.4,corr]
    ax.set_thetagrids(np.degrees(np.arccos(corr)),[f'{v:g}' for v in corr],fontsize=fontsize)
    ticks=MaxNLocator(nbins=5,steps=[1,2,2.5,5,10]).tick_values(0,limit)
    ticks=ticks[(ticks>0)&(ticks<limit)]
    ax.set_rgrids(ticks,[f'{v:g}' for v in ticks],angle=0,fontsize=fontsize-1)
    ax.grid(color='#E1E6EC',lw=.7)
    ax.spines['polar'].set_color('#A7B1BE')
    if reference is not None:
        t,rad=np.meshgrid(np.linspace(0,maxangle,350),np.linspace(0,limit,350))
        errors=np.sqrt(np.maximum(0,rad**2+reference**2-2*rad*reference*np.cos(t)))
        levels=MaxNLocator(nbins=7).tick_values(0,limit)
        levels=levels[(levels>0)&(levels<limit)]
        cs=ax.contour(t,rad,errors,levels=levels,colors='#6D9980',linestyles='--',linewidths=.8)
        ax.clabel(cs,inline=True,fontsize=fontsize-1,fmt='%g')
        ax.plot(np.linspace(0,maxangle,200),np.full(200,reference),color='#A4AFBC',lw=1)
        ax.scatter([0],[reference],marker='*',c='#172033',s=145,zorder=12,clip_on=False)

# Combined comparison: same physical reference for all six aggregate points.
limit=float(np.ceil(max([G]+[p['model_sd'] for p in summary])*1.12*2)/2)
negative=any(p['correlation']<0 for p in summary)
fig=plt.figure(figsize=(12.8,8.8))
ax=fig.add_axes([.065,.24,.43,.47],projection='polar')
detail=fig.add_axes([.61,.24,.31,.47])
setup(ax,limit,negative,reference=G)
ax.set_title('Combined Taylor diagram',loc='left',pad=27,fontsize=12,weight='bold')
ax.text(.5,-.10,'Radius: reconstructed standard deviation (mm/h)',transform=ax.transAxes,ha='center',fontsize=10)
points=np.array([[p['x'],p['y']] for p in summary]+[[G,0]])
span=max(np.ptp(points[:,0]),np.ptp(points[:,1]),.1)
pad=.13*span
xlo,xhi=points[:,0].min()-pad,points[:,0].max()+pad
ylo,yhi=-pad,points[:,1].max()+pad
xx,yy=np.meshgrid(np.linspace(xlo,xhi,350),np.linspace(ylo,yhi,350))
levels=MaxNLocator(nbins=6).tick_values(0,max(p['centered_rmse'] for p in summary)*1.2)
levels=levels[levels>0]
cs=detail.contour(xx,yy,np.hypot(xx-G,yy),levels=levels,colors='#6D9980',linestyles='--',linewidths=.8)
detail.clabel(cs,inline=True,fontsize=9,fmt='%g')
detail.contour(xx,yy,np.hypot(xx,yy),levels=np.linspace(0,limit,9)[1:],colors='#E1E6EC',linewidths=.7)
for r in [.6,.7,.8,.9,.95,.99,1]:
    t=np.linspace(0,limit,100)
    detail.plot(t*r,t*np.sqrt(1-r*r),color='#E1E6EC',lw=.7)
detail.scatter([G],[0],marker='*',c='#172033',s=145,zorder=12)
detail.set(xlim=(xlo,xhi),ylim=(ylo,yhi),aspect='equal')
detail.set_xticks([]); detail.set_yticks([])
for spine in detail.spines.values(): spine.set_color('#A7B1BE')
detail.set_title('Detail: same six points',fontsize=12,weight='bold',pad=15)
for row, (name,slug,folder,color,marker) in zip(summary,METHODS):
    kwargs=dict(marker=marker,s=80,c=color,edgecolors='white',linewidths=.6,zorder=5)
    if name=='Convex solver':
        kwargs=dict(marker='o',s=155,facecolors='none',edgecolors=color,linewidths=2,zorder=7)
    elif name=='Homotopy solver':
        kwargs=dict(marker='+',s=90,c=color,linewidths=2,zorder=8)
    ax.scatter([np.arccos(row['correlation'])],[row['model_sd']],**kwargs)
    detail.scatter([row['x']],[row['y']],**kwargs)
fig.text(.065,.953,'Unnormalized Taylor diagram: all six methods',fontsize=21,weight='bold')
fig.text(.065,.911,'100 patches per method | equal patch weights | means removed within patches | distances in mm/h',fontsize=11,color='#667085')
handles=[Line2D([],[],marker=m,linestyle='None',color=c,markersize=8,
                markerfacecolor='none' if name=='Convex solver' else c,label=name)
         for name,slug,folder,c,m in METHODS]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.060,.867),ncol=3,frameon=False,columnspacing=3)
fig.text(.065,.16,f'Ground-truth star: G = {G:.3f} mm/h. Green contours: combined centered RMSE (mm/h).',fontsize=11)
fig.text(.065,.108,'The combined error is the RMS of the 100 patch-level centered RMSEs; it is not their arithmetic mean.',fontsize=10,color='#667085')
fig.text(.065,.069,'Convex and homotopy nearly overlap. No division by ground-truth standard deviation is applied.',fontsize=10,color='#667085')
fig.text(.065,.032,'Correlation is shown on the outer arc. Mean bias is excluded.',fontsize=10,color='#667085')
save(fig,'combined_taylor_unnormalized')

# Individual patches have DIFFERENT reference SDs: no universal error contours.
refs=np.array([p['reference_sd'] for p in records['IDW']])
norm=Normalize(vmin=float(refs.min()),vmax=float(refs.max()))
cmap=plt.get_cmap('viridis')
maximum=max(p[k] for rows in records.values() for p in rows for k in ['model_sd','reference_sd'])
cloud_limit=float(np.ceil(maximum*1.08))
cloud_negative=any(p['correlation']<0 for rows in records.values() for p in rows)

def cloud(ax, name, color):
    setup(ax,cloud_limit,cloud_negative,fontsize=9)
    rows=records[name]
    for p in rows:
        c=cmap(norm(p['reference_sd']))
        # Cartesian interpolation guarantees a straight error segment after polar transformation.
        t=np.linspace(0,1,30)
        x=p['reference_sd']+(p['x']-p['reference_sd'])*t
        y=p['y']*t
        assert np.isclose(np.hypot(x[-1]-x[0],y[-1]-y[0]),p['centered_rmse'],atol=1e-10)
        ax.plot(np.arctan2(y,x),np.hypot(x,y),color=c,alpha=.22,lw=.65,zorder=2)
    colors=[cmap(norm(p['reference_sd'])) for p in rows]
    ax.scatter(np.zeros(100),refs,c=colors,marker='*',s=33,alpha=.55,zorder=3,clip_on=False)
    ax.scatter([np.arccos(p['correlation']) for p in rows],[p['model_sd'] for p in rows],
               c=colors,marker='o',s=24,alpha=.83,edgecolors='white',linewidths=.3,zorder=5)
    combined=next(r for r in summary if r['method']==name)
    ax.scatter([np.arccos(combined['correlation'])],[combined['model_sd']],c='#172033',
               marker='D',s=65,edgecolors='white',linewidths=.7,zorder=10)
    ax.scatter([0],[G],c='#172033',marker='*',s=135,zorder=12,clip_on=False)
    ax.set_title(name,fontsize=12,weight='bold',color=color,pad=25)

legend=[Line2D([],[],marker='o',linestyle='None',color='#318E8D',markersize=6,label='One patch / model point'),
        Line2D([],[],marker='*',linestyle='None',color='#318E8D',markersize=10,label='That patch\'s reference'),
        Line2D([],[],marker='D',linestyle='None',color='#172033',markersize=7,label='Combined model point'),
        Line2D([],[],marker='*',linestyle='None',color='#172033',markersize=11,label='Combined reference')]

fig,axes=plt.subplots(2,3,figsize=(15,12.9),subplot_kw={'projection':'polar'})
fig.subplots_adjust(left=.055,right=.94,bottom=.22,top=.80,wspace=.34,hspace=.40)
fig.text(.055,.953,'Individual patches without normalization',fontsize=22,weight='bold')
fig.text(.055,.919,'100 patches in each panel | identical axes | radius = model SD (mm/h) | outer arc = correlation',fontsize=11,color='#667085')
fig.legend(handles=legend,loc='upper left',bbox_to_anchor=(.05,.889),ncol=4,frameon=False,columnspacing=1.8)
for ax,(name,slug,folder,color,marker) in zip(axes.flat,METHODS):
    cloud(ax,name,color)
cax=fig.add_axes([.28,.126,.44,.018])
cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,orientation='horizontal')
cb.set_label('Patch ground-truth standard deviation (mm/h)',fontsize=10)
fig.text(.055,.062,'Each line joins a patch to its own reference star; its length equals that patch\'s centered RMSE in mm/h.',fontsize=11)
fig.text(.055,.033,'There is no single per-patch reference or shared centered-RMSE contour system. All 600 model points are included.',fontsize=10,color='#667085')
save(fig,'individual_taylor_unnormalized_all_methods')

for name,slug,folder,color,marker in METHODS:
    fig=plt.figure(figsize=(8.8,9.6))
    ax=fig.add_axes([.12,.27,.72,.52],projection='polar')
    cloud(ax,name,color)
    ax.set_title('')
    fig.text(.08,.951,f'{name}: unnormalized Taylor diagram',fontsize=19,weight='bold')
    fig.text(.08,.914,'100 individual patches | radius in mm/h | outer arc labelled by correlation',fontsize=11,color='#667085')
    fig.legend(handles=legend,loc='upper left',bbox_to_anchor=(.074,.884),ncol=2,frameon=False,columnspacing=1.2)
    cax=fig.add_axes([.24,.17,.50,.018])
    cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,orientation='horizontal')
    cb.set_label('Patch ground-truth standard deviation (mm/h)',fontsize=10)
    fig.text(.08,.086,'Each patch has its own reference star on the horizontal axis.',fontsize=11)
    fig.text(.08,.052,'Connecting segment length = centered RMSE (mm/h). Mean bias is excluded.',fontsize=10,color='#667085')
    fig.text(.08,.022,'Axis limits match the other five individual-method diagrams.',fontsize=10,color='#667085')
    save(fig,f'individual_{slug}_unnormalized')
print(f'Wrote eight figures in PNG and SVG, plus statistics.json, to {OUT}')
