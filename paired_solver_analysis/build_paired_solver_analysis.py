#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
NOTE_DIR = ROOT / "paired_solver_analysis"
CACHE_PATH = (
    ROOT
    / "Compute-Link-Attenuations/HundredPatches/pipeline/batch_analyze_output"
    / "stats_report_cache.json"
)
LIGHT_SHRINKAGE_CACHE_PATH = CACHE_PATH
EST_INPUT_DIR = ROOT / "Compute-Link-Attenuations/HundredPatches/est_dir"

sys.path.insert(0, str(ROOT / "Compute-Link-Attenuations"))
from batch_analyze_multi import (  # noqa: E402
    load_est_payload,
    parse_bins,
)

SOLVERS = [
    ("IDW", "IDW"),
    ("ILDW", "ILDW"),
    ("OPT_NORM_ILDW_MULT_ILDW_INIT", "Nonlinear Optimizer (300 iters, normal shrinkage)"),
    (
        "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL",
        "Virtual Convex Light Shrinkage (2000 iters)",
    ),
    (
        "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL",
        "Homotopy Light Shrinkage (2000 iters)",
    ),
]

TABLE_SOLVER_NAMES = {
    "IDW": "IDW",
    "ILDW": "ILDW",
    "OPT_NORM_ILDW_MULT_ILDW_INIT": "Nonlinear Opt.",
    "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL": "VC Light Shrinkage",
    "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL": "Homotopy Light Shrinkage",
}

BASELINES = [
    ("IDW", "IDW"),
    ("ILDW", "ILDW"),
]

CANDIDATES = [
    ("OPT_NORM_ILDW_MULT_ILDW_INIT", "Nonlinear Optimizer (300 iters, normal shrinkage)"),
    (
        "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL",
        "Virtual Convex Light Shrinkage (2000 iters)",
    ),
    (
        "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL",
        "Homotopy Light Shrinkage (2000 iters)",
    ),
]

TEST_COMPARISONS = [
    (candidate_key, baseline_key, candidate_name, baseline_name)
    for candidate_key, candidate_name in CANDIDATES
    for baseline_key, baseline_name in BASELINES
]

METRICS = {
    "rmse_mmph": "RMSE",
    "bias_mmph": "Bias",
    "pearson_corr": "Pearson $r$",
}


def finite_pairs(xs: list[Any], ys: list[Any]) -> tuple[list[float], list[float]]:
    paired_x: list[float] = []
    paired_y: list[float] = []
    for x, y in zip(xs, ys):
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if math.isfinite(x) and math.isfinite(y):
                paired_x.append(float(x))
                paired_y.append(float(y))
    return paired_x, paired_y


def load_npz_first_key(path: str | Path, preferred_keys: list[str]) -> np.ndarray:
    with np.load(path) as data:
        for key in preferred_keys:
            if key in data:
                return np.asarray(data[key])
        first_key = list(data.files)[0]
        return np.asarray(data[first_key])


def compute_exact_d3_map(est: dict[str, Any], *, chunk_size: int = 2048) -> np.ndarray:
    header = est["header"]
    links = est["links"]
    h = int(header["H"])
    w = int(header["W"])
    pix = float(header["pixel_size_m"])
    if len(links) < 3:
        return np.full((h, w), np.inf, dtype=np.float64)

    x0 = np.array([float(link["x0_m"]) for link in links], dtype=np.float64)
    y0 = np.array([float(link["y0_m"]) for link in links], dtype=np.float64)
    x1 = np.array([float(link["x1_m"]) for link in links], dtype=np.float64)
    y1 = np.array([float(link["y1_m"]) for link in links], dtype=np.float64)
    dx = x1 - x0
    dy = y1 - y0
    seg_len2 = dx * dx + dy * dy

    xs = (np.arange(w, dtype=np.float64) + 0.5) * pix
    ys = (np.arange(h, dtype=np.float64) + 0.5) * pix
    grid_x, grid_y = np.meshgrid(xs, ys)
    points = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)

    out = np.empty(points.shape[0], dtype=np.float64)
    for start in range(0, points.shape[0], chunk_size):
        end = min(points.shape[0], start + chunk_size)
        px = points[start:end, 0][:, None]
        py = points[start:end, 1][:, None]
        t = ((px - x0) * dx + (py - y0) * dy) / np.where(seg_len2 == 0.0, 1.0, seg_len2)
        t = np.clip(t, 0.0, 1.0)
        proj_x = x0 + t * dx
        proj_y = y0 + t * dy
        distances = np.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        out[start:end] = np.partition(distances, 2, axis=1)[:, 2]
    return out.reshape(h, w)


