# Full-Area d3 Link Plot

This folder contains a standalone visualization helper for building a single full-area map of distance-to-third-closest-link bins from many patch `est_input_*.json` files and overlaying the retained CML links.

This is not part of the maintained 100-patch solver pipeline. It is useful when you want to inspect the spatial coverage of the patch/link geometry across a larger mosaic, especially for debugging or exploratory figures.

## Script

- `plot_fullarea_d3_links.py`: reads patch estimator-input JSON files, computes each pixel's distance to the third-closest link segment inside each patch, merges the per-patch distance maps into one RD-coordinate mosaic, overlays deduplicated links, and writes a PNG.

## Usage

Run from `Compute-Link-Attenuations/` or pass paths relative to the config file location:

```bash
python Misc/fullarea_d3_links/plot_fullarea_d3_links.py --config path/to/config.yaml
```

The config must provide either `input.est_input_glob` or `input.est_input_dir`. Optional settings include distance-bin edges, KD-tree sampling parameters, merge behavior for overlapping patches, and output location. The script defaults to writing `fullarea_d3_bins_with_links.png` under `output.out_dir/images/`.

This script expects the same `est_input_*.json` structure produced by the patch benchmark generation step in the main pipeline.
