# patch006 robustness runs

Patch: RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306192200_patch006

## Patch facts

| quantity | value |
|---|---|
| H | 752 |
| W | 704 |
| pixels | 529408 |
| links | 2093 |
| wet_A_gt_0_positive_length | 2092 |
| dry_A_eq_0_positive_length | 0 |
| zero_endpoint_length | 1 |
| min_endpoint_length_m_positive | 58.228080868849304 |
| n_endpoint_lt_100m | 2 |
| n_endpoint_lt_500m | 97 |
| median_endpoint_length_km | 2.2580299470161065 |
| max_endpoint_length_km | 21.500191307457815 |
| freq_range_ghz | [12.765, 58.2] |
| pols | {'H': 2093} |
| A_db_median | 1.8197343019011682 |
| A_db_max | 13.089562555209913 |
| idw_noise_free_mean | 3.428554614172901 |
| n_inv_alpha_gt_1_positive_length | 1911 |
| n_inv_alpha_le_1_positive_length | 181 |
| inv_alpha_range_positive_length | [0.8593124470076328, 1.2947455792237124] |
| freq_link899_ghz | 57.2 |
| convex_noise_free_mean (nf rerun) | 3.4181054228420233 |

## IDW (20 seeds each)

| model | random max | random RMS (mean, range) | random median | mean signed | exact worst max / RMS / median | pixel bound max / RMS / median | max_l b_l (link) |
|---|---|---|---|---|---|---|---|
| N1 | 7.64 | 0.131 (0.121–0.141) | 0.0529 | 0.00709 | 26.2 / 0.955 / 0.849 | 30 / 0.995 / 0.88 | 30.1 (link 1231, 58 m, 57.2 GHz) |
| N2 | 137 | 2.34 (2.23–2.42) | 2.01 | 2.16 | 161 / 4.74 / 4.12 | 199 / 5.1 / 4.36 | 199 (link 1214, 58 m, 58.2 GHz) |

IDW assertions: N1 per-link b >= max(up,dn): PASS, N1 per-link b >= |random change|: PASS, N2 per-link b >= up: PASS, N2 random change >= 0: PASS, A+e >= 0 (all 40 draws, asserted inside noise()): PASS, N1 random <= worst <= bound per pixel: PASS, N2 random <= worst <= bound per pixel: PASS

IDW reproduction: {'max_abs_diff_vs_stored_float32': 4.768277044320257e-07, 'max_abs_diff_vs_stored_after_float32_cast': 0.0, 'stored_max': 12.021784782409668, 'link_values_max_abs_diff_vs_mine': 3.552713678800501e-15, 'max_abs_diff_mine_vs_repo_kernel_20000_random_pixels': 1.0658141036401503e-14, 'max_abs_diff_mine_vs_repo_midpoint_rule_pixels': 3.552713678800501e-15, 'n_midpoint_rule_pixels': 1139}

## Convex runs (reference: noise-free rerun nf, ftol 1e-6)

