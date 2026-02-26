# Disjoint-Link Sanity Check (>=177 m)

This folder is a sanity check built with synthetic links constrained so no two links are closer than 177 m (therefore links fall into distinct 125 m pixels in this setup).

Data source:
- `batch_analyze_output_multi/stats_multi.xlsx`
- Sheet `LinkStats_GTvsILDW`: `J_atten_all` is in the order of 1e-31.
- Sheet `LinkStats_GTvsIDW`: `J_atten_all` is in the order of 1e-3.

Patch-level `J_atten_all` (ILDW):
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301310900_patch000`: `1.231258969087334012e-31`
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301311600_patch000`: `8.736512270966203916e-32`
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301312000_patch001`: `1.060238069315271940e-31`

Patch-level `J_atten_all` (IDW):
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301310900_patch000`: `3.388074063879309861e-03`
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301311600_patch000`: `1.165698495441943065e-03`
- `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301312000_patch001`: `2.450485362705027113e-03`

Averages from the same sheets:
- `J_atten_all` ILDW average: `1.055049421833075995e-31`
- `J_atten_all` IDW average: `2.334752640675427041e-03`
- ILDW/IDW ratio (average): `4.518891652384458987e-29`

This is dramatically smaller than the ~5-9% ILDW/IDW regime observed with the original Netherlands link set.

The overlay image for this setup is:
- `patch_links_viewer_gt177m_disjoint_patches.png`

The IDW/ILDW implementation used here is the same baseline implementation used previously, documented in:
- `idw_ildw_pseudocode.pdf`
- `idw_ildw_pseudocode.tex`
