# Attribution and Data Sources (case studies)

Copyright © 2026 Iván Soto and Guy Even.

This directory follows the terms of the repository root
[`ATTRIBUTION.md`](../../../ATTRIBUTION.md). The scripts in `scripts/` are
licensed under the MIT License. The benchmark inputs, solver outputs,
`objective_values.json` and the figures are licensed under CC BY 4.0, to the
extent that the repository contributors hold or control the relevant rights.
Third-party material keeps its upstream terms, as listed below.

When reusing these files, cite the data sources below as well as this
repository.

## EURADCLIM radar-derived precipitation data

- **Used for**: the ground-truth rainfall fields in `*/inputs/gt_*.npz` and the simulated attenuations in `*/inputs/est_input_*.json`. Every solver output and figure in this directory is derived from them.
- **Creator(s)** (DataCite record): Overeem, Aart. Leijnse, Hidde. van den Besselaar, Else. van der Schrier, Gerard. Meirink, Jan Fokke.
- **Title**: *EURADCLIM: The European climatological gauge-adjusted radar precipitation dataset (1-h accumulations)*.
- **Version**: 3.0.
- **Publisher**: KNMI Radar Team, Royal Netherlands Meteorological Institute (KNMI), 2025.
- **Dataset DOI**: <https://doi.org/10.21944/1rxx-ev62>.
- **Source files**: `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202306120300` (Case I) and `RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301252200` (Case II).
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.
- **Upstream attribution note**: Based on EUMETNET/OPERA radar data and ECA&D rain-gauge data.

### Acknowledgement and reference

We acknowledge the EURADCLIM dataset, the data providers in the ECA&D
project (<https://www.ecad.eu>), and the National Meteorological and
Hydrological Services that provided radar data to the EUMETNET (European
Meteorological Network) program OPERA (Operational Program on the Exchange of
Weather Radar Information).

Overeem, A., van den Besselaar, E., van der Schrier, G., Meirink, J. F., van
der Plas, E., and Leijnse, H.: *EURADCLIM: The European climatological
high-resolution gauge-adjusted radar precipitation dataset*, Earth Syst. Sci.
Data, 15, 1441–1464, <https://doi.org/10.5194/essd-15-1441-2023>, 2023.

### Changes made

Each case uses one patch cropped from one hourly EURADCLIM field. The native
grid of about 2 km was refined to 125 m and smoothed. The result is stored as
the ground-truth array `R_gt`. Rain-induced link attenuations were simulated
from this array. The solver outputs are reconstructions of the field from
those simulated attenuations. They are not EURADCLIM data.

## 4TU commercial microwave-link data

- **Used for**: the link geometry and frequencies in `*/inputs/est_input_*.json`.
- **Creator(s)**: Overeem, Aart. Walraven, Bas. Leijnse, Hidde. Uijlenhoet, Remko.
- **Title**: *Four-year commercial microwave link dataset for the Netherlands*.
- **Version**: 1.
- **Repository**: 4TU.ResearchData, 2024.
- **Dataset DOI**: <https://doi.org/10.4121/be252844-b672-471e-8d69-27269a862ec1.v1>.
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.

### Changes made

The link geometries and frequencies of the Dutch network were placed into the
coordinate system of each patch. Only the links with endpoints inside the
patch were kept. The attenuations in the input files were simulated from the
EURADCLIM-derived field. They are not the measured 4TU attenuations.

## OpenStreetMap map tiles

- **Used for**: the map panel of each case (`*/figures/map_case*.png` and the left panel of `*/figures/RAD_OPERA_*.png`), drawn from the zoom-7 tiles in `osm_tiles_z7/`.
- **Credit**: Map data © OpenStreetMap contributors.
- **License**: the OpenStreetMap data are available under the Open Database License (ODbL). See <https://www.openstreetmap.org/copyright>.
- **Tile source**: `https://tile.openstreetmap.org/7/{x}/{y}.png`, downloaded on 2026-11-12. Use of this server is subject to the OSMF Tile Usage Policy, <https://operations.osmfoundation.org/policies/tiles/>.

### Changes made

The tiles were stitched, cropped to the patch bounding box enlarged by four
times its width and height on each side, and the patch was outlined in red.

## No endorsement

Use of the names 4TU.ResearchData, KNMI, EURADCLIM, EUMETNET/OPERA, ECA&D,
OpenStreetMap, or any associated creator names is for attribution only. It
does not imply endorsement of this repository, these case-study files, the
solver implementations, or the conclusions drawn from them by the original
data providers or creators.
