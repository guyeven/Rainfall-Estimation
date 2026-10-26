#!/usr/bin/env python3
"""Recompute Journal.tex summary tables from both 100-patch benchmarks."""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

sys_path = str(Path(__file__).resolve().parents[3] / "Compute-Link-Attenuations")
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)
from batch_analyze_multi import assign_bin_labels, compute_dk_maps_sampled_points, load_est_payload

ROOT=Path(__file__).resolve().parents[3]
C=ROOT/"Compute-Link-Attenuations"
J=ROOT/"output/journal_revision"
WINTER=C/"HundredPatches"
SUMMER=C/"June2023HundredPatches"
W_CACHE=json.loads((WINTER/"pipeline/batch_analyze_output/stats_report_cache.json").read_text())
S_CACHE=json.loads((SUMMER/"pipeline/June2023HundredPatches/pipeline/batch_analyze_output_final/stats_report_cache.json").read_text())
W_MAP={"IDW":"IDW","ILDW":"ILDW","Solver(ILDW)":"OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG","Convex Solver":"OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL","Homotopy Solver":"OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL","Solver(GT)":"OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL"}
S_MAP={"IDW":"IDW","ILDW":"ILDW","Solver(ILDW)":"Solver(ILDW) light shrinkage","Convex Solver":"Convex Solver light shrinkage","Homotopy Solver":"Homotopy Solver light shrinkage"}
COMMON=["IDW","ILDW","Solver(ILDW)","Convex Solver","Homotopy Solver"]
ALL=["IDW","ILDW","Solver(ILDW)","Convex Solver","Homotopy Solver","Solver(GT)"]
MACRO={"IDW":r"\IDW","ILDW":r"\ILDW","Solver(ILDW)":r"\solverILDW","Convex Solver":r"\ConvexSolver","Homotopy Solver":r"\Homotopy","Solver(GT)":r"\solverGT"}


def cache_rows(cache, sheet):
    return cache["ordered_sheets"].get(sheet, [])

def sample_sd(x):
    return statistics.stdev(x) if len(x)>1 else 0.0

def fmt(x, digits=2):
    if abs(x)<0.5*10**(-digits): x=0.0
    return f"{x:.{digits}f}"

def pooled_rows(rows):
    return [r for r in rows if r.get("patch_key") and r.get("distance_bin_m") is not None]


def full_patch_metrics():
    out={m:{"winter":[],"summer":[]} for m in ALL}
    for season,base,map_ in [("winter",WINTER,W_MAP),("summer",SUMMER,S_MAP)]:
        for gt_path in sorted((base/"gt_dir").glob("gt_*.npz")):
            patch=gt_path.stem.removeprefix("gt_")
            with np.load(gt_path) as z: gt=np.asarray(z["R_gt"],dtype=np.float64)
            for method in ALL:
                if season=="summer" and method=="Solver(GT)":
                    sol_dir=base/"pipeline/solutions/sol_dir_solver_gt_light_shrinkage"
                else:
                    dirname=(map_.get(method) if season=="summer" else map_[method])
                    if season=="winter":
                        dirname={
                            "IDW":"sol_dir_idw","ILDW":"sol_dir_ildw",
                            "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL":"sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal",
                            "OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG":"sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long",
                            "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL":"sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal",
                            "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL":"sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal"}[dirname]
                    else:
                        dirname={"IDW":"sol_dir_idw","ILDW":"sol_dir_ildw","Solver(ILDW) light shrinkage":"sol_dir_solver_ildw_timing","Convex Solver light shrinkage":"sol_dir_convex_light_shrinkage","Homotopy Solver light shrinkage":"sol_dir_homotopy_light_shrinkage"}[dirname]
                    sol_dir=base/"pipeline/solutions"/dirname
                solution=sol_dir/f"est_input_{patch}_solution.npz"
                if not solution.exists(): raise FileNotFoundError(solution)
                with np.load(solution) as z: pred=np.asarray(z["R_hat"],dtype=np.float64)
                if gt.shape!=pred.shape: raise ValueError(f"Shape mismatch {patch} {method}")
                d=pred-gt; sg=float(np.std(gt)); sp=float(np.std(pred))
                gt_mean=float(np.mean(gt))
                corr=float(np.corrcoef(gt.ravel(),pred.ravel())[0,1]) if sg and sp else 0.0
                wet=gt>=0.6; predwet=pred>=0.6; dry=~wet
                tp=int(np.count_nonzero(wet&predwet)); fn=int(np.count_nonzero(wet&~predwet)); fp=int(np.count_nonzero(dry&predwet)); tn=int(np.count_nonzero(dry&~predwet)); n=gt.size
                rmse=float(np.sqrt(np.mean(d*d))); bias=float(np.mean(d))
                out[method][season].append({"patch":patch,"rmse":rmse,"bias":bias,"nrmse":rmse/gt_mean if gt_mean else float("nan"),"normalized_bias":bias/gt_mean if gt_mean else float("nan"),"pearson":corr,"tp":tp/n,"fp":fp/n,"tn":tn/n,"fn":fn/n,"fp_dry":fp/max(1,int(dry.sum())),"tn_dry":tn/max(1,int(dry.sum())),"fn_wet":fn/max(1,int(wet.sum())),"tp_wet":tp/max(1,int(wet.sum()))})
    for method in ALL:
        if len(out[method]["winter"])!=100 or len(out[method]["summer"])!=100: raise RuntimeError(f"Wrong patch count for {method}")
    return out


