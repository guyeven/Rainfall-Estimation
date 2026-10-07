# Unnormalized Taylor diagrams

These figures use the same saved six methods and 100 whole patches as the normalized comparison. No solver was rerun. All fields are centered by their own means within each patch. No ground-truth-SD normalization is applied. Standard deviations and centered RMSEs are in mm/h; correlations are dimensionless.

## Combined diagram

For each method, the combined ground-truth SD is G = sqrt(mean(sigma_GT_i^2)), the combined model SD is F = sqrt(mean(sigma_model_i^2)), and covariance C = mean(r_i * sigma_GT_i * sigma_model_i). Each patch contributes equal weight (1/100); pixels within each patch contribute equal weights (1/N_i).

The combined model point has radius F and angle arccos(C/(F*G)). Its reference is at (G, 0). Its distance to that reference is sqrt(mean(centered_RMSE_i^2)). It is not the arithmetic mean of the patch RMSEs, and centering means it excludes mean bias.

## Individual diagrams

Each diagram contains all 100 patch-level model points for one method. The patch point has radius sigma_model_i and angle arccos(r_i). Its own reference star is at (sigma_GT_i, 0). Points, reference stars, and connecting segments share a color determined by the patch ground-truth SD. Each straight segment has length equal to that patch centered RMSE.

Without normalization, different patches do not share one reference star. Hence these diagrams intentionally have no common centered-RMSE contours. The black diamond and black star identify the combined model and reference for context. All six individual diagrams use identical axis limits. The six-panel overview repeats the standalone diagrams.

## Files and checks

- `combined_taylor_unnormalized.png` / `.svg`: six combined model points.
- `individual_taylor_unnormalized_all_methods.png` / `.svg`: six-panel overview of individual patch results.
- `individual_<method>_unnormalized.png` / `.svg`: six standalone method diagrams.
- `statistics.json`: exact combined statistics and 600 patch-level records, including physical SD, covariance, correlation, centered RMSE, mean bias, ordinary RMSE, and Cartesian coordinates.
- `build_unnormalized_taylor.py`: generator (NumPy and Matplotlib required).

The generator verifies finite values and matching field shapes, all 600 patch-level Taylor identities and bias decompositions, the six combined identities, and every plotted error-segment length.

To reproduce within this repository, run `python output/taylor_unnormalized/build_unnormalized_taylor.py`. Outside the repository, pass `--data-root /path/to/Compute-Link-Attenuations/HundredPatches`.
