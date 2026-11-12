"""Shared definitions of the two journal case studies (paths are relative to this directory)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / "osm_tiles_z7"
ZOOM = 7

CASES = [
    dict(
        case="case1",
        dir=ROOT / "case1_summer_202306120300_patch036",
        patch="RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306120300_patch036",
        title="Piedmont, Italy | 06/12/2023 03:00",
        # patch centre latitude, longitude (degrees), width and height (km)
        geo=(44.78703641118289, 8.073046934026, 82.0, 56.0),
    ),
    dict(
        case="case2",
        dir=ROOT / "case2_winter_202301252200_patch000",
        patch="RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301252200_patch000",
        title="English Channel off northern France | 01/25/2023 22:00",
        geo=(50.46801207625039, 1.2728096221333027, 52.0, 56.0),
    ),
]

SOLVER_DIRS = {
    "IDW": "sol_dir_idw",
    "Solver(GT)": "sol_dir_solver_gt_no_shrinkage",
    "Convex Solver": "sol_dir_convex_no_shrinkage",
}


def gt_path(c):
    return c["dir"] / "inputs" / f"gt_{c['patch']}.npz"


def solution_path(c, label, suffix=".npz"):
    return c["dir"] / "solutions" / SOLVER_DIRS[label] / f"est_input_{c['patch']}_solution{suffix}"
