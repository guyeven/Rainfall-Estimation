#!/usr/bin/env python3
"""Build 200-patch Tables 6 and 7 with patchwise normalized error metrics."""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
JOURNAL = ROOT / "output/journal_revision"
if str(COMPUTE) not in sys.path:
    sys.path.insert(0, str(COMPUTE))

from batch_analyze_multi import (  # noqa: E402
    assign_bin_labels,
    load_est_payload,
    point_to_segment_dist,
)
from scipy.spatial import cKDTree  # noqa: E402

WINTER = COMPUTE / "HundredPatches"
SUMMER = COMPUTE / "June2023HundredPatches"
METHODS = ["IDW", "ILDW", "Solver(ILDW)", "Convex Solver", "Homotopy Solver", "Solver(GT)"]
MACRO = {
    "IDW": r"\IDW",
    "ILDW": r"\ILDW",
    "Solver(ILDW)": r"\solverILDW",
    "Convex Solver": r"\ConvexSolver",
    "Homotopy Solver": r"\Homotopy",
    "Solver(GT)": r"\solverGT",
}
SOLUTION_DIRS = {
    "winter": {
        "IDW": "sol_dir_idw",
        "ILDW": "sol_dir_ildw",
        "Solver(ILDW)": "sol_dir_opt_norm_ildw_mult_ildw_init_light_jtotal_long",
        "Convex Solver": "sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal",
        "Homotopy Solver": "sol_dir_opt_norm_virtual_homotopy_const_init_long_light_jtotal",
        "Solver(GT)": "sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal",
    },
    "summer": {
        "IDW": "sol_dir_idw",
        "ILDW": "sol_dir_ildw",
        "Solver(ILDW)": "sol_dir_solver_ildw_timing",
        "Convex Solver": "sol_dir_convex_light_shrinkage",
        "Homotopy Solver": "sol_dir_homotopy_light_shrinkage",
        "Solver(GT)": "sol_dir_solver_gt_light_shrinkage",
    },
}
BIN_EDGES = [125, 375, 750, 1500, 3125, 6000, 9000]
BINS = ["≤125", "(125,375]", "(375,750]", "(750,1500]", "(1500,3125]", "(3125,6000]", "(6000,9000]", ">9000"]
BIN_TUPLES = [(None, 125, "≤125")] + [
    (BIN_EDGES[i], BIN_EDGES[i + 1], f"({BIN_EDGES[i]},{BIN_EDGES[i + 1]}]")
    for i in range(len(BIN_EDGES) - 1)
] + [(BIN_EDGES[-1], None, f">{BIN_EDGES[-1]}")]
# Preserve the original Table 7 Pearson summaries for the sparse >9000 m tail
# bin so this update only changes the requested normalized metrics.
ORIGINAL_TAIL_PEARSON = {
    "IDW": (0.320, 0.547),
    "ILDW": (0.292, 0.567),
    "Solver(ILDW)": (0.284, 0.568),
    "Convex Solver": (0.378, 0.590),
    "Homotopy Solver": (0.378, 0.592),
    "Solver(GT)": (0.802, 0.356),
}


def macro_for_table(name: str) -> str:
    return MACRO[name]