def t_cdf(t,df):
    # Student-t CDF via the regularized incomplete beta function.
    def betacf(a,b,x):
        qab=a+b; qap=a+1; qam=a-1; c=1.0; d=1.0-qab*x/qap
        if abs(d)<1e-300: d=1e-300
        d=1.0/d; h=d
        for m in range(1,301):
            m2=2*m; aa=m*(b-m)*x/((qam+m2)*(a+m2)); d=1+aa*d
            if abs(d)<1e-300:d=1e-300
            c=1+aa/c
            if abs(c)<1e-300:c=1e-300
            d=1/d; h*=d*c
            aa=-(a+m)*(qab+m)*x/((a+m2)*(qap+m2)); d=1+aa*d
            if abs(d)<1e-300:d=1e-300
            c=1+aa/c
            if abs(c)<1e-300:c=1e-300
            d=1/d; delta=d*c; h*=delta
            if abs(delta-1)<3e-14: break
        return h
    def ibeta(a,b,x):
        if x<=0:return 0.0
        if x>=1:return 1.0
        bt=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
        if x<(a+1)/(a+b+2): return bt*betacf(a,b,x)/a
        return 1-bt*betacf(b,a,1-x)/b
    x=df/(df+t*t); tail=.5*ibeta(df/2,.5,x)
    return tail if t<0 else 1-tail


def paired_table(metrics, field, use_abs=False, caption="", label=""):
    idw={x["patch"]:(abs(x[field]) if use_abs else x[field]) for s in ("winter","summer") for x in metrics["IDW"][s]}
    methods=["ILDW","Solver(ILDW)","Convex Solver","Homotopy Solver","Solver(GT)"]
    title=(r"mean $|\mathrm{Bias}|$" if use_abs else "mean")
    header=(r"Comparison & $n$ & wins A:\IDW & mean A & mean \IDW & mean diff & SD diff & SE & $t$ & one-sided $p$ & 99\% upper bound & decision \\")
    s=[r"\begin{table}[H]\centering\scriptsize\setlength{\tabcolsep}{3pt}\resizebox{\textwidth}{!}{\begin{tabular}{lrrrrrrrrrrl}",r"\toprule",header,r"\midrule"]
    for m in methods:
        vals={x["patch"]:(abs(x[field]) if use_abs else x[field]) for seas in ("winter","summer") for x in metrics[m][seas]}
        keys=sorted(set(idw)&set(vals)); dif=[vals[k]-idw[k] for k in keys]; n=len(dif); mean=sum(dif)/n; sd=sample_sd(dif); se=sd/math.sqrt(n); t=mean/se if se else 0; p=t_cdf(t,n-1); upper=mean+2.345*se
        a=sum(x<0 for x in dif); b=sum(x>0 for x in dif); ties=n-a-b
        macro=MACRO[m]; dec="reject" if p<.01 else "retain"
        p_mantissa, p_exponent = f"{p:.2e}".split("e")
        p_tex = f"${p_mantissa} \\times 10^{{{int(p_exponent)}}}$"
        row=f"{macro} - \\IDW & {n} & {a}:{b}"+(f" ({ties} ties)" if ties else "")+f" & {fmt(sum(vals.values())/n)} & {fmt(sum(idw[k] for k in keys)/n)} & {fmt(mean)} & {fmt(sd)} & {fmt(se)} & {fmt(t)} & {p_tex} & {fmt(upper)} & {dec}"; s.append(row+" "+chr(92)*2)
    s += [r"\bottomrule\end{tabular}}",caption,label,r"\end{table}"]
    return "\n".join(s)


