"""Render the 100 saved benchmark ground-truth fields as labeled 4x5 sheets."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE.parent
ROOT = BENCHMARK.parents[1]


def main():
    metadata_path = ROOT / 'Patch-Generator/Benchmark-Patches/benchmark-500-files-758-patches.local.jan2023.jsonl'
    metadata = {r['id']: r for r in map(json.loads, metadata_path.read_text().splitlines()) if r}
    paths = sorted((BENCHMARK / 'gt_dir').glob('gt_*.npz'))
    assert len(paths) == 100, f'Expected 100 patches, found {len(paths)}'
    out = BENCHMARK / 'review-sheets'
    out.mkdir(exist_ok=True)
    rows = []
    for start in range(0, len(paths), 20):
        fig, axes = plt.subplots(4, 5, figsize=(15, 12), layout='constrained')
        for number, (ax, path) in enumerate(zip(axes.flat, paths[start:start+20]), start+1):
            with np.load(path, allow_pickle=False) as z:
                pid = str(z['patch_id'].item())
                rain = z['R_gt']
                spacing = float(z['pixel_size_m']) / 1000
                assert pid == path.stem.removeprefix('gt_')
                assert np.isfinite(rain).all()
                height, width = np.array(rain.shape) * spacing
            meta = metadata[pid]
            assert np.isclose(width, meta['width_km']) and np.isclose(height, meta['height_km'])
            peak = float(rain.max())
            im = ax.imshow(rain, cmap='turbo', vmin=0, vmax=30, extent=[0, width, height, 0], interpolation='nearest')
            ax.set_title(f'{number:03d} {meta["timestamp"][5:16]} {pid.rsplit("_", 1)[-1]}\n{meta["nearest_city"]} max {peak:.0f}', fontsize=9)
            rows.append(dict(number=number, sheet=f'review-{start//20+1:02d}.png', patch_id=pid, timestamp=meta['timestamp'], city=meta['nearest_city'], max_mm_per_hour=peak, gt_file=str(path.relative_to(ROOT))))
        fig.colorbar(im, ax=list(axes.flat), label='Hourly rainfall (mm)', shrink=.7)
        fig.savefig(out / f'review-{start//20+1:02d}.png', dpi=120)
        plt.close(fig)
    assert len({row['patch_id'] for row in rows}) == 100
    with (out / 'patch-index.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / 'README.md').write_text('''# HundredPatches review sheets

Five sheets, each with four rows and five columns, cover all 100 patches in chronological filename order. Labels include review number, timestamp, source patch suffix, nearest city, and actual maximum rainfall. Axes are kilometres, with the north/top edge at y=0.

Plots use the saved `gt_dir` ground-truth fields (125 m refinement and Gaussian smoothing), which are the benchmark inputs. The shared turbo color scale is 0–30 mm/hour, matching the greedy review sheets; values above 30 saturate. `patch-index.csv` maps each review number to the full patch ID and source NPZ.

Regenerate from the repository root:

```sh
MPLCONFIGDIR=/private/tmp/rain-review-mpl Patch-Generator/backend/.venv/bin/python Compute-Link-Attenuations/HundredPatches/patch_overview_generation/make_review_sheets.py
```
''')
    print(f'Created {len(rows)} labeled panels in {out}')


if __name__ == '__main__':
    main()