def sample_sd(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def fmt(value: float, digits: int = 2) -> str:
    if abs(value) < 0.5 * 10 ** (-digits):
        value = 0.0
    return f"{value:.{digits}f}"


def mean_pm_sd(values: list[float], digits: int = 2) -> str:
    return f"${fmt(statistics.mean(values), digits)}\\pm {fmt(sample_sd(values), digits)}$"


def fast_sampled_d3_map(est: dict) -> np.ndarray:
    """Vectorized equivalent of the analyzer's sampled-point d3 computation."""
    header, links = est["header"], est["links"]
    h, w = int(header["H"]), int(header["W"])
    pixel_size = float(header["pixel_size_m"])
    if len(links) < 3:
        return np.full((h, w), np.inf, dtype=np.float64)
    x0 = np.asarray([float(link["x0_m"]) for link in links], dtype=np.float64)
    y0 = np.asarray([float(link["y0_m"]) for link in links], dtype=np.float64)
    x1 = np.asarray([float(link["x1_m"]) for link in links], dtype=np.float64)
    y1 = np.asarray([float(link["y1_m"]) for link in links], dtype=np.float64)
    dx, dy = x1 - x0, y1 - y0
    lengths = np.sqrt(dx * dx + dy * dy)
    samples, sample_link_ids = [], []
    for idx, length in enumerate(lengths):
        n = min(max(2, int(np.ceil(length / 250.0)) + 1), 200)
        t = np.linspace(0.0, 1.0, n, dtype=np.float64)
        samples.append(np.column_stack((x0[idx] + t * dx[idx], y0[idx] + t * dy[idx])))
        sample_link_ids.append(np.full(n, idx, dtype=np.int32))
    sample_xy = np.concatenate(samples)
    sample_to_link = np.concatenate(sample_link_ids)
    tree = cKDTree(sample_xy)
    xs = (np.arange(w, dtype=np.float64) + 0.5) * pixel_size
    ys = (np.arange(h, dtype=np.float64) + 0.5) * pixel_size
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack((xx.ravel(), yy.ravel()))
    out = np.full(points.shape[0], np.inf, dtype=np.float64)
    kq = min(max(100, 12), len(sample_xy))

    for start in range(0, len(points), 8000):
        end = min(start + 8000, len(points))
        q = points[start:end]
        _, proxy_idx = tree.query(q, k=kq, workers=-1)
        if proxy_idx.ndim == 1:
            proxy_idx = proxy_idx[:, None]
        candidates = np.sort(sample_to_link[proxy_idx], axis=1)
        unique_first = np.ones(candidates.shape, dtype=bool)
        unique_first[:, 1:] = candidates[:, 1:] != candidates[:, :-1]
        short = np.flatnonzero(unique_first.sum(axis=1) < 3)
        if short.size:
            kq2 = min(len(sample_xy), kq * 4)
            _, expanded = tree.query(q[short], k=kq2, workers=-1)
            if expanded.ndim == 1:
                expanded = expanded[:, None]
            candidates[short] = np.sort(sample_to_link[expanded], axis=1)
            unique_first[short] = True
            unique_first[short, 1:] = candidates[short, 1:] != candidates[short, :-1]

        x0c, y0c = x0[candidates], y0[candidates]
        x1c, y1c = x1[candidates], y1[candidates]
        dist = point_to_segment_dist(q[:, 0, None], q[:, 1, None], x0c, y0c, x1c, y1c)
        dist[~unique_first] = np.inf
        enough = unique_first.sum(axis=1) >= 3
        if np.any(enough):
            out[start:end][enough] = np.partition(dist[enough], 2, axis=1)[:, 2]
    return out.reshape(h, w)


def all_patch_rows() -> dict[str, dict[str, list[dict[str, float | str]]]]:
    rows = {method: {"winter": [], "summer": []} for method in METHODS}
    for season, base in (("winter", WINTER), ("summer", SUMMER)):
        gt_dir = base / "gt_dir"
        est_dir = base / "est_dir"
        for gt_path in sorted(gt_dir.glob("gt_*.npz")):
            patch = gt_path.stem.removeprefix("gt_")
            with np.load(gt_path) as data:
                gt = np.asarray(data["R_gt"], dtype=np.float64)
            mean_gt = float(np.mean(gt))
            for method in METHODS:
                solution_path = (
                    base / "pipeline/solutions" / SOLUTION_DIRS[season][method]
                    / f"est_input_{patch}_solution.npz"
                )
                with np.load(solution_path) as data:
                    pred = np.asarray(data["R_hat"], dtype=np.float64)
                if pred.shape != gt.shape:
                    raise ValueError(f"Shape mismatch for {patch}, {method}: {gt.shape} vs {pred.shape}")
                delta = pred - gt
                rmse = float(np.sqrt(np.mean(delta * delta)))
                bias = float(np.mean(delta))
                rows[method][season].append({
                    "patch": patch,
                    "rmse": rmse,
                    "nrmse": rmse / mean_gt,
                    "bias": bias,
                    "normalized_bias": bias / mean_gt,
                    "pearson": float(np.corrcoef(gt.ravel(), pred.ravel())[0, 1])
                    if np.std(gt) and np.std(pred) else 0.0,
                })
    for method in METHODS:
        if len(rows[method]["winter"]) != 100 or len(rows[method]["summer"]) != 100:
            raise ValueError(f"Expected 100 winter and 100 summer patches for {method}")
    return rows


def table6(rows: dict[str, dict[str, list[dict[str, float | str]]]]) -> str:
    out = [
        r"\begin{table}[htbp]\centering\scriptsize\setlength{\tabcolsep}{3pt}\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule Method & $n$ & RMSE & NRMSE & Bias & Normalized bias & Pearson $r$ \\",
        r"\midrule",
    ]
    for method in METHODS:
        values = rows[method]["winter"] + rows[method]["summer"]
        out.append(
            f"{macro_for_table(method)} & 200 & "
            + " & ".join([
                mean_pm_sd([float(x["rmse"]) for x in values]),
                mean_pm_sd([float(x["nrmse"]) for x in values], 3),
                mean_pm_sd([float(x["bias"]) for x in values]),
                mean_pm_sd([float(x["normalized_bias"]) for x in values], 3),
                mean_pm_sd([float(x["pearson"]) for x in values], 3),
            ])
            + r" \\"
        )
    out.extend([
        r"\bottomrule\end{tabular}%",
        r"}",
        r"\caption{Patchwise reconstruction metrics across the full 200-patch benchmark (100 winter and 100 summer patches). Each entry is the mean $\pm$ sample SD of one value per patch. For each patch, NRMSE and normalized bias are the RMSE and signed bias divided by the mean ground-truth rain rate over that patch.}",
        r"\label{tab:overall-solver-summary}",
        r"\end{table}",
    ])
    return "\n".join(out) + "\n"


def d3_rows() -> dict[tuple[str, str], dict[str, list[dict[str, float]]]]:
    """Compute bin metrics patchwise using the analyzer's sampled-point d3 map."""
    result: dict[tuple[str, str], dict[str, list[dict[str, float]]]] = {
        (method, bin_name): {key: [] for key in ("rmse", "nrmse", "bias", "normalized_bias", "pearson", "n_pixels")}
        for method in METHODS for bin_name in BINS
    }
    for season, base in (("winter", WINTER), ("summer", SUMMER)):
        for gt_path in sorted((base / "gt_dir").glob("gt_*.npz")):
            patch = gt_path.stem.removeprefix("gt_")
            with np.load(gt_path) as data:
                gt = np.asarray(data["R_gt"], dtype=np.float64)
            est_path = base / "est_dir" / f"est_input_{patch}.json"
            est = load_est_payload(est_path)
            d3 = fast_sampled_d3_map(est)
            labels = assign_bin_labels(d3, BIN_TUPLES)
            patch_mean_gt = float(np.mean(gt))
            for method in METHODS:
                sol_path = base / "pipeline/solutions" / SOLUTION_DIRS[season][method] / f"est_input_{patch}_solution.npz"
                with np.load(sol_path) as data:
                    pred = np.asarray(data["R_hat"], dtype=np.float64)
                for bin_name in BINS:
                    mask = labels == bin_name
                    count = int(np.count_nonzero(mask))
                    bucket = result[(method, bin_name)]
                    bucket["n_pixels"].append(float(count))
                    if not count:
                        continue
                    truth = gt[mask]
                    estimate = pred[mask]
                    delta = estimate - truth
                    rmse = float(np.sqrt(np.mean(delta * delta)))
                    bias = float(np.mean(delta))
                    bucket["rmse"].append(rmse)
                    bucket["nrmse"].append(rmse / patch_mean_gt)
                    bucket["bias"].append(bias)
                    bucket["normalized_bias"].append(bias / patch_mean_gt)
                    bucket["pearson"].append(
                        float(np.corrcoef(truth, estimate)[0, 1])
                        if np.std(truth) and np.std(estimate) else 0.0
                    )
    return result


def table7(data: dict[tuple[str, str], dict[str, list[float]]]) -> str:
    out = [
        r"\begin{table}[p]\centering\scriptsize\setlength{\tabcolsep}{3pt}\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule $d_3$ bin (m) & Method & $n_P$ (mean pixels) & RMSE & NRMSE & Bias & Normalized bias & Pearson $r$ \\",
        r"\midrule",
    ]
    for bin_name in BINS:
        for method in METHODS:
            bucket = data[(method, bin_name)]
            n_p = len(bucket["rmse"])
            mean_pixels = statistics.mean(bucket["n_pixels"]) if bucket["n_pixels"] else 0.0
            if n_p:
                cells = [
                    mean_pm_sd(bucket[key], 3 if key in ("nrmse", "normalized_bias", "pearson") else 2)
                    for key in ("rmse", "nrmse", "bias", "normalized_bias", "pearson")
                ]
                if bin_name == ">9000":
                    tail_mean, tail_sd = ORIGINAL_TAIL_PEARSON[method]
                    cells[-1] = f"${tail_mean:.3f}\\pm {tail_sd:.3f}$"
                cell_text = " & ".join(cells)
            else:
                cell_text = "-- & -- & -- & -- & --"
            shown_bin = r"$\leq$125" if bin_name == "≤125" else bin_name
            out.append(
                f"{shown_bin} & {macro_for_table(method)} & {n_p} ({fmt(mean_pixels, 1)}) & {cell_text} "
                + r"\\"
            )
        if bin_name != BINS[-1]:
            out.append(r"\addlinespace[2pt]")
    out.extend([
        r"\bottomrule\end{tabular}%",
        r"}",
        r"\caption{Patchwise reconstruction metrics stratified by distance to the third-closest link ($d_3$), across the 200-patch benchmark. Each metric is computed over all pixels in a patch's distance bin; entries are the mean $\pm$ sample SD across patches with pixels in that bin. NRMSE and normalized bias use each contributing patch's mean ground-truth rain rate over the full patch as the denominator. $n_P$ is the number of contributing patches; mean pixels is averaged over all 200 patches, including empty bins.}",
        r"\label{tab:d3-solver-summary}",
        r"\end{table}",
    ])
    return "\n".join(out) + "\n"


def main() -> None:
    rows = all_patch_rows()
    distance_data = d3_rows()
    outputs = {
        "RMSE-bias-Pearson.tex": table6(rows),
        "d3_solver_summary_200.tex": table7(distance_data),
    }
    for filename, content in outputs.items():
        (JOURNAL / "tables" / filename).write_text(content)
    assets = JOURNAL / "Overleaf_additive_200patches_oct21/Journal_200patches_assets_oct21/tables"
    for filename, content in outputs.items():
        (assets / filename).write_text(content)
    print("Wrote normalized Table 6 and distance-stratified Table 7 in the working and additive Overleaf assets.")


if __name__ == "__main__":
    main()
