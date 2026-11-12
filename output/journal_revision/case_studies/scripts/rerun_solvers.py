#!/usr/bin/env python3
"""Rerun Solver(GT) and the Convex Solver (no shrinkage) on the case-study inputs.

Needs a checkout of Compute-Link-Attenuations from this repository (it provides batch_solve_multi.py and
the cml_attenuation package). The stored solutions are not touched: results go to --out/<case>/solutions/.

Usage:  python rerun_solvers.py --repo ../../../../Compute-Link-Attenuations [--case case1 case2] [--out DIR]
"""
import argparse
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True, help="path to Compute-Link-Attenuations")
    ap.add_argument("--case", nargs="+", default=[c["case"] for c in CASES], choices=[c["case"] for c in CASES])
    ap.add_argument("--out", type=Path, default=Path("rerun_output"))
    args = ap.parse_args()
    repo = args.repo.resolve()
    for c in (c for c in CASES if c["case"] in args.case):
        settings = yaml.safe_load((HERE / "solver_settings.yaml").read_text())  # fresh copy per case
        run_dir = (args.out / c["case"]).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        inputs = (c["dir"] / "inputs").resolve()
        cfg = {"resume": False,
               "input": {"est_dir": str(inputs), "file_pattern": "est_input_*.json", "recursive": False},
               **settings}
        for s in cfg["solvers"].values():
            s["out_dir"] = str(run_dir / s["out_dir"])
            gt = s["optimization"]["rain_init"].get("gt")
            if gt is not None:
                gt["dir"] = str(inputs)
        cfg_path = run_dir / "config.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        print(f"{c['case']}: {cfg_path}", flush=True)
        # one process per case: batch_solve_multi.py ends with raise SystemExit
        subprocess.run([sys.executable, str(repo / "batch_solve_multi.py"), "--config", str(cfg_path)], check=True)


if __name__ == "__main__":
    main()
