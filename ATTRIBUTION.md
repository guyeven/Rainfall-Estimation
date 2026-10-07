# Attribution and Data Sources

Copyright © 2026 Iván Soto and Guy Even.

Unless stated otherwise, original source code and software configuration files
in this repository are licensed under the [MIT License](LICENSE). Original
documentation, figures, reports, thesis material, benchmark inputs, and
solver-output datasets are licensed under [CC BY 4.0](LICENSE-CC-BY-4.0), to
the extent that the repository contributors hold or control the relevant
rights. Third-party code, datasets, and other third-party materials retain
their upstream terms.

The workflow uses or derives artifacts from external data sources distributed
under CC BY 4.0. When reusing generated benchmark artifacts, cite the original
data sources as well as this repository.

## 4TU commercial microwave-link data

- **Source**: 4TU.ResearchData commercial microwave-link / RAINLINK data source used in `Links-4TU-NL/`.
- **Creator(s)**: Overeem, Aart; Walraven, Bas; Leijnse, Hidde; Uijlenhoet, Remko.
- **Title**: *Four-year commercial microwave link dataset for the Netherlands*.
- **Version**: 1.
- **Repository**: 4TU.ResearchData.
- **Dataset DOI**: <https://doi.org/10.4121/be252844-b672-471e-8d69-27269a862ec1.v1>.
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.

### Changes made in this repository

The 4TU CML records are converted into JSONL files containing selected link geometry and frequency fields. The maintained 100-patch benchmark does **not** use the original 4TU link measurements as rainfall observations at their original locations. Instead, the 4TU-derived link geometries and frequencies are used as realistic CML network structure: the link network is placed into selected radar-patch coordinate systems, links whose endpoints fall inside each patch are retained, and rain-induced attenuations are simulated from the radar-derived rainfall field.

The original `RawCMLdata.zip` and `IDRawCMLdata.zip` archives are not
redistributed in this repository because of their size. They can be obtained
from the cited 4TU.ResearchData record. This repository includes only the
processed `unique_links.jsonl` and `LIST-OF-LINKS.jsonl` extracts containing
selected link geometry, length, and frequency fields.

## EURADCLIM radar-derived precipitation data

- **Source**: EURADCLIM radar-derived precipitation fields used by `Patch-Generator/` and `Compute-Link-Attenuations/`.
- **Creator(s)**: Overeem, Aart; van den Besselaar, Else; van der Schrier, Gerard; Meirink, Jan Fokke; van der Plas, Emiel; Leijnse, Hidde.
- **Title**: *EURADCLIM: The European climatological gauge-adjusted radar precipitation dataset (1-h accumulations)*.
- **Version**: 3.0.
- **Repository**: KNMI Radar Team / Royal Netherlands Meteorological Institute (KNMI).
- **Dataset DOI**: <https://doi.org/10.21944/1rxx-ev62>.
- **License**: Creative Commons Attribution 4.0 International, <https://creativecommons.org/licenses/by/4.0/>.
- **Required upstream attribution note**: Based on EUMETNET/OPERA radar data and ECA&D rain-gauge data.

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

This repository includes the hourly EURADCLIM HDF5 rainfall files used
by the benchmark under `Patch-Generator/backend/data/raw/`. Those redistributed
source files remain subject to the upstream CC BY 4.0 license and attribution
requirements, including acknowledgement that the data are based on
EUMETNET/OPERA radar data and ECA&D rain-gauge data.

### Changes made in this repository

The radar-derived precipitation fields are used to select rainy-event patches and construct benchmark rainfall arrays. The pipeline crops selected event patches, refines the native approximately 2 km grid to a 125 m grid, smooths the refined rainfall field, and uses the resulting arrays as radar-derived ground truth for simulating CML attenuation and evaluating reconstruction methods.

## No endorsement

Use of the names 4TU.ResearchData, KNMI, EURADCLIM, EUMETNET/OPERA, ECA&D, RAINLINK, or any associated creator names is for attribution only. It does not imply endorsement of this repository, the generated benchmark artifacts, the solver implementations, or the conclusions drawn from them by the original data providers or creators.

## Notes for maintainers

The source attribution should remain visible in the root README and travel with any redistributed benchmark artifacts. If the upstream datasets are replaced by different versions, update the creator names, titles, versions, repositories, and DOI links above to match the exact dataset records used.
