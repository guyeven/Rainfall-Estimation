# Patch Viewers

This folder contains small visual inspection helpers for patch inputs and generated attenuation files. They are useful for debugging or manually checking individual patches, but they are not part of the maintained batch pipeline in `../../HundredPatches/pipeline/`.

## Scripts

- `view_estimator_input.py`: plots a ground-truth rainfall array from `gt_*.npz` and overlays the links from the matching `est_input_*.json` in the same patch-local coordinate frame. Link colors represent attenuation.
- `view_patch.py`: interactive viewer for a selected patch. It loads patch/link metadata, shows the refined and smoothed rainfall field, overlays links, and lets you click near a link to inspect its attenuation, length, frequency, and polarization.

## Usage

Run these from `Compute-Link-Attenuations/` so imports and relative paths match the rest of the project.

For an already-generated estimator input and ground-truth file:

```bash
python Misc/patch_viewers/view_estimator_input.py \
  --est HundredPatches/est_dir/est_input_<patch_id>.json \
  --gt HundredPatches/gt_dir/gt_<patch_id>.npz
```

For the interactive patch viewer:

```bash
python Misc/patch_viewers/view_patch.py
```

or pass a config file:

```bash
python Misc/patch_viewers/view_patch.py --config /path/to/view_patch_config.json
```

## Status

Treat these as optional manual tools. They are intended for quick inspection and debugging rather than for regenerating the benchmark, solving patches, or rendering the report artifacts.