def update_tables(metrics):
    outdir=J/"tables"
    # Patch-wide summary: all six methods have 100 valid winter and summer points.
    rows=[r"\begin{table}[htbp]\centering\small\begin{tabular}{lrrrrrr}",r"\toprule Method & $n$ & RMSE & NRMSE & Bias & Normalized bias & Pearson $r$ \\",r"\midrule"]
    for m in ALL:
        allrows=metrics[m]["winter"]+metrics[m]["summer"]; n=len(allrows)
        pm=chr(92)+"pm"; row=f"{MACRO[m]} & {n} & ${fmt(statistics.mean(x['rmse'] for x in allrows))} {pm} {fmt(sample_sd([x['rmse'] for x in allrows]))}$ & ${fmt(statistics.mean(x['nrmse'] for x in allrows),3)} {pm} {fmt(sample_sd([x['nrmse'] for x in allrows]),3)}$ & ${fmt(statistics.mean(x['bias'] for x in allrows))} {pm} {fmt(sample_sd([x['bias'] for x in allrows]))}$ & ${fmt(statistics.mean(x['normalized_bias'] for x in allrows),3)} {pm} {fmt(sample_sd([x['normalized_bias'] for x in allrows]),3)}$ & ${fmt(statistics.mean(x['pearson'] for x in allrows),3)} {pm} {fmt(sample_sd([x['pearson'] for x in allrows]),3)}$"; rows.append(row+" "+chr(92)*2)
    rows += [r"\\",r"\bottomrule\end{tabular}",r"\caption{Patchwise reconstruction metrics across the full 200-patch benchmark (100 winter and 100 summer patches). Each entry is the mean $\pm$ sample SD of one value per patch. NRMSE and normalized bias are each patch's RMSE or signed bias divided by that patch's mean ground-truth rain rate.}",r"\label{tab:overall-solver-summary}",r"\end{table}"]
    (outdir/"RMSE-bias-Pearson.tex").write_text("\n".join(rows)+"\n")
    # Paired tests and sign counts.
    (J/"tables/paired_rmse_200.tex").write_text(paired_table(metrics,"rmse",caption=r"\caption{One-sided paired $t$ tests of patchwise RMSE differences against \IDW\ across all 200 patches. Negative differences favor method A; upper bounds are one-sided 99\% bounds.}",label=r"\label{tab:paired-rmse-t-test}"))
    (J/"tables/paired_bias_200.tex").write_text(paired_table(metrics,"bias",use_abs=True,caption=r"\caption{One-sided paired $t$ tests of patchwise absolute-bias differences against \IDW\ across all 200 patches. Negative differences favor method A.}",label=r"\label{tab:paired-absolute-bias-test}"))
    ptab=[r"\begin{table}[H]\centering\begin{tabular}{lrr}",r"\toprule Comparison & wins A:\IDW & $n$ \\",r"\midrule"]
    for m in ALL[1:]:
        idw={x["patch"]:x["pearson"] for sea in ("winter","summer") for x in metrics["IDW"][sea]}
        vals={x["patch"]:x["pearson"] for sea in ("winter","summer") for x in metrics[m][sea]}
        keys=set(idw)&set(vals); a=sum(vals[k]>idw[k] for k in keys); b=sum(vals[k]<idw[k] for k in keys); ties=len(keys)-a-b
        row=f"{MACRO[m]} - \\IDW & {a}:{b}"+(f" ({ties} ties)" if ties else "")+f" & {len(keys)}"; ptab.append(row+" "+chr(92)*2)
    ptab += [r"\bottomrule\end{tabular}",r"\caption{Patchwise Pearson correlation wins over IDW across all 200 patches.}",r"\label{tab:paired-pearson-sign-test}",r"\end{table}"]
    (J/"tables/pearson_wins_200.tex").write_text("\n".join(ptab)+"\n")
    # Wet/dry fractions are computed patchwise from all 200 GT and predictions.
    conf=[r"\begin{table}[htbp]\centering\scriptsize\setlength{\tabcolsep}{3pt}\resizebox{\textwidth}{!}{\begin{tabular}{lrrrrrrrrr}",r"\toprule Method & $n$ & \multicolumn{4}{c}{Fraction of all pixels} & \multicolumn{4}{c}{Conditional rate} \\",r"\cmidrule(lr){3-6}\cmidrule(lr){7-10}",r"& & TP & FP & TN & FN & TP & FP & TN & FN \\",r"\midrule"]
    for m in ALL:
        rr=[x for sea in ("winter","summer") for x in metrics[m][sea]]
        cells=[statistics.mean(x[k] for x in rr) for k in ("tp","fp","tn","fn","tp_wet","fp_dry","tn_dry","fn_wet")]
        conf.append(f"{MACRO[m]} & 200 & "+" & ".join(fmt(x,3) for x in cells)+r" \\")
    conf += [r"\\",r"\bottomrule\end{tabular}}",r"\caption{Patch-averaged wet/dry confusion at the $0.6$ mm/h threshold across all 200 patches. Fraction columns are normalized by each patch's pixel count; conditional TP/FN rates use wet GT pixels and FP/TN rates use dry GT pixels.}",r"\label{tab:wet-dry-confusion-merged}",r"\end{table}"]
    (outdir/"wet-dry-confusion-matrix.tex").write_text("\n".join(conf)+"\n")