def sample_sd(values: list[float]) -> float:
    return float(stdev(values)) if len(values) > 1 else float("nan")


def normal_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def t_pdf(x: float, df: int) -> float:
    return (
        math.gamma((df + 1.0) / 2.0)
        / (math.sqrt(df * math.pi) * math.gamma(df / 2.0))
        * (1.0 + x * x / df) ** (-(df + 1.0) / 2.0)
    )


def t_cdf(x: float, df: int) -> float:
    if x == 0.0:
        return 0.5
    sign = 1.0 if x > 0.0 else -1.0
    upper = abs(x)
    steps = max(600, int(upper * 300))
    if steps % 2:
        steps += 1
    h = upper / steps
    total = t_pdf(0.0, df) + t_pdf(upper, df)
    for i in range(1, steps):
        total += (4.0 if i % 2 else 2.0) * t_pdf(i * h, df)
    area = total * h / 3.0
    return 0.5 + sign * area


def t_sf(x: float, df: int) -> float:
    return max(0.0, 1.0 - t_cdf(x, df))


def t_ppf(prob: float, df: int) -> float:
    lo, hi = -12.0, 12.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < prob:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def binom_tail_ge_p(k: int, n: int) -> float:
    if n == 0:
        return float("nan")
    return min(1.0, sum(math.comb(n, i) * (0.5**n) for i in range(k, n + 1)))


def paired_t_row(
    metric_data: dict[str, Any],
    lhs_key: str,
    rhs_key: str,
    lhs_name: str,
    rhs_name: str,
    metric_key: str,
    alternative: str = "less",
) -> dict[str, Any]:
    lhs_values = metric_data[lhs_key]
    rhs_values = metric_data[rhs_key]
    if isinstance(lhs_values, dict):
        lhs_values = lhs_values[metric_key]
    if isinstance(rhs_values, dict):
        rhs_values = rhs_values[metric_key]
    lhs, rhs = finite_pairs(lhs_values, rhs_values)
    diffs = [a - b for a, b in zip(lhs, rhs)]
    n = len(diffs)
    df = n - 1
    mean_diff = float(mean(diffs))
    sd_diff = sample_sd(diffs)
    se = sd_diff / math.sqrt(n)
    t_stat = mean_diff / se
    if alternative == "less":
        p_one = t_cdf(t_stat, df)
        bound_99 = mean_diff + t_ppf(0.99, df) * se
        bound_label = r"99\% upper bound"
    elif alternative == "greater":
        p_one = t_sf(t_stat, df)
        bound_99 = mean_diff - t_ppf(0.99, df) * se
        bound_label = r"99\% lower bound"
    else:
        raise ValueError(f"unsupported alternative: {alternative}")
    return {
        "metric": METRICS[metric_key],
        "comparison": f"{lhs_name} - {rhs_name}",
        "alternative": alternative,
        "n": n,
        "mean_lhs": mean(lhs),
        "mean_rhs": mean(rhs),
        "mean_diff": mean_diff,
        "sd_diff": sd_diff,
        "se": se,
        "t": t_stat,
        "p_one": p_one,
        "alpha": 0.01,
        "decision": "reject" if p_one <= 0.01 else "do not reject",
        "reject_alpha_0_01": p_one <= 0.01,
        "reject_alpha_0_05": p_one <= 0.05,
        "bound_label": bound_label,
        "bound_99": bound_99,
    }


def fisher_z(r: float) -> float:
    eps = 1e-12
    clipped = min(max(r, -1.0 + eps), 1.0 - eps)
    return math.atanh(clipped)


def sign_test_row(
    metric_data: dict[str, list[float]],
    lhs_key: str,
    rhs_key: str,
    lhs_name: str,
    rhs_name: str,
) -> dict[str, Any]:
    lhs, rhs = finite_pairs(metric_data[lhs_key], metric_data[rhs_key])
    diffs = [a - b for a, b in zip(lhs, rhs) if a != b]
    positive = sum(1 for d in diffs if d > 0.0)
    negative = sum(1 for d in diffs if d < 0.0)
    n = positive + negative
    p_one = binom_tail_ge_p(positive, n) if n else None
    return {
        "comparison": f"{lhs_name} - {rhs_name}",
        "n_nonzero": n,
        "a_higher": positive,
        "b_higher": negative,
        "p_one": p_one,
        "reject_alpha_0_01": p_one <= 0.01 if p_one is not None else False,
        "reject_alpha_0_05": p_one <= 0.05 if p_one is not None else False,
    }