| run | nit | stop | opt s | proj grad inf | |dR| max | RMS | median | mean signed | claim ratio (H0) | cor (i) ratio | own-H ratio | pixels |dR|>max|dr| | RMS bound (ii) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| n1_s0_F | 749 | ftol | 496 | 0.0007 | 6.36 | 0.307 | 0.17 | -0.0357 | 0.5273 | 0.5166 | – | 0 | 28.4 |
| n1_s0_R | 406 | gtol | 277 | 7.14e-07 | 2.43 | 0.228 | 0.124 | 0.00726 | 0.3623 | 0.3588 | 0.4308 | 0 | 28.4 |
| n1_s1_F | 728 | ftol | 480 | 0.000573 | 5.44 | 0.301 | 0.154 | -0.0208 | 0.4848 | 0.4744 | – | 0 | 28.5 |
| n1_s1_R | 366 | gtol | 257 | 6.9e-07 | 2.19 | 0.209 | 0.114 | 0.0141 | 0.3204 | 0.3174 | 0.3856 | 0 | 28.5 |
| n1_s2_F | 744 | ftol | 494 | 0.000146 | 5.21 | 0.314 | 0.157 | -0.0367 | 0.488 | 0.4792 | – | 0 | 28.5 |
| n1_s2_R | 350 | ftol | 251 | 5.16e-05 | 2.3 | 0.225 | 0.117 | -0.0111 | 0.3367 | 0.3338 | 0.3968 | 0 | 28.5 |
| n1_s3_F | 766 | ftol | 546 | 0.000173 | 5.07 | 0.293 | 0.152 | -0.026 | 0.5347 | 0.5249 | – | 0 | 28.7 |
| n1_s3_R | 396 | gtol | 247 | 8.69e-07 | 2.68 | 0.229 | 0.131 | 0.00507 | 0.3822 | 0.3791 | 0.4466 | 0 | 28.7 |
| n1_s4_F | 751 | ftol | 575 | 0.000497 | 4.45 | 0.302 | 0.163 | -0.0157 | 0.5208 | 0.5109 | – | 0 | 28.5 |
| n1_s4_R | 397 | gtol | 288 | 7.61e-07 | 2.01 | 0.227 | 0.119 | 0.0162 | 0.364 | 0.3607 | 0.4288 | 0 | 28.5 |
| n2_s0_F | 592 | ftol | 456 | 0.0012 | 45.7 | 1.66 | 1.13 | 1.21 | 0.8737 | 0.8666 | – | 0 | 149 |
| n2_s0_R | 245 | gtol | 193 | 9.86e-07 | 22.4 | 1.58 | 1.23 | 1.32 | 0.7537 | 0.7513 | 0.8007 | 0 | 149 |
| n2_s1_F | 623 | ftol | 492 | 0.000687 | 45.9 | 1.63 | 1.16 | 1.22 | 0.862 | 0.8535 | – | 0 | 151 |
| n2_s1_R | 242 | gtol | 179 | 7.9e-07 | 23 | 1.55 | 1.24 | 1.31 | 0.7297 | 0.7275 | 0.7783 | 0 | 151 |
| n2_s2_F | 528 | ftol | 425 | 0.00187 | 83.3 | 1.65 | 1.05 | 1.09 | 0.8523 | 0.8403 | – | 0 | 155 |
| n2_s2_R | 241 | gtol | 192 | 7.43e-07 | 25.3 | 1.54 | 1.16 | 1.25 | 0.7026 | 0.7003 | 0.7546 | 0 | 155 |
| n2_s3_F | 596 | ftol | 398 | 0.0018 | 54.7 | 1.65 | 1.12 | 1.19 | 0.8676 | 0.8585 | – | 0 | 150 |
| n2_s3_R | 258 | gtol | 213 | 5.26e-07 | 29.8 | 1.58 | 1.25 | 1.31 | 0.7312 | 0.7288 | 0.7817 | 0 | 150 |
| n2_s4_F | 607 | ftol | 248 | 0.00152 | 68.3 | 1.66 | 1.13 | 1.2 | 0.8739 | 0.8639 | – | 0 | 153 |
| n2_s4_R | 274 | gtol | 213 | 6.05e-07 | 27.8 | 1.61 | 1.23 | 1.34 | 0.7429 | 0.7404 | 0.7908 | 0 | 153 |
| n2const_F | 710 | ftol | 567 | 0.00257 | 131 | 3.11 | 2.36 | 2.59 | 0.9863 | 0.9766 | – | 0 | 267 |
| n2const_R | 348 | gtol | 256 | 8.85e-07 | 72.6 | 3.07 | 2.43 | 2.67 | 0.9183 | 0.9143 | 0.9465 | 0 | 267 |

