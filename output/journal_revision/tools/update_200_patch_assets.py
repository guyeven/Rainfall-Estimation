#!/usr/bin/env python3
"""Regenerate the 200-patch map and Taylor diagrams for Journal.tex.

Uses only the benchmark metadata and saved NPZ outputs. The basemap is the
existing journal map with its winter outlines recolored blue; summer footprints
are projected and drawn in red over it.
"""
from __future__ import annotations

import base64
import sys
import json
import math
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
JOURNAL = ROOT / "output/journal_revision"
ASSETS = JOURNAL / "images"
R = 6378137.0
BLUE = "#2563eb"
RED = "#dc2626"


def records(path: Path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def mercator(lon: float, lat: float):
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def patch_bounds(row: dict):
    lon, lat = float(row["center_lon"]), float(row["center_lat"])
    w, h = float(row["width_km"]), float(row["height_km"])
    half_lat = (h / 2) / 111.32
    half_lon = (w / 2) / (111.32 * max(1e-6, math.cos(math.radians(lat))))
    ll = mercator(lon-half_lon, lat-half_lat)
    ur = mercator(lon+half_lon, lat+half_lat)
    return ll[0], ll[1], ur[0], ur[1]


def load_season_metadata():
    winter_path = ROOT / "Patch-Generator/Benchmark-Patches/benchmark-500-files-758-patches.local.jan2023.jsonl"
    winter_meta = {str(r["id"]): r for r in records(winter_path)}
    winter_dir = COMPUTE / "HundredPatches/patch_overview_generation/patch_jsonl_files"
    winter_ids = [p.stem.removeprefix("patch_") for p in sorted(winter_dir.glob("patch_*.jsonl"))]
    winter = [winter_meta[x] for x in winter_ids]
    summer = records(COMPUTE / "June2023HundredPatches/benchmark-patches.review-order.jsonl")
    if len(winter) != 100 or len(summer) != 100:
        raise RuntimeError(f"Expected 100 patches per season, got {len(winter)} winter and {len(summer)} summer")
    return winter, summer


def render_map(winter, summer):
    out = ASSETS / "patch_overview/hundredpatches_europe_overview_basemap.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    base = out.with_name(".original-europe-basemap.png")
    relative = out.relative_to(ROOT).as_posix()
    original = subprocess.check_output(["git", "show", f"HEAD:{relative}"])
    base.write_bytes(original)
    blue_base = out.with_name(".winter-blue-basemap.png")
    subprocess.run(["magick", str(base), "-fuzz", "28%", "-fill", BLUE, "-opaque", "#c71f17", str(blue_base)], check=True)
    # The map generator uses padded projected bounds of the winter roster.
    bounds = [patch_bounds(r) for r in winter]
    xmin, ymin = min(b[0] for b in bounds), min(b[1] for b in bounds)
    xmax, ymax = max(b[2] for b in bounds), max(b[3] for b in bounds)
    xpad, ypad = .08 * (xmax-xmin), .10 * (ymax-ymin)
    xmin, xmax, ymin, ymax = xmin-xpad, xmax+xpad, ymin-ypad, ymax+ypad
    # Determine dimensions from the basemap file; the original plotted map fills
    # the canvas, so these are the same map-to-pixel limits used for both seasons.
    probe = subprocess.check_output(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(base)], text=True)
    vals = [int(line.split(":")[-1]) for line in probe.splitlines() if "pixel" in line]
    width, height = vals
    def xy(x, y):
        return (x-xmin) / (xmax-xmin) * width, (ymax-y) / (ymax-ymin) * height
    draw = []
    for row in summer:
        x0,y0,x1,y1 = patch_bounds(row)
        px0,py1 = xy(x0,y0); px1,py0 = xy(x1,y1)
        draw.extend(["-stroke", RED, "-strokewidth", "3", "-fill", "none", "-draw", f"rectangle {px0:.2f},{py0:.2f} {px1:.2f},{py1:.2f}"])
    # Draw a compact key with explicit raster drawing commands to keep outlines
    # transparent when rendered by ImageMagick's SVG backend.
    lx,ly=width-310,28
    draw.extend(["-stroke", "#d1cbc2", "-strokewidth", "1", "-fill", "white", "-draw", f"roundrectangle {lx},{ly} {width-18},{ly+94} 9,9"])
    draw.extend(["-stroke", RED, "-strokewidth", "4", "-draw", f"line {lx+20},{ly+29} {lx+56},{ly+29}"])
    draw.extend(["-stroke", BLUE, "-strokewidth", "4", "-draw", f"line {lx+20},{ly+67} {lx+56},{ly+67}"])
    draw.extend(["-stroke", "none", "-fill", "#222222", "-font", "/System/Library/Fonts/Supplemental/Arial.ttf", "-pointsize", "17", "-draw", f"text {lx+68},{ly+35} 'Summer (June 2023)' text {lx+68},{ly+73} 'Winter (January 2023)'"])
    subprocess.run(["magick", str(blue_base), *draw, str(out)], check=True)
    base.unlink(missing_ok=True); blue_base.unlink(missing_ok=True)
    print(out)


