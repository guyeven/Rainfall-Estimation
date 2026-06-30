# Attribution and Data Sources

This repository is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0):
<https://creativecommons.org/licenses/by/4.0/>.

The workflow uses or derives artifacts from external data sources that are also understood to be distributed under CC BY 4.0. When reusing this repository or generated benchmark artifacts, cite the original data sources as well as this repository.

## 4TU commercial microwave-link data

- **Source**: 4TU.ResearchData commercial microwave-link / RAINLINK data source used in `Links-4TU-NL/`.
- **Creator(s)**: Overeem, Aart.
- **Title**: *Commercial microwave link data for rainfall monitoring*.
- **Version**: 2.
- **Repository**: 4TU.Centre for Research Data.
- **Dataset DOI**: <https://doi.org/10.4121/7a692e36-c32f-4916-813b-c62d2566e8d8.v2>.
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.

### Changes made in this repository

The raw 4TU/RAINLINK link records are converted into JSONL files containing selected link geometry and frequency fields. The maintained 100-patch benchmark does **not** use the original 4TU link measurements as rainfall observations at their original locations. Instead, the 4TU-derived link geometries and frequencies are used as realistic CML network structure: the link network is placed into selected radar-patch coordinate systems, links whose endpoints fall inside each patch are retained, and rain-induced attenuations are simulated from the radar-derived rainfall field.

## EURADCLIM / OPERA radar-derived precipitation data

- **Source**: EURADCLIM / KNMI radar-derived precipitation fields used by `Patch-Generator/` and `Compute-Link-Attenuations/`.
- **Creator(s)**: Overeem, Aart; Leijnse, Hidde; van den Besselaar, Else; van der Schrier, Gerard; Meirink, Jan Fokke.
- **Title**: *EURADCLIM: The European climatological gauge-adjusted radar precipitation dataset (1-h accumulations)*.
- **Version**: 3.0.
- **Repository**: KNMI Radar Team / Royal Netherlands Meteorological Institute (KNMI).
- **Dataset DOI**: <https://doi.org/10.21944/1rxx-ev62>.
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.
- **Required upstream attribution note**: Based on EUMETNET/OPERA radar data and ECA&D rain-gauge data.

### Changes made in this repository

The radar-derived precipitation fields are used to select rainy-event patches and construct benchmark rainfall arrays. The pipeline crops selected event patches, refines the native approximately 2 km grid to a 125 m grid, smooths the refined rainfall field, and uses the resulting arrays as radar-derived ground truth for simulating CML attenuation and evaluating reconstruction methods.

## No endorsement

Use of the names 4TU.ResearchData, KNMI, EURADCLIM, EUMETNET/OPERA, ECA&D, RAINLINK, or any associated creator names is for attribution only. It does not imply endorsement of this repository, the generated benchmark artifacts, the solver implementations, or the conclusions drawn from them by the original data providers or creators.

## Notes for maintainers

The source attribution should remain visible in the root README and travel with any redistributed benchmark artifacts. If the upstream datasets are replaced by different versions, update the creator names, titles, versions, repositories, and DOI links above to match the exact dataset records used.