Noise-free runs: {"nf": {"nit": 1095, "stop_reason": "ftol", "optimizer_seconds": 263.8875907077454, "wall_seconds": 264.7396490573883, "proj_grad_inf": 0.00017950116345702094, "fun": 0.29056088496903676, "ftol": 1e-06, "gtol": 1e-06, "maxiter": 2000, "maxrss_MB": 448.453125}, "nf_tight": {"nit": 2730, "stop_reason": "ftol", "optimizer_seconds": 1421.0443885000423, "wall_seconds": 1422.3822510242462, "proj_grad_inf": 3.7765984884405715e-07, "fun": 0.290318643540213, "ftol": 1e-12, "gtol": 1e-09, "maxiter": 15000, "maxrss_MB": 450.90625}, "stored": {"nit": 1095, "stop_reason": "ftol", "optimizer_seconds": 219.15736225, "proj_grad_inf": 0.00017950116345702094}}

Noise-free comparisons: {"nf_vs_stored": {"max": 0.0, "rms": 0.0, "median": 0.0}, "nf_tight_vs_stored": {"max": 0.2284684181213379, "rms": 0.034516356199378595, "median": 0.0062043070793151855}, "stopping_error_nf_vs_tight": {"max": 0.2284684181213379, "rms": 0.034516356199378595, "median": 0.0062043070793151855}, "stopping_error_mean_signed_nf_minus_tight": -0.008430643067668338, "stored_vs_tight": {"max": 0.2284684181213379, "rms": 0.034516356199378595, "median": 0.0062043070793151855}, "f_nf": 0.29056088496903676, "f_tight": 0.290318643540213, "f_stored": 0.29056088496903676, "H_norm_sq_nf_minus_tight": 0.0004846520347337013, "H_norm_sq_stored_minus_tight": 0.0004846520347337013, "r_identical_nf_tight": true}

Max principle (noise-free): {"r_l_range": [0.008492333811785413, 12.021784636523117], "stored": {"R_min": 0.0, "R_max": 14.311999320983887, "n_above_max_r": 297, "n_below_min_r": 146, "n_zero": 46, "mean": 3.4181054228420233, "max_excess_above_max_r": 2.2902146844607696}, "nf": {"R_min": 0.0, "R_max": 14.311999320983887, "n_above_max_r": 297, "n_below_min_r": 146, "n_zero": 46, "mean": 3.4181054228420233, "max_excess_above_max_r": 2.2902146844607696}, "nf_tight": {"R_min": 0.0, "R_max": 14.316216468811035, "n_above_max_r": 292, "n_below_min_r": 158, "n_zero": 46, "mean": 3.4265360659096915, "max_excess_above_max_r": 2.294431832287918}}

## lambda_min(H)

```
{
 "H_nnz": 6569808,
 "splu": {
  "seconds": 119.39423608779907,
  "L_nnz": 91313005,
  "U_nnz": 91313005,
  "maxrss_MB_after": 1122.59375,
  "ordering": "MMD_AT_PLUS_A, diag_pivot_thresh 0, SymmetricMode",
  "solve_rel_residual_random_rhs": 1.5852442717045626e-14
 },
 "eigsh_shift_invert": {
  "tol_1e-08": {
   "eigs_smallest4": [
    2.806399951669656e-07,
    3.0615864922025213e-07,
    3.2073161479988743e-07,
    4.0748747038629047e-07
   ],
   "rel_residuals": [
    5.7123784918500846e-12,
    5.364749503040484e-12,
    5.499548382715167e-12,
    2.6324406359511477e-10
   ],
   "rayleigh_quotients": [
    2.8063999516671857e-07,
    3.061586492200103e-07,
    3.207316147996502e-07,
    4.0748747038607564e-07
   ],
   "seconds": 47.55632281303406
  },
  "tol_1e-12": {
   "eigs_smallest4": [
    2.8063999516696585e-07,
    3.0615864922025187e-07,
    3.2073161479988743e-07,
    4.0748747038628973e-07
   ],
   "rel_residuals": [
    4.522954189442225e-12,
    4.290606272982183e-12,
    4.145251420319653e-12,
    4.492771559842915e-12
   ],
   "rayleigh_quotients": [
    2.806399951667175e-07,
    3.0615864922000993e-07,
    3.207316147996543e-07,
    4.074874703860749e-07
   ],
   "seconds": 44.50391602516174
  }
 },
 "inverse_iteration_300_steps_rayleigh": 2.8063999516672196e-07,
 "rayleigh_constant_vector_upper_bound": 0.001251737341291775,
 "lambda_min": 2.8063999516696585e-07,
 "lambda_min_eigvec": {
  "abs_max": 0.018025177225386872,
  "sign_uniform": false,
  "participation_ratio_over_P": 0.010460283570301421
 },
 "lambda_max": 0.06199926457990618,
 "lambda_max_seconds": 1.1776587963104248,
 "condition_number": 220920.98648669058,
 "unconstrained_minimizer": {
  "min": -0.20812028851645012,
  "n_negative": 144,
  "n_below_minus_1e-6": 144,
  "f": 0.2902648933495584,
  "max": 14.31620500069702,
  "f_stored": 0.29056088496236043,
  "max_abs_diff_vs_stored": 0.22858329745091766,
  "rms_diff_vs_stored": 0.03456785147028965,
  "f_nf": 0.29056088496236043,
  "max_abs_diff_vs_nf": 0.22858329745091766,
  "rms_diff_vs_nf": 0.03456785147028965,
  "f_nf_tight": 0.29031864355147263,
  "max_abs_diff_vs_nf_tight": 0.20812028851645012,
  "rms_diff_vs_nf_tight": 0.004780365927101637
 },
 "maxrss_MB": 2083.953125,
 "seconds": 369.72367906570435
}
```

