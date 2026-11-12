#!/usr/bin/env python3
"""Compute the objective values and whole-patch RMSEs quoted for the two case studies.

J = w_atten J_atten + w_1d J_1d + w_2d J_2d, with the weights stored as alpha_* in the itertrace files.

* J at the ground truth: iteration 0 of the Solver(GT) trace, which starts from the ground-truth field.
* J(Solver(GT)): last row of the Solver(GT) trace.
* Convex surrogate J: last row of the Convex Solver trace. It is evaluated on the virtual links, with
  w_atten recomputed on those links, so it is not comparable with the other values.
* J(Convex Solver) in the original objective: w_atten (real links, from the Solver(GT) trace) * J_atten_real
  + w_1d J_1d + w_2d J_2d, all taken from the last row of the Convex Solver trace.
* RMSE: sqrt(mean((R_hat - R_gt)^2)) over all pixels of the patch.

Usage:  python compute_objective_values.py [--out FILE]   (default: ../objective_values.json)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES, ROOT, SOLVER_DIRS, gt_path, solution_path  # noqa: E402


def rows(c, label):
    return json.loads(solution_path(c, label, "_itertrace.json").read_text())["iterations"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "objective_values.json")
    args = ap.parse_args()
    result = {}
    for c in CASES:
        gt_rows, cx_rows = rows(c, "Solver(GT)"), rows(c, "Convex Solver")
        g0, gl, cl = gt_rows[0], gt_rows[-1], cx_rows[-1]
        for k in ("alpha_1d", "alpha_2d"):
            if not np.isclose(gl[k], cl[k], rtol=1e-12, atol=0.0):
                raise ValueError(f"{c['case']}: {k} differs between the Solver(GT) and Convex traces")
        j_convex_original = gl["alpha_atten"] * cl["J_atten_real"] + cl["alpha_1d"] * cl["J_1d"] + cl["alpha_2d"] * cl["J_2d"]
        with np.load(gt_path(c)) as d:
            gt = np.asarray(d["R_gt"], dtype=np.float64)
        rmse = {}
        for label in SOLVER_DIRS:
            with np.load(solution_path(c, label)) as d:
                pred = np.asarray(d["R_hat"], dtype=np.float64)
            rmse[label] = float(np.sqrt(np.mean((pred - gt) ** 2)))
        result[c["case"]] = {
            "patch": c["patch"],
            "weights_original_objective": {"w_atten": gl["alpha_atten"], "w_1d": gl["alpha_1d"], "w_2d": gl["alpha_2d"]},
            "w_atten_virtual_links_convex": cl["alpha_atten"],
            "J_ground_truth": g0["J_weighted_sum"],
            "J_ground_truth_J_atten": g0["J_atten"],
            "J_solver_gt_final": gl["J_weighted_sum"],
            "solver_gt_iterations": len(gt_rows) - 1,
            "J_convex_surrogate_final": cl["J_weighted_sum"],
            "J_convex_original_objective": j_convex_original,
            "convex_iterations": len(cx_rows) - 1,
            "rmse_whole_patch_mm_per_h": rmse,
        }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    for case, r in result.items():
        print(f"{case}: J(GT)={r['J_ground_truth']:.4f}  J(Solver(GT))={r['J_solver_gt_final']:.4f}  "
              f"J_convex(surrogate)={r['J_convex_surrogate_final']:.4f}  J(Convex, original)={r['J_convex_original_objective']:.4f}  "
              + "  ".join(f"RMSE {k}={v:.6f}" for k, v in r["rmse_whole_patch_mm_per_h"].items()))
    print(args.out)


if __name__ == "__main__":
    main()
