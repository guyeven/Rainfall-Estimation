#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from batch_analyze_multi import default_cache_path, deep_get, load_config_file, resolve_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--cache-path", default=None)
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    batch_script = here / "batch_analyze_multi.py"
    render_script = here / "render_analysis_report.py"

    analyze_cmd = [sys.executable, str(batch_script), "--config", args.config, "--analyze-only"]
    render_cmd = [sys.executable, str(render_script)]

    cfg_path = Path(args.config).resolve()
    cfg = load_config_file(cfg_path)
    base_dir = cfg_path.parent
    out_dir = (
        resolve_path(deep_get(cfg, "output.out_dir", "batch_analyze_output_multi"), base_dir=base_dir)
        or (base_dir / "batch_analyze_output_multi").resolve()
    )
    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
        analyze_cmd.extend(["--output-dir", args.output_dir])
        render_cmd.extend(["--output-dir", args.output_dir])
    excel_name = str(deep_get(cfg, "output.excel_filename", "coverage_stats_long_multi.xlsx"))
    cache_path = Path(args.cache_path).resolve() if args.cache_path else default_cache_path(out_dir=out_dir, excel_name=excel_name)
    analyze_cmd.extend(["--cache-path", str(cache_path)])
    render_cmd.extend(["--cache", str(cache_path)])

    subprocess.run(analyze_cmd, check=True)
    subprocess.run(render_cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
