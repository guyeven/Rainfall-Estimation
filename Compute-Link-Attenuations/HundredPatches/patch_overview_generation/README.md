# Patch Overview Generation

This folder groups helper inputs for generating patch-overview maps and summaries for the 100-patch benchmark.

## Contents

- `patch_jsonl_files/`: per-patch JSONL geometry files used by overview/map-generation helpers.
- `make_hundredpatches_europe_svg.py`: writes the patch-footprint SVG overview.
- `make_hundredpatches_europe_map_html.py`: writes an interactive HTML map of the selected patches.
- `make_hundredpatches_europe_basemap.py`: writes the basemap-backed PNG/PDF overview used by the report artifacts.

These files sit upstream of the maintained pipeline in `../pipeline/`: they describe benchmark patch geometry and are useful for visualization and inspection, but the solver and report workflow itself is configured from `../pipeline/`.

## Running

Run the overview helpers from this directory:

```bash
cd Compute-Link-Attenuations/HundredPatches/patch_overview_generation
python make_hundredpatches_europe_svg.py
python make_hundredpatches_europe_map_html.py
python make_hundredpatches_europe_basemap.py
```

The SVG and HTML helpers use only the standard library. The basemap helper also requires `geopandas`, `contextily`, `matplotlib`, and `shapely`.