def fmt_num(value: Any) -> str:
    if value is None:
        return ""
    x = float(value)
    if math.isnan(x):
        return "NaN"
    if x == 0:
        return "0"
    if abs(x) < 1e-3 or abs(x) >= 1e4:
        return f"{x:.3e}"
    return f"{x:.4f}"


def latex_escape(text: str) -> str:
    return text.replace("&", r"\&").replace("_", r"\_")


def latex_distance_label(text: str) -> str:
    return latex_escape(text).replace("≤", r"$\leq$").replace(">", r"$>$")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def merge_gtbin_plot_data(
    data: dict[str, Any], light_data: dict[str, Any]
) -> dict[str, Any]:
    base_gtbin = data["gtbin_plot_data"]
    light_gtbin = light_data["gtbin_plot_data"]
    merged: dict[str, Any] = {
        "labels_to_plot": list(base_gtbin["labels_to_plot"]),
        "bin_count_stats": dict(base_gtbin["bin_count_stats"]),
    }
    for solver_key, _ in SOLVERS:
        source = base_gtbin if solver_key in base_gtbin["abs_mean"] else light_gtbin
        merged[solver_key] = {
            "abs_mean": list(source["abs_mean"][solver_key]),
            "abs_std": list(source["abs_std"][solver_key]),
        }
    return merged


