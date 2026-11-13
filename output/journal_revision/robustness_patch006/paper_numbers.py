"""Numbers quoted in the Robustness Analysis section that are not read directly from one stored field.

Reads results_idw.json, results_convex.json, results_ops_check.json, results_lmin.json and idw_fields.npz
(all written by the other scripts in this folder) and recomputes IDW on error draws 0-4 (about one minute).
Writes paper_numbers.json and prints a short report. No solver is run.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import common as C  # noqa: E402

rj = lambda f: json.loads((OUT / f).read_text())
idw, cvx, ops, lmin = rj("results_idw.json"), rj("results_convex.json"), rj("results_ops_check.json"), rj("results_lmin.json")
res = {}

# ---- IDW: tightness of Prop. 1(ii) against the exact worst case, and locality (tab:robust-idw text)
f = np.load(OUT / "idw_fields.npz")
for m, Wk, Bk, thr in [("N1", "W1", "B1", (2.0, 5.0)), ("N2", "W2", "B2", (10.0,))]:
    Wc, B = f[Wk], f[Bk]
    r = Wc / np.where(B > 0, B, np.nan)
    res[f"idw_{m}"] = {
        "worst_over_bound_median": float(np.nanmedian(r)),
        "worst_over_bound_min": float(np.nanmin(r)),
        "eta_eps_plus_mu_max": idw[m]["geometry_free"]["max_l_b_l"],
        "worst_p99": float(np.percentile(Wc, 99)),
        **{f"frac_worst_gt_{t:g}": float((Wc > t).mean()) for t in thr},
    }
res["idw_links_shorter_than_500m"] = idw["patch_facts"]["n_endpoint_lt_500m"]
res["idw_noise_free_mean"] = idw["patch_facts"]["idw_noise_free_mean"]
res["idw_N2_worst_mean_increase"] = idw["N2"]["worst_mean_signed_shift"] / idw["patch_facts"]["idw_noise_free_mean"]

# ---- IDW on the error draws used for the Convex runs (seeds 0-4), IDW rows of tab:robust-convex
R0 = C.req(C.A)
idw5 = {}
for m, E in [("N1", 0.5), ("N2", 2.3)]:
    rows = []
    for s in range(5):
        D = C.idw_apply(C.req(C.A + C.noise(s, m, E)) - R0)
        rows.append([float(np.abs(D).max()), float(np.sqrt(np.mean(D**2))), float(np.median(np.abs(D))), float(D.mean())])
    x = np.array(rows)
    idw5[m] = {"max": x[:, 0].max(), "rms": x[:, 1].mean(), "median": x[:, 2].mean(), "mean": x[:, 3].mean(), "per_seed": rows}
w = idw["N2"]["worst_case_eq_const_2p3_on_wet"]
idw5["N2const"] = {"max": w["max"], "rms": w["rms"], "median": w["median"], "mean": idw["N2"]["worst_mean_signed_shift"]}
res["table_convex_idw_rows"] = idw5

# ---- Convex rows of tab:robust-convex: max over seeds, mean of RMS, median and signed mean
runs = cvx["runs"]
ca = ops["c_a"]  # c_a = 2 w_atten kappa0^2 / n_valid
a = ca / 2
nf_mean = cvx["max_principle_noise_free"]["nf"]["mean"]
tab = {}
for m in ("N1", "N2", "N2const"):
    for v in ("F", "R"):
        rs = [r for r in runs if r["model"] == m and r["variant"] == v]
        tab[f"{m}_{v}"] = {
            "max": max(r["dR"]["max"] for r in rs),
            "rms": float(np.mean([r["dR"]["rms"] for r in rs])),
            "median": float(np.mean([r["dR"]["median"] for r in rs])),
            "mean": float(np.mean([r["mean_signed_shift"] for r in rs])),
            "mean_increase_vs_noise_free": float(np.mean([r["mean_signed_shift"] for r in rs])) / nf_mean,
            "n_runs": len(rs),
        }
res["table_convex_rows"] = tab

# ---- Prop. 2 (factor-2 form) in the fixed-weight runs.
# The runs store the factor-1 form (claim_*). With G = cor_i_lhs = sum |l| <dR>^2 and
# 2S = claim_lhs - c_a G (S: smoothness terms), the factor-2 ratio is (G + 2S/a) / rhs = 2 claim_ratio - cor_i_ratio.
p2 = {}
for r in runs:
    if r["variant"] != "F":
        continue
    G, rhs = r["cor_i_lhs"], r["cor_i_rhs"]
    twoS = r["claim_lhs_noise_free_H"] - ca * G
    p2[r["name"]] = {"ratio_factor2": (G + twoS / a) / rhs, "smoothness_share_of_rhs": (twoS / a) / rhs,
                     "check_2claim_minus_cori": 2 * r["claim_ratio_noise_free_H"] - r["cor_i_ratio"]}
res["prop2_factor2"] = p2
res["prop2_holds_all_fixed_runs"] = all(v["ratio_factor2"] <= 1 for v in p2.values())

# ---- Maximum principle
res["max_dR_over_max_dr_all_runs"] = max(r["dR"]["max"] / r["max_abs_dr"] for r in runs)
mp = cvx["max_principle_noise_free"]["nf"]
res["noise_free_pixels_above_max_r"] = mp["n_above_max_r"]
res["noise_free_max_excess_above_max_r"] = mp["max_excess_above_max_r"]
res["noise_free_max_r_link"] = cvx["max_principle_noise_free"]["r_l_range"][1]

# ---- Paired paths: links with identical endpoints, and their noise-free agreement
g = defaultdict(list)
for li in range(C.NL):
    if C.OK[li]:
        key = tuple(sorted([(round(C.x0[li], 3), round(C.y0[li], 3)), (round(C.x1[li], 3), round(C.y1[li], 3))]))
        g[key].append(li)
sizes = np.array([len(v) for v in g.values()])
spread = [(R0[v].max() - R0[v].min()) / R0[v].mean() for v in g.values() if len(v) >= 2]
res["paths"] = {"n_paths": len(g), "size_counts": {int(s): int((sizes == s).sum()) for s in np.unique(sizes)},
                "links_on_shared_paths": int(sum(len(v) for v in g.values() if len(v) >= 2)),
                "median_relative_spread_noise_free": float(np.median(spread))}

# ---- Weights recomputed from the noisy ILDW (R runs)
w0 = ops["weights"]
wr = {}
for m in ("N1", "N2", "N2const"):
    x = np.array([[r["weights_from_noisy_ildw"][k] for k in ("alpha_atten", "alpha_1d", "alpha_2d")]
                  for r in runs if r["model"] == m and r["variant"] == "R"])
    r1 = x[:, 1] / x[:, 0] / (w0["alpha_1d"] / w0["alpha_atten"])
    r2 = x[:, 2] / x[:, 0] / (w0["alpha_2d"] / w0["alpha_atten"])
    wr[m] = {"w_atten": [x[:, 0].min(), x[:, 0].max()], "w_1d": [x[:, 1].min(), x[:, 1].max()],
             "w_2d": [x[:, 2].min(), x[:, 2].max()], "J_atten_ildw": [1 / x[:, 0].max(), 1 / x[:, 0].min()],
             "w1d_over_watten_factor": [r1.min(), r1.max()], "w2d_over_watten_factor": [r2.min(), r2.max()]}
res["weights_noise_free"] = {k: w0[k] for k in ("alpha_atten", "alpha_1d", "alpha_2d", "J_atten_ildw")}
res["weights_recomputed"] = wr

# ---- Stopping error and conditioning
st = cvx["noise_free"]["stopping_error_nf_vs_tight"]
n1 = [r["dR"]["rms"] for r in runs if r["model"] == "N1"]
n2 = [r["dR"]["rms"] for r in runs if r["model"] == "N2"]
res["stopping"] = {"max": st["max"], "rms": st["rms"], "rms_share_of_N1_rms": [st["rms"] / max(n1), st["rms"] / min(n1)],
                   "rms_share_of_N2_rms": [st["rms"] / max(n2), st["rms"] / min(n2)],
                   "nf_nit": cvx["noise_free_runs"]["nf"]["nit"], "nf_stop": cvx["noise_free_runs"]["nf"]["stop_reason"],
                   "stop_reasons": {r["name"]: r["stop_reason"] for r in runs}}
res["hessian_condition_number"] = lmin["condition_number"]

(OUT / "paper_numbers.json").write_text(json.dumps(res, indent=1, default=float))

print("IDW tightness N1 median %.3f min %.3f | N2 median %.3f min %.3f" % (
    res["idw_N1"]["worst_over_bound_median"], res["idw_N1"]["worst_over_bound_min"],
    res["idw_N2"]["worst_over_bound_median"], res["idw_N2"]["worst_over_bound_min"]))
print("IDW locality N1 >2: %.4f >5: %.5f p99 %.2f | N2 >10: %.4f p99 %.2f" % (
    res["idw_N1"]["frac_worst_gt_2"], res["idw_N1"]["frac_worst_gt_5"], res["idw_N1"]["worst_p99"],
    res["idw_N2"]["frac_worst_gt_10"], res["idw_N2"]["worst_p99"]))
for k, v in idw5.items():
    print("table IDW %-8s max %.2f rms %.2f median %.2f mean %.2f" % (k, v["max"], v["rms"], v["median"], v["mean"]))
for k, v in tab.items():
    print("table Convex %-10s max %.2f rms %.2f median %.2f mean %.2f  mean increase %.2f" % (
        k, v["max"], v["rms"], v["median"], v["mean"], v["mean_increase_vs_noise_free"]))
print("Prop 2 factor-2 ratios:", {k: round(v["ratio_factor2"], 4) for k, v in p2.items()})
print("max smoothness share %.4f" % max(v["smoothness_share_of_rhs"] for v in p2.values()))
print("max |dR|/max|dr| %.3f, noise-free pixels above max r %d, excess %.2f" % (
    res["max_dR_over_max_dr_all_runs"], mp["n_above_max_r"], mp["max_excess_above_max_r"]))
print("paths", res["paths"])
print("weights recomputed", json.dumps(wr, default=float))
print("stopping", {k: v for k, v in res["stopping"].items() if k != "stop_reasons"})
print("condition number %.3g" % lmin["condition_number"])