def render_geometry(winter, summer):
    out=ASSETS/"patch_overview/patch_dimensions_scatter.png"
    out.parent.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":11,
                         "axes.spines.top":False, "axes.spines.right":False,
                         "axes.labelcolor":"#222222", "xtick.color":"#333333",
                         "ytick.color":"#333333"})
    fig,ax=plt.subplots(figsize=(8.2,7.0))
    ax.scatter([float(r["width_km"]) for r in winter],
               [float(r["height_km"]) for r in winter],
               s=26,c=BLUE,alpha=.62,edgecolors="white",linewidths=.3,label="Winter (n=100)",zorder=3)
    ax.scatter([float(r["width_km"]) for r in summer],
               [float(r["height_km"]) for r in summer],
               s=26,c=RED,alpha=.62,edgecolors="white",linewidths=.3,label="Summer (n=100)",zorder=3)
    ax.plot([50,95],[50,95],color="#929292",linestyle="--",linewidth=1.35,zorder=1)
    ax.set(xlim=(48,96),ylim=(48,96),xlabel="Width (km)",ylabel="Height (km)")
    ax.set_xlabel("Width (km)",fontsize=13)
    ax.set_ylabel("Height (km)",fontsize=13)
    ax.set_xticks(np.arange(50,96,5)); ax.set_yticks(np.arange(50,96,5))
    ax.set_aspect("equal",adjustable="box")
    ax.grid(True,linestyle=":",linewidth=.75,color="#c8c8c8",alpha=.8,zorder=0)
    ax.tick_params(labelsize=10)
    fig.suptitle("Scatter plot of patch dimensions",fontsize=17,y=.98)
    fig.legend(*ax.get_legend_handles_labels(),loc="upper center",bbox_to_anchor=(.5,.92),
               frameon=False,ncol=2,handletextpad=.5,columnspacing=1.8,fontsize=10)
    fig.subplots_adjust(left=.14,right=.97,bottom=.12,top=.84)
    fig.savefig(out,dpi=220,bbox_inches="tight",facecolor="white")
    fig.savefig(out.with_suffix(".svg"),bbox_inches="tight",facecolor="white")
    plt.close(fig)
    sizes=[]
    for base in (COMPUTE/"HundredPatches",COMPUTE/"June2023HundredPatches"):
        for p in (base/"gt_dir").glob("gt_*.npz"):
            with np.load(p) as z: sizes.append(int(np.asarray(z["R_gt"]).size))
    stats={"n":len(sizes),"mean_pixels":float(np.mean(sizes)),"sd_pixels":float(np.std(sizes,ddof=1)),"min_pixels":min(sizes),"max_pixels":max(sizes)}
    (out.parent/"patch_dimensions_stats_200.json").write_text(json.dumps(stats,indent=2))
    print(out)


METHODS = {
    "IDW": ("sol_dir_idw", "sol_dir_idw"),
    "ILDW": ("sol_dir_ildw", "sol_dir_ildw"),
    "Solver(ILDW)": ("sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long", "sol_dir_solver_ildw_timing"),
    "Convex Solver": ("sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal", "sol_dir_convex_light_shrinkage"),
    "Homotopy Solver": ("sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal", "sol_dir_homotopy_light_shrinkage"),
    "Solver(GT)": ("sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal", "sol_dir_solver_gt_light_shrinkage"),
}


def moments(gt, pred):
    g = np.asarray(gt, dtype=np.float64).ravel()
    p = np.asarray(pred, dtype=np.float64).ravel()
    if g.size != p.size or not g.size:
        raise ValueError("GT and prediction arrays do not match")
    sg, sp = float(np.std(g)), float(np.std(p))
    corr = float(np.corrcoef(g, p)[0, 1]) if sg and sp else 0.0
    diff = p-g
    return sp / sg if sg else 0.0, corr, float(np.sqrt(np.mean(diff*diff))), float(np.mean(diff))


