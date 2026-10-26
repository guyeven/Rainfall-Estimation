#!/usr/bin/env python3
"""Render the 200 winter/summer benchmark patches as ten chronological 4x5 sheets."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
OUT = COMPUTE / "review-sheets-200"


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_winter():
    metadata_path = ROOT / "Patch-Generator/Benchmark-Patches/benchmark-500-files-758-patches.local.jan2023.jsonl"
    metadata = {r["id"]: r for r in rows(metadata_path)}
    ids = [p.stem.removeprefix("patch_") for p in sorted((COMPUTE / "HundredPatches/patch_overview_generation/patch_jsonl_files").glob("patch_*.jsonl"))]
    gt_dir = COMPUTE / "HundredPatches/gt_dir"
    paths = [gt_dir / f"gt_{pid}.npz" for pid in ids]
    if len(paths) != 100 or any(not p.exists() for p in paths):
        raise RuntimeError(f"Expected 100 selected winter ground-truth patches; found {sum(p.exists() for p in paths)}")
    return [(p, metadata[p.stem.removeprefix("gt_")], "winter") for p in paths]


def load_summer():
    roster = rows(COMPUTE / "June2023HundredPatches/benchmark-patches.review-order.jsonl")
    gt_dir = COMPUTE / "June2023HundredPatches/gt_dir"
    items = []
    for meta in roster:
        p = gt_dir / f"gt_{meta['id']}.npz"
        if not p.exists():
            raise FileNotFoundError(p)
        items.append((p, meta, "summer"))
    if len(items) != 100:
        raise RuntimeError(f"Expected 100 summer patches, found {len(items)}")
    return items


def render(items):
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for season_offset, season, header, season_items in [
        (0, "winter", "15–31 January 2023 · Winter patches", items[:100]),
        (100, "summer", "June 2023 · Summer patches", items[100:]),
    ]:
        for page in range(5):
            batch = season_items[page * 20:(page + 1) * 20]
            fig, axes = plt.subplots(4, 5, figsize=(17, 13), layout="constrained")
            fig.suptitle(f"{header}  |  Review sheet {page + 1} of 5", fontsize=19, fontweight="bold")
            image = None
            for local_i, (ax, (path, meta, _)) in enumerate(zip(axes.flat, batch), start=1):
                with np.load(path, allow_pickle=False) as z:
                    pid = str(z["patch_id"].item())
                    rain = np.asarray(z["R_gt"], dtype=np.float32)
                    spacing = float(z["pixel_size_m"]) / 1000
                if pid != path.stem.removeprefix("gt_") or not np.isfinite(rain).all():
                    raise ValueError(f"Invalid ground-truth field in {path}")
                width, height = rain.shape[1] * spacing, rain.shape[0] * spacing
                if "width_km" in meta and (not np.isclose(width, meta["width_km"]) or not np.isclose(height, meta["height_km"])):
                    raise ValueError(f"Shape/metadata mismatch for {pid}")
                global_no = season_offset + page * 20 + local_i
                timestamp = meta["timestamp"]
                city = meta["nearest_city"]
                peak = float(rain.max())
                image = ax.imshow(rain, cmap="turbo", vmin=0, vmax=30,
                                  extent=[0, width, height, 0], interpolation="nearest")
                ax.set_title(f"{global_no:03d} · {timestamp[5:16]} · {pid.rsplit('_', 1)[-1]}\n{city} · max {peak:.1f} mm/h", fontsize=8.5)
                ax.set_xlabel("km", fontsize=7)
                ax.set_ylabel("km", fontsize=7)
                ax.tick_params(labelsize=6, length=2)
                index.append({"number": global_no, "season": season, "sheet": f"{season}-{page+1:02d}.png",
                              "patch_id": pid, "timestamp": timestamp, "city": city,
                              "max_mm_per_hour": peak, "gt_file": str(path.relative_to(ROOT))})
            fig.colorbar(image, ax=list(axes.flat), label="Hourly rainfall (mm/h)", shrink=.77, pad=.012)
            fig.savefig(OUT / f"{season}-{page + 1:02d}.png", dpi=150)
            plt.close(fig)
    if len(index) != 200 or len({r["patch_id"] for r in index}) != 200:
        raise RuntimeError("Review sheets do not cover 200 unique benchmark patches")
    with (OUT / "patch-index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows(index)
    (OUT / "README.md").write_text("""# 200-patch review sheets

Ten sheets contain 20 ground-truth rainfall maps each in a 4-by-5 grid. The first five sheets show the 100 winter patches (15–31 January 2023), followed by five sheets for the 100 summer patches (June 2023). Each page has a season/date header; panel labels show the overall patch number, timestamp, source patch suffix, nearest city, and maximum rainfall.

Plots use the saved benchmark ground-truth fields at 125 m spacing, with a shared 0–30 mm/h color scale. The accompanying `patch-index.csv` maps every displayed patch to its source NPZ.

Regenerate from the repository root with:

```sh
MPLCONFIGDIR=/private/tmp/rain-review-mpl Patch-Generator/backend/.venv/bin/python output/journal_revision/tools/make_200_patch_review_sheets.py
```
""", encoding="utf-8")
    print(f"Created 10 sheets covering {len(index)} unique patches in {OUT}")


if __name__ == "__main__":
    render(load_winter() + load_summer())