## Quadratic form check

```
{
 "n_valid": 2092,
 "P": 529408,
 "kappa0": 0.15589135351133135,
 "alpha0": 1.0000000000000016,
 "c_a": 0.10184010268013512,
 "H_nnz": 6569808,
 "quadratic_vs_code": {
  "stored_R_hat": {
   "f_code": 0.290560884965503,
   "f_quadratic": 0.29056088496236043,
   "rel_diff_f": 1.0815432995139167e-11,
   "rel_diff_grad_inf": 6.541326772179942e-11
  },
  "uniform_0_5": {
   "f_code": 4092.2574604533343,
   "f_quadratic": 4092.2574604533374,
   "rel_diff_f": 7.778668588101529e-16,
   "rel_diff_grad_inf": 2.410563654503023e-15
  },
  "const_0p6": {
   "f_code": 4717.089919101777,
   "f_quadratic": 4717.089919101776,
   "rel_diff_f": 1.928084300640411e-16,
   "rel_diff_grad_inf": 1.4635992392653424e-15
  }
 },
 "r_in_grid_vs_endpoint_length": {
  "max_abs_diff": 4.973799150320701e-14,
  "n_diff_gt_1e-6": 0,
  "max_rel_diff": 7.246943155949214e-15
 }
}
```

## Weight rule diagnosis (R runs, appended after make_summary.py)

Noise-free weights: alpha_atten 4383.35, alpha_1d 88.41, alpha_2d 39.99.

| run | alpha_atten | alpha_1d |
|---|---|---|
| n1_s0_R | 138.6 | 58.77 |
| n1_s1_R | 127.5 | 59.28 |
| n1_s2_R | 128.5 | 58.23 |
| n1_s3_R | 137.9 | 62.01 |
| n1_s4_R | 138.4 | 60.20 |
| n2_s0_R | 17.2 | 7.53 |
| n2_s1_R | 15.4 | 7.52 |
| n2_s2_R | 13.0 | 6.57 |
| n2_s3_R | 15.2 | 7.53 |
| n2_s4_R | 15.7 | 7.06 |
| n2const_R | 16.1 | 2.87 |

Cause: the weight rule scales by the inverse of J_atten at the ILDW initial field. J_atten(ILDW) is 2.28e-4 noise free and 7.2e-3 to 7.8e-3 with noise. Patch006 has 935 shared paths (1870 links) whose noise-free R agree to a median relative spread of 2.3e-5. Independent per-link noise breaks that agreement, so no field fits both links of a pair and J_atten(ILDW) rises about 30x. The top 5 links carry only 4% of J_atten, so the rise is spread, not driven by outliers.