def npz_array(path: Path, key: str):
    with np.load(path) as f:
        return np.asarray(f[key])


SUMMARY_COLORS = ["#667085", "#56A8C7", "#23835C", "#2563B0", "#D87819", "#A13D82"]
METHOD_LABELS = ["IDW", "ILDW", "Solver(ILDW)", "Convex Solver", "Homotopy Solver", "Solver(GT)"]


def style_taylor_axes(ax, max_sd):
    ax.set_thetamin(0)
    ax.set_thetamax(90)
    ax.set_ylim(0, max_sd)
    correlations = np.array([0, .2, .4, .6, .8, .9, .95, .99, 1])
    ax.set_thetagrids(np.degrees(np.arccos(correlations)), [f"{r:g}" for r in correlations], fontsize=8)
    ax.set_rgrids(np.arange(.25, max_sd + 1e-8, .25), angle=0, fontsize=7)
    ax.grid(color="#E1E6EC", lw=.75)
    ax.spines["polar"].set_color("#A7B1BE")
    theta, radius = np.meshgrid(np.linspace(0, np.pi/2, 320), np.linspace(0, max_sd, 320))
    centered_rmse = np.sqrt(np.maximum(0, radius**2 + 1 - 2*radius*np.cos(theta)))
    levels = [x for x in (.25, .5, .75, 1, 1.25) if x <= max_sd + 1]
    cs = ax.contour(theta, radius, centered_rmse, levels=levels, colors="#79A38C", linestyles="--", linewidths=.7)
    ax.clabel(cs, inline=True, fontsize=6.5, fmt="%g")
    ax.plot(np.linspace(0, np.pi/2, 200), np.ones(200), color="#9AA7B8", lw=1)
    ax.scatter([0], [1], marker="*", c="#172033", s=95, zorder=12, clip_on=False)


def save_taylor_figure(fig, path):
    fig.savefig(path.with_suffix(".png"), dpi=220, facecolor="white", bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), facecolor="white", bbox_inches="tight")
    plt.close(fig)