def patch_and_link_tables():
    # Ground-truth rain-pattern descriptors.
    desc={k:[] for k in ["wet","wetmean","p95","cv","above5","relgrad"]}
    for base in (WINTER,SUMMER):
        for p in sorted((base/"gt_dir").glob("gt_*.npz")):
            with np.load(p) as z: a=np.asarray(z["R_gt"],dtype=np.float64)
            wet=a[a>=.6]; gy,gx=np.gradient(a,.125)
            desc["wet"].append(float(wet.size/a.size)); desc["wetmean"].append(float(wet.mean()) if wet.size else 0)
            desc["p95"].append(float(np.percentile(wet,95)) if wet.size else 0.0); desc["cv"].append(float(wet.std()/wet.mean()) if wet.size and wet.mean() else 0)
            desc["above5"].append(float(np.mean(a>5))); desc["relgrad"].append(float(np.mean(np.hypot(gx,gy))/a.mean()) if a.mean() else 0)
    labs=[("wet","Wet fraction",3),("wetmean",r"Mean wet rain rate ($\mathrm{mm/h}$)",2),("p95",r"95th percentile wet rain rate ($\mathrm{mm/h}$)",2),("cv","Coefficient of variation, wet pixels",3),("above5",r"Area fraction above $5\,\mathrm{mm/h}$",3),("relgrad",r"Relative gradient ($\mathrm{km}^{-1}$)",3)]
    lines=[r"\begin{table}[!htbp]\centering\small\begin{tabular}{lrrrrr}",r"\toprule Descriptor & Mean & SD & Min & Median & Max \\",r"\midrule"]
    for k,label,dig in labs:
        x=desc[k]; lines.append(label+" & "+" & ".join(fmt(v,dig) for v in [statistics.mean(x),sample_sd(x),min(x),statistics.median(x),max(x)])+" "+chr(92)*2)
    lines += [r"\bottomrule\end{tabular}",r"\caption{Rain-pattern descriptors across all 200 benchmark patches, summarized from one value per patch. Wet pixels have rain rate at least 0.6 mm/h. For each patch, the wet-pixel coefficient of variation (CV) is the standard deviation of wet-pixel rain rates divided by their mean.\newline Relative gradient is defined as follows. At each pixel, the local gradient magnitude is $\sqrt{g_x^2+g_y^2}$. Let $h=0.125$ km be the spacing between adjacent pixel centers. At an interior pixel $p$, $g_x(p)=\tfrac12\bigl[(R(p)-R(p_{\leftarrow}))/h+(R(p_{\rightarrow})-R(p))/h\bigr]$, averaging the slope from the left neighbor to $p$ and the slope from $p$ to its right neighbor. Similarly, $g_y(p)=\tfrac12\bigl[(R(p)-R(p_{\uparrow}))/h+(R(p_{\downarrow})-R(p))/h\bigr]$, using the pixel above and the pixel below. At an edge where a neighbor is missing, the available one-sided slope is used. Thus both components are in rain rate per kilometre. Relative gradient is the average of these magnitudes over all pixels divided by the patch mean rain rate.}",r"\label{tab:patch_rain_patterns}",r"\end{table}"]
    (J/"tables/patch_rain_patterns.tex").write_text("\n".join(lines)+"\n")

    # All link summaries are first computed within each patch, then summarized
    # across the 200 independent patches.
    patch_link={k:[] for k in ["pairs","paths","length","frequency","endpoints","maxdegree","single_pct","double_pct"]}
    for base in (WINTER,SUMMER):
        for p in sorted((base/"est_dir").glob("est_input_*.json")):
            d=json.loads(p.read_text()); links=d["links"]
            freq_by_path={}; endpoints=set(); degree={}; length_by_path={}
            for link in links:
                a=(round(float(link["x0_m"]),3),round(float(link["y0_m"]),3)); b=(round(float(link["x1_m"]),3),round(float(link["y1_m"]),3))
                key=tuple(sorted((a,b))); freq_by_path[key]=freq_by_path.get(key,0)+1
                endpoints.update((a,b)); degree[a]=degree.get(a,0)+1; degree[b]=degree.get(b,0)+1
                length_by_path[key]=math.hypot(a[0]-b[0],a[1]-b[1])/1000
            mult=list(freq_by_path.values()); lengths=list(length_by_path.values())
            patch_link["pairs"].append(len(links)); patch_link["paths"].append(len(freq_by_path))
            patch_link["length"].append(statistics.mean(lengths) if lengths else 0)
            patch_link["frequency"].append(statistics.mean(float(x["freq_ghz"]) for x in links) if links else 0)
            patch_link["endpoints"].append(len(endpoints)); patch_link["maxdegree"].append(max(degree.values(),default=0))
            patch_link["single_pct"].append(100*sum(x==1 for x in mult)/max(1,len(mult)))
            patch_link["double_pct"].append(100*sum(x==2 for x in mult)/max(1,len(mult)))
    def summary(vals): return [statistics.mean(vals),sample_sd(vals),min(vals),statistics.median(vals),max(vals)]
    link_labels=[("pairs","Link--frequency pairs per patch"),("paths","Unique physical links per patch"),("length","Mean physical-link length (km)"),("frequency","Mean carrier frequency (GHz)"),("endpoints","Unique endpoints per patch"),("maxdegree","Maximum endpoint degree"),("single_pct","Single-frequency links (%)"),("double_pct","Two-frequency links (%)")]
    lt=[r"\begin{table}[htbp]\centering\small\begin{tabular}{lrrrrr}",r"\toprule Measure & Mean & SD & Min & Median & Max \\",r"\midrule"]
    for key,label in link_labels: lt.append(label+" & "+" & ".join(fmt(x,2) for x in summary(patch_link[key]))+" "+chr(92)*2)
    lt += [r"\\",r"\bottomrule\end{tabular}",r"\caption{CML link-geometry summaries across all 200 patches. Link multiplicity counts distinct carrier frequencies on the same physical path; all other statistics are computed per patch before aggregation.}",r"\label{tab:link-geometry-200}",r"\end{table}"]
    (J/"tables/link_geometry_200.tex").write_text("\n".join(lt)+"\n")
    # Distance-bin ground-truth pixel counts are averaged patchwise across both seasons.
    stat_rows=[]
    for cache in (W_CACHE,S_CACHE):
        stat_rows += [r for r in cache_rows(cache,"DistanceStats_GTvsIDW") if r.get("patch_key") and r.get("distance_bin_m") is not None]
    bins=["≤125","(125,375]","(375,750]","(750,1500]","(1500,3125]","(3125,6000]","(6000,9000]",">9000"]
    grouped={}
    for r in stat_rows: grouped.setdefault((r["patch_key"],r["mask_type"],r["distance_bin_m"]),int(r.get("n_pixels",0)))
    rainy_total={p:sum(v for (pp,m,b),v in grouped.items() if pp==p and m=="rainy") for p in {k[0] for k in grouped}}
    dry_total={p:sum(v for (pp,m,b),v in grouped.items() if pp==p and m=="nonrainy") for p in {k[0] for k in grouped}}
    ct=[r"\begin{table}[!htbp]\centering\small\setlength{\tabcolsep}{3pt}\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrr@{}}",r"\toprule & \multicolumn{3}{c}{Rainy pixels} & \multicolumn{3}{c}{Non-rainy pixels} \\",r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",r"$d_3$ bin (m) & Mean count & Mean \% & SD & Mean count & Mean \% & SD \\",r"\midrule"]
    allpatches=sorted(p.stem.removeprefix("gt_") for base in (WINTER,SUMMER) for p in (base/"gt_dir").glob("gt_*.npz"))
    for b in bins:
        cells=[]
        for mask,total_map in [("rainy",rainy_total),("nonrainy",dry_total)]:
            vals=[grouped.get((p,mask,b),0) for p in allpatches]; pct=[100*v/total_map[p] if total_map.get(p,0) else 0 for p,v in zip(allpatches,vals)]
            cells.extend([fmt(statistics.mean(vals),1),fmt(statistics.mean(pct),2),fmt(sample_sd(vals),1)])
        ct.append(b.replace("≤",r"$\leq$")+" & "+" & ".join(cells)+" "+chr(92)*2)
    # Totals are reported per patch, not as a sum over heterogeneous patch areas.
    cells=[]
    for vals in [list(rainy_total.values()),list(dry_total.values())]: cells.extend([fmt(statistics.mean(vals),1),"100",fmt(sample_sd(vals),1)])
    ct += [r"\midrule Total & "+" & ".join(cells)+r" \\\\",r"\bottomrule\end{tabular*}",r"\caption{Ground-truth rainy and non-rainy pixel counts by $d_3$ bin. Counts and within-class percentages are first computed per patch and then averaged across all 200 patches.}",r"\label{tab:rainy_nonrain_counts}",r"\end{table}"]
    (J/"tables/rainy_nonrain_counts_200.tex").write_text("\n".join(ct)+"\n")
    return desc


def d3_summary_table():
    bins=["≤125","(125,375]","(375,750]","(750,1500]","(1500,3125]","(3125,6000]","(6000,9000]",">9000"]
    valid={p.stem.removeprefix("gt_") for base in (WINTER,SUMMER) for p in (base/"gt_dir").glob("gt_*.npz")}
    by={}
    for cache,mp in [(W_CACHE,W_MAP),(S_CACHE,S_MAP)]:
        for method in COMMON:
            for r in cache_rows(cache,f"DistanceStats_GTvs{mp[method]}"):
                if r.get("patch_key") in valid and r.get("distance_bin_m") in bins and int(r.get("n_pixels",0))>0:
                    by[(method,r["mask_type"],r["patch_key"],r["distance_bin_m"])]=float(r.get("median_abs",0))
    tables=[]
    for mask,title,label in [("rainy","Rainy pixels: median relative absolute error","tab:d3-rainy-summary"),("nonrainy","Non-rainy pixels: median absolute error","tab:d3-dry-summary")]:
        lines=[r"\begin{table}[htbp]\centering\scriptsize\setlength{\tabcolsep}{4pt}\resizebox{\textwidth}{!}{\begin{tabular}{lr"+"r"*len(COMMON)+"}",r"\toprule $d_3$ bin (m) & $n$ & "+" & ".join(MACRO[m] for m in COMMON)+r" \\\\",r"\midrule"]
        for b in bins:
            vals={}
            for m in COMMON:
                xx=[v for (mm,ma,patch,bb),v in by.items() if mm==m and ma==mask and bb==b]
                vals[m]=(len(xx),statistics.mean(xx) if xx else 0,sample_sd(xx))
            n=min(v[0] for v in vals.values())
            cells=[f"{fmt(vals[m][1])} $\\pm$ {fmt(vals[m][2])}" if vals[m][0] else "--" for m in COMMON]
            lines.append(f"{b.replace('≤', chr(36)+chr(92)+'leq'+chr(36))} & {n} & "+" & ".join(cells)+" "+chr(92)*2)
        lines += [r"\bottomrule\end{tabular}}",f"\\caption{{{title} summarized patchwise across all 200 benchmark patches. Each entry is mean $\\pm$ sample SD; $n$ gives the number of patches with pixels in the distance bin.}}",f"\\label{{{label}}}",r"\end{table}"]
        tables.extend(lines)
    (J/"tables/d3_solver_summary_tables.tex").write_text("\n".join(tables)+"\n")

def link_fit_table():
    rows=[]
    valid={p.stem.removeprefix("gt_") for base in (WINTER,SUMMER) for p in (base/"gt_dir").glob("gt_*.npz")}
    for cache,mp in [(W_CACHE,W_MAP),(S_CACHE,S_MAP)]:
        for m in COMMON:
            label=mp[m]
            for r in cache_rows(cache,f"LinkStats_GTvs{label}"):
                if r.get("patch_key") in valid: rows.append((m,r))
    out=[r"\begin{table}[H]\centering\small\begin{tabular}{lrrr}",r"\toprule Solver & $n$ & Attenuation MAE (dB/km) & $J_{\mathrm{atten}}$ \\",r"\midrule"]
    for m in COMMON:
        rs=[r for mm,r in rows if mm==m]; mae=[float(r["mean_abs_attn_err_per_km_all"]) for r in rs]; j=[float(r["J_atten_all"]) for r in rs]
        pm=chr(92)+"pm"; row=f"{MACRO[m]} & {len(rs)} & ${fmt(statistics.mean(mae),4)}{pm}{fmt(sample_sd(mae),4)}$ & ${fmt(statistics.mean(j),4)}{pm}{fmt(sample_sd(j),4)}$"; out.append(row+" "+chr(92)*2)
    out += [r"\bottomrule\end{tabular}",r"\caption{Patch-averaged attenuation errors across the 200-patch benchmark. Methods are included when a matching winter and summer solver output is available.}",r"\label{tab:attenuation-fit-summary}",r"\end{table}"]
    (J/"tables/attenuation_fit_200.tex").write_text("\n".join(out)+"\n")


def distance_win_table():
    bins=["≤125","(125,375]","(375,750]","(750,1500]","(1500,3125]","(3125,6000]","(6000,9000]",">9000"]
    valid={p.stem.removeprefix("gt_") for base in (WINTER,SUMMER) for p in (base/"gt_dir").glob("gt_*.npz")}
    values={"IDW":{},"Convex Solver":{}}
    for cache,mp in [(W_CACHE,W_MAP),(S_CACHE,S_MAP)]:
        for method in values:
            for r in cache_rows(cache,f"DistanceStats_GTvs{mp[method]}"):
                if r.get("patch_key") in valid and int(r.get("n_pixels",0))>0:
                    values[method][(r["patch_key"],r["mask_type"],r["distance_bin_m"])]=float(r.get("median_abs",0))
    out=[r"\begin{table}[t]\centering\begin{tabular}{lrrr}",r"\toprule $d_3$ bin (m) & Rainy pixels, Convex:IDW & Non-rainy pixels, Convex:IDW & $n$ "+chr(92)*2,r"\midrule"]
    for b in bins:
        cells=[]; counts=[]
        for mask in ("rainy","nonrainy"):
            keys=[k for k in values["IDW"] if k[1]==mask and k[2]==b and k in values["Convex Solver"]]
            dif=[values["Convex Solver"][k]-values["IDW"][k] for k in keys]
            a=sum(x<0 for x in dif); z=sum(x==0 for x in dif); c=sum(x>0 for x in dif)
            cells.append(f"{a}:{c}"+(f" ({z} ties)" if z else "")); counts.append(len(keys))
        out.append(f"{b.replace('≤', chr(36)+chr(92)+'leq'+chr(36))} & {cells[0]} & {cells[1]} & {min(counts)} "+chr(92)*2)
    out += [r"\bottomrule\end{tabular}",r"\caption{Patchwise median-error wins by $d_3$ bin across all 200 patches. Rainy pixels are compared by median relative absolute error; non-rainy pixels by median absolute error. $n$ is the number of paired patches with pixels in both strata.}",r"\label{tab:distance-bin-win-counts}",r"\end{table}"]
    (J/"tables/distance_bin_win_counts_200.tex").write_text("\n".join(out)+"\n")


def main():
    metrics=full_patch_metrics()
    (J/"images/taylor_200/benchmark_metrics.json").write_text(json.dumps(metrics,indent=2))
    update_tables(metrics)
    patch_and_link_tables()
    d3_summary_table()
    link_fit_table()
    distance_win_table()
    print("Wrote pooled 200-patch metrics and summary tables")


if __name__=="__main__": main()