def cache_jobs_by_solver(*cache_data_items: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    jobs: dict[str, dict[str, dict[str, Any]]] = {}
    for cache_data in cache_data_items:
        for job in cache_data.get("patch_plot_jobs", []):
            solver = str(job["solver_label"])
            patch_key = str(job["patch_key"])
            jobs.setdefault(solver, {})[patch_key] = job
    return jobs


def compute_binned_patch_metrics(
    data: dict[str, Any],
    light_data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs_by_solver = cache_jobs_by_solver(data, light_data)
    intervals = parse_bins([125, 375, 750, 1500, 3125, 6000, 9000])
    d3_maps: dict[str, np.ndarray] = {}
    d3_cache_dir = NOTE_DIR / "d3_distance_cache"
    d3_cache_dir.mkdir(exist_ok=True)

    def d3_map_for_patch(patch_key: str, shape: tuple[int, int]) -> np.ndarray:
        if patch_key not in d3_maps:
            cache_path = d3_cache_dir / f"{patch_key}.npy"
            if cache_path.exists():
                d3_maps[patch_key] = np.load(cache_path)
            else:
                print(f"computing d3 distance map for {patch_key}")
                est = load_est_payload(EST_INPUT_DIR / f"est_input_{patch_key}.json")
                d3_maps[patch_key] = compute_exact_d3_map(est)
                np.save(cache_path, d3_maps[patch_key])
        d3 = d3_maps[patch_key]
        if d3.shape != shape:
            raise ValueError(f"d3 map shape {d3.shape} != data shape {shape} for {patch_key}")
        return d3

    def distance_mask(d3: np.ndarray, lo: float | None, hi: float | None) -> np.ndarray:
        if lo is None:
            return d3 <= float(hi)
        if hi is None:
            return d3 > float(lo)
        return (d3 > float(lo)) & (d3 <= float(hi))

    patch_rows: list[dict[str, Any]] = []
    for solver_key, solver_name in SOLVERS:
        solver_jobs = jobs_by_solver[solver_key]
        for patch_key in sorted(solver_jobs):
            job = solver_jobs[patch_key]
            gt = load_npz_first_key(job["gt_path"], list(job.get("gt_key_pref", ["R_gt", "rain", "gt"]))).astype(np.float64)
            pred = load_npz_first_key(job["sol_path"], list(job.get("sol_key_pref", ["R_hat"]))).astype(np.float64)
            d3 = d3_map_for_patch(patch_key, gt.shape)
            valid = np.isfinite(gt) & np.isfinite(pred)
            for lo, hi, bin_label in intervals:
                mask = valid & np.isfinite(d3) & distance_mask(d3, lo, hi)
                n_pixels = int(np.sum(mask))
                if n_pixels == 0:
                    continue
                gt_vals = gt[mask].ravel()
                pred_vals = pred[mask].ravel()
                diff = pred_vals - gt_vals
                rmse = float(np.sqrt(np.mean(diff * diff)))
                bias = float(np.mean(diff))
                rho = None
                if n_pixels >= 2 and float(np.std(gt_vals)) > 0.0 and float(np.std(pred_vals)) > 0.0:
                    rho = float(np.corrcoef(gt_vals, pred_vals)[0, 1])
                patch_rows.append(
                    dict(
                        patch_key=patch_key,
                        solver=solver_key,
                        solver_display=solver_name,
                        distance_bin_m=bin_label,
                        n_pixels=n_pixels,
                        rmse_mmph=rmse,
                        bias_mmph=bias,
                        pearson_corr=rho,
                    )
                )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in patch_rows:
        grouped.setdefault((str(row["distance_bin_m"]), str(row["solver"])), []).append(row)

    summary_rows: list[dict[str, Any]] = []
    bin_order = [label for _, _, label in intervals]
    solver_order = [key for key, _ in SOLVERS]
    for bin_label in bin_order:
        for solver_key, solver_name in SOLVERS:
            rows = grouped.get((bin_label, solver_key), [])
            out: dict[str, Any] = dict(distance_bin_m=bin_label, solver=solver_key, solver_display=solver_name)
            out["n_patch_rmse"] = len([r for r in rows if r["rmse_mmph"] is not None])
            out["n_patch_bias"] = len([r for r in rows if r["bias_mmph"] is not None])
            out["n_patch_pearson"] = len([r for r in rows if r["pearson_corr"] is not None])
            out["mean_pixel_count"] = mean([float(r["n_pixels"]) for r in rows]) if rows else None
            for metric in ["rmse_mmph", "bias_mmph", "pearson_corr"]:
                vals = [float(r[metric]) for r in rows if r[metric] is not None]
                out[f"{metric}_mean"] = mean(vals) if vals else None
                out[f"{metric}_sd"] = sample_sd(vals) if len(vals) > 1 else None
            summary_rows.append(out)
    summary_rows.sort(key=lambda r: (bin_order.index(str(r["distance_bin_m"])), solver_order.index(str(r["solver"]))))
    return patch_rows, summary_rows


def metric_cell(row: dict[str, Any], metric: str) -> str:
    mean_value = row.get(f"{metric}_mean")
    sd_value = row.get(f"{metric}_sd")
    if mean_value is None:
        return ""
    return rf"{fmt_num(mean_value)} $\pm$ {fmt_num(sd_value)}"


def table_binned_patch_metrics(summary_rows: list[dict[str, Any]]) -> str:
    rows_by_bin_solver = {(str(r["distance_bin_m"]), str(r["solver"])): r for r in summary_rows}
    bin_labels: list[str] = []
    for row in summary_rows:
        label = str(row["distance_bin_m"])
        if label not in bin_labels:
            bin_labels.append(label)
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\tiny",
        r"\setlength{\tabcolsep}{2.2pt}",
        r"\resizebox{\textwidth}{!}{%",
        rf"\begin{{tabular}}{{lr{'ccc' * len(SOLVERS)}}}",
        r"\toprule",
        r" &  & "
        + " & ".join(
            rf"\multicolumn{{3}}{{c}}{{{latex_escape(TABLE_SOLVER_NAMES.get(key, name))}}}"
            for key, name in SOLVERS
        )
        + r" \\",
        "".join(
            rf"\cmidrule(lr){{{3 + 3 * i}-{5 + 3 * i}}}"
            for i in range(len(SOLVERS))
        ),
        r"$d_3$ bin (m) & mean pixels & "
        + " & ".join("RMSE & Bias & Pearson $r$" for _ in SOLVERS)
        + r" \\",
        r"\midrule",
    ]
    for bin_label in bin_labels:
        first_row = next((rows_by_bin_solver.get((bin_label, solver_key)) for solver_key, _ in SOLVERS), None)
        mean_pixels = first_row.get("mean_pixel_count") if first_row else None
        lines.append(
            " & ".join(
                [rf"\mbox{{{latex_distance_label(bin_label)}}}", fmt_num(mean_pixels)]
                + [
                    item
                    for solver_key, _ in SOLVERS
                    for item in [
                        metric_cell(rows_by_bin_solver[(bin_label, solver_key)], "rmse_mmph"),
                        metric_cell(rows_by_bin_solver[(bin_label, solver_key)], "bias_mmph"),
                        metric_cell(rows_by_bin_solver[(bin_label, solver_key)], "pearson_corr"),
                    ]
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\caption{Distance-to-3rd-closest-link bin summaries. Each metric cell reports mean $\pm$ sample SD across patch-level bin metrics. RMSE, Bias, and Pearson $r$ are recomputed from the underlying pixel values inside each $d_3$ distance bin for each patch and solver.}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def table_paired_t(rows: list[dict[str, Any]], caption: str) -> str:
    bound_label = str(rows[0]["bound_label"]) if rows else "99% bound"
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrrrrrrrrrrrl}",
        r"\toprule",
        rf"Comparison & n & mean A & mean B & mean diff & SD diff & SE & $t$ & one-sided $p$ & {bound_label} & $\alpha$ & decision \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(row["comparison"]),
                    str(row["n"]),
                    fmt_num(row["mean_lhs"]),
                    fmt_num(row["mean_rhs"]),
                    fmt_num(row["mean_diff"]),
                    fmt_num(row["sd_diff"]),
                    fmt_num(row["se"]),
                    fmt_num(row["t"]),
                    fmt_num(row["p_one"]),
                    fmt_num(row["bound_99"]),
                    fmt_num(row["alpha"]),
                    str(row["decision"]),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            rf"\caption{{{caption}}}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def table_sign(rows: list[dict[str, Any]]) -> str:
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\scriptsize",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Comparison & nonzero n & A higher & B higher & one-sided $p$ \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            " & ".join(
                [
                    latex_escape(row["comparison"]),
                    str(row["n_nonzero"]),
                    str(row["a_higher"]),
                    str(row["b_higher"]),
                    fmt_num(row["p_one"]),
                ]
            )
            + r" \\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\caption{One-sided sign test for patchwise Pearson correlation differences. The alternative is that solver A has higher Pearson correlation than solver B on more than half of the non-tied patches.}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    NOTE_DIR.mkdir(exist_ok=True)
    with CACHE_PATH.open() as f:
        data = json.load(f)
    metrics = data["patch_map_metrics_plot_data"]
    with LIGHT_SHRINKAGE_CACHE_PATH.open() as f:
        light_data = json.load(f)
    light_metrics = light_data["patch_map_metrics_plot_data"]
    for solver_key in [
        "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL",
        "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL",
    ]:
        metrics[solver_key] = light_metrics[solver_key]
    _gtbin_by_solver = merge_gtbin_plot_data(data, light_data)
    binned_patch_rows, binned_summary_rows = compute_binned_patch_metrics(data, light_data)

    rmse_rows = [
        paired_t_row(metrics, a_key, b_key, a_name, b_name, "rmse_mmph", alternative="less")
        for a_key, b_key, a_name, b_name in TEST_COMPARISONS
    ]
    bias_rows = [
        paired_t_row(metrics, a_key, b_key, a_name, b_name, "bias_mmph", alternative="less")
        for a_key, b_key, a_name, b_name in TEST_COMPARISONS
    ]

    corr_z_metrics: dict[str, list[float]] = {
        key: [fisher_z(float(r)) for r in metrics[key]["pearson_corr"]] for key, _ in SOLVERS
    }
    corr_z_rows = [
        paired_t_row(corr_z_metrics, a_key, b_key, a_name, b_name, "pearson_corr", alternative="greater")
        for a_key, b_key, a_name, b_name in TEST_COMPARISONS
    ]
    sign_rows = [
        sign_test_row(
            {key: metrics[key]["pearson_corr"] for key, _ in SOLVERS},
            a_key,
            b_key,
            a_name,
            b_name,
        )
        for a_key, b_key, a_name, b_name in TEST_COMPARISONS
    ]

    write_csv(NOTE_DIR / "paired_t_rmse.csv", rmse_rows)
    write_csv(NOTE_DIR / "paired_t_bias.csv", bias_rows)
    write_csv(NOTE_DIR / "paired_fisher_z_correlation.csv", corr_z_rows)
    write_csv(NOTE_DIR / "sign_test_correlation.csv", sign_rows)
    write_csv(NOTE_DIR / "binned_patch_metrics_by_patch.csv", binned_patch_rows)
    write_csv(NOTE_DIR / "binned_patch_metrics_summary.csv", binned_summary_rows)

    tex = rf"""\documentclass[11pt]{{article}}

\usepackage[margin=0.85in]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage{{lmodern}}
\usepackage{{booktabs}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{graphicx}}
\usepackage{{float}}
\usepackage{{hyperref}}

\title{{Paired Patchwise Solver Comparisons}}
\author{{}}
\date{{}}

\begin{{document}}
\maketitle

\section*{{What is being compared}}
Each solver is evaluated on the same 100 patches, so the inferential unit is the patchwise paired difference. For metric $M$ and solvers $A$ and $B$, the tested quantity is
\[
d_P = M_A(P) - M_B(P).
\]
The descriptive mean/SD table is useful for orientation, but significance depends on the variance of these paired differences, not on the separate solver standard deviations. The inferential tables below compare the optimization solvers against the two interpolation baselines, IDW and ILDW.

The one-sided $t$ tests for RMSE and signed Bias use
\[
H_0:\mathbb{{E}}[d]\ge 0,\qquad H_1:\mathbb{{E}}[d]<0.
\]
The paired-test tables use $\alpha=0.01$. The one-sided $p$-value is the probability, under the boundary null $\mathbb{{E}}[d]=0$, of observing a test statistic at least as favorable to solver $A$ as the one observed. The p-value rule is to reject when the one-sided $p$-value is at most $0.01$.

The 99\% one-sided bound is a confidence-bound version of the same test. For RMSE and signed Bias, the table reports an upper bound for the true mean paired difference $\mathbb{{E}}[d]$; if that upper bound is below zero, then the whole 99\% one-sided confidence region lies in the ``solver $A$ is smaller'' direction. For Pearson correlation, the table reports a lower bound; if that lower bound is above zero, then the whole 99\% one-sided confidence region lies in the ``solver $A$ has higher correlation'' direction. These bound rules and the $p \le 0.01$ rule give the same decisions because they are two equivalent forms of the same one-sided $t$ test at the same 1\% significance level.

{table_binned_patch_metrics(binned_summary_rows)}

The sample size $n$ can differ between tables, and sometimes even for the same distance bin, because each table counts only patch/bin entries where that metric is defined. A bin can contain a different number of valid pixels from patch to patch; Pearson correlation additionally requires at least two pixels with nonzero variation in both the ground truth and solver field. Therefore an RMSE or Bias entry can exist for a patch/bin where the corresponding Pearson entry is omitted.

\section*{{Paired $t$ analysis for RMSE}}
For RMSE, negative differences mean that solver $A$ has lower RMSE than solver $B$ on average. This is the natural one-sided direction for testing whether $A$ improves on $B$.

{table_paired_t(rmse_rows, "Paired $t$ comparisons for patchwise RMSE differences.")}

\section*{{Paired $t$ analysis for Bias}}
For Bias, the difference is the signed bias difference $Bias_A-Bias_B$. The one-sided lower-tail test asks whether solver $A$ has a smaller signed bias than solver $B$. This is not the same as testing which solver is closer to zero bias; for that question, use paired differences of absolute bias instead.

{table_paired_t(bias_rows, "Paired $t$ comparisons for patchwise signed-bias differences.")}

\section*{{Paired Fisher-$z$ analysis for correlation}}
For Pearson correlation, first apply the Fisher transform
\[
z = \frac{{1}}{{2}}\log\frac{{1+r}}{{1-r}},
\]
then compare the paired $z$ values across patches. For correlation, larger is better, so the Fisher-$z$ table uses the one-sided direction $H_0:\mathbb{{E}}[d]\le 0$ against $H_1:\mathbb{{E}}[d]>0$.

{table_paired_t(corr_z_rows, "Paired $t$ comparisons for Fisher-transformed patchwise Pearson correlations. Positive differences mean solver $A$ has higher transformed correlation than solver $B$.")}

{table_sign(sign_rows)}

\end{{document}}
"""
    (NOTE_DIR / "paired_solver_analysis.tex").write_text(tex)
    print(f"wrote {NOTE_DIR / 'paired_solver_analysis.tex'}")


if __name__ == "__main__":
    main()