def render_taylor(winter, summer):
    root = ASSETS / "taylor_200"
    root.mkdir(parents=True, exist_ok=True)
    all_points={}; aggregate={}; all_metrics={}
    season_dirs=[COMPUTE/"HundredPatches", COMPUTE/"June2023HundredPatches"]
    patch_lists=[winter,summer]
    for idx,(label,solvers) in enumerate(METHODS.items()):
        by_season={"winter":[],"summer":[]}; metrics_by_season={"winter":[],"summer":[]}
        for season_index,season_name in enumerate(["winter","summer"]):
            gt_dir=season_dirs[season_index]/"gt_dir"
            solution_dir=season_dirs[season_index]/"pipeline/solutions"/solvers[season_index]
            for gt_path in sorted(gt_dir.glob("gt_*.npz")):
                patch=gt_path.stem.removeprefix("gt_")
                sol_path=solution_dir/f"est_input_{patch}_solution.npz"
                if not sol_path.exists(): raise FileNotFoundError(sol_path)
                gt=npz_array(gt_path,"R_gt"); pred=npz_array(sol_path,"R_hat")
                sd,corr,rmse,bias=moments(gt,pred)
                by_season[season_name].append((sd,corr))
                metrics_by_season[season_name].append({"patch":patch,"rmse":rmse,"bias":bias,"pearson":corr})
        if any(len(v)!=100 for v in by_season.values()): raise RuntimeError(f"Expected 100 points per season for {label}")
        all_points[label]=by_season
        all_metrics[label]=metrics_by_season
        rows=by_season["winter"]+by_season["summer"]
        sd=math.sqrt(sum(x*x for x,_ in rows)/len(rows))
        corr=sum(s*r for s,r in rows)/(sd*len(rows)) if sd else 0.0
        aggregate[label]=(sd,corr,SUMMARY_COLORS[idx])
    max_observed_sd=max(sd for methods in all_points.values() for season in methods.values() for sd,_ in season)
    max_sd=max(1.25, math.ceil(max_observed_sd*4)/4)
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":9,
                         "text.color":"#253047", "axes.labelcolor":"#253047",
                         "xtick.color":"#4B5563", "ytick.color":"#4B5563"})
    fig, axes=plt.subplots(2,3,figsize=(13.8,10.7),subplot_kw={"projection":"polar"})
    fig.subplots_adjust(left=.045,right=.975,bottom=.12,top=.82,wspace=.27,hspace=.38)
    fig.text(.045,.982,"Taylor diagrams across the 200-patch benchmark",fontsize=19,weight="bold")
    fig.text(.045,.947,"One point per patch • shared normalized standard-deviation scale",fontsize=10.5,color="#667085")
    for ax,label in zip(axes.flat,METHOD_LABELS):
        style_taylor_axes(ax,max_sd)
        for season,color in (("winter",BLUE),("summer",RED)):
            points=all_points[label][season]
            ax.scatter([math.acos(max(-1,min(1,c))) for _,c in points], [s for s,_ in points],
                       s=18,c=color,alpha=.62,edgecolors="white",linewidths=.35,zorder=5)
        ax.set_title(label,fontsize=11.5,weight="bold",pad=18)
    legend=[Line2D([],[],marker="o",color="none",markerfacecolor=BLUE,markeredgecolor="white",markersize=7,label="Winter (n=100)"),
            Line2D([],[],marker="o",color="none",markerfacecolor=RED,markeredgecolor="white",markersize=7,label="Summer (n=100)"),
            Line2D([],[],marker="*",color="#172033",linestyle="None",markersize=10,label="Ground truth")]
    fig.legend(handles=legend,loc="upper left",bbox_to_anchor=(.045,.918),ncol=3,frameon=False,columnspacing=2)
    fig.text(.045,.065,"Angle shows correlation; radius is reconstructed SD / ground-truth SD. Green dashed contours show centered RMSE.",fontsize=9)
    fig.text(.045,.038,"Each dot is one patch; all six panels use the same radial scale.",fontsize=9,color="#667085")
    save_taylor_figure(fig,root/"seasonal_clouds")
    for label in METHOD_LABELS:
        fig,ax=plt.subplots(figsize=(7.2,6.4),subplot_kw={"projection":"polar"})
        fig.subplots_adjust(left=.06,right=.94,bottom=.12,top=.88)
        style_taylor_axes(ax,max_sd)
        for season,color in (("winter",BLUE),("summer",RED)):
            points=all_points[label][season]
            ax.scatter([math.acos(max(-1,min(1,c))) for _,c in points], [s for s,_ in points],
                       s=24,c=color,alpha=.65,edgecolors="white",linewidths=.4,zorder=5)
        ax.set_title(label,fontsize=15,weight="bold",pad=22)
        ax.legend(handles=legend[:2],loc="upper center",bbox_to_anchor=(.5,1.17),ncol=2,frameon=False)
        stem=label.lower().replace(" ","_").replace("(","").replace(")","")
        save_taylor_figure(fig,root/stem)
    fig,ax=plt.subplots(figsize=(9.2,7.4),subplot_kw={"projection":"polar"})
    fig.subplots_adjust(left=.05,right=.80,bottom=.11,top=.86)
    style_taylor_axes(ax,max_sd)
    summary_handles=[]
    for label,(sd,corr,color) in aggregate.items():
        ax.scatter([math.acos(max(-1,min(1,corr)))],[sd],s=78,c=color,edgecolors="white",linewidths=.9,zorder=8)
        summary_handles.append(Line2D([],[],marker="o",color="none",markerfacecolor=color,markeredgecolor="white",markersize=8,label=label))
    ax.set_title("All 200 patches",fontsize=15,weight="bold",pad=22)
    ax.legend(handles=summary_handles,loc="center left",bbox_to_anchor=(1.05,.5),frameon=False,labelspacing=1.2)
    save_taylor_figure(fig,root/"combined_normalized")
    (root/"taylor_metrics.json").write_text(json.dumps({k:{s:[list(x) for x in v[s]] for s in v} for k,v in all_points.items()},indent=2),encoding="utf-8")
    (root/"benchmark_metrics.json").write_text(json.dumps(all_metrics,indent=2),encoding="utf-8")
    print(root)


def main():
    winter,summer=load_season_metadata()
    mode=sys.argv[1] if len(sys.argv)>1 else "all"
    if mode in ("all","map"): render_map(winter,summer)
    if mode in ("all","geometry"): render_geometry(winter,summer)
    if mode in ("all","taylor"): render_taylor(winter,summer)


if __name__ == "__main__":
    main()
