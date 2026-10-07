# June 2023 convective-looking rainfall patches

Use `selected-108.june2023.jsonl` as the final patch list. Each row uses the
Rain Patch Explorer export schema: source HDF5 path, timestamp, inclusive
pixel bounds, rainfall statistics, dimensions, centre coordinates and city.
Source paths are relative to the repository root. No rainfall data are copied
into the JSONL: the referenced crop can be extracted from its original HDF5.

The original 289 candidates occupy 123 distinct hours. They cannot all satisfy
the pairwise requirements. The final 108 have unique timestamps at least four
hours apart, and every pair of patch centres is at least 75 km apart (minimum
75.03 km). This is centre separation, not a 75 km gap between rectangle edges.

Detection sampled 180 maps at 00, 04, 08, 12, 16 and 20 hours on every June day.
It used a 4-by-4 uniform filter, a 3 mm hourly accumulation threshold,
8-connected regions and rectangular dimensions of 50–94 km. Candidate
screening required a raw maximum of at least 15 mm, at least 0.5% of pixels
at 10 mm or higher, coefficient of variation at least 0.8 and no more than
85% of pixels at 1 mm or higher. Crops with more than 1% negative/missing
values were rejected. These are practical selection heuristics, not a
meteorological classification of convection.

All selected images were visually reviewed for concentrated cores and spatial
variation. Obvious speckle/seam patterns and some diffuse cases were excluded;
values above 150 mm/hour were also excluded conservatively. Convective strength
varies, and hourly accumulations alone cannot establish storm type.

An integer optimization selected the maximum possible number from this
review-filtered candidate pool under the spacing rules: 108. Among subsets
of that size, it maximized the screening score. This is not a claim that 108
is the maximum across every hour or every possible crop in June.

`review-01.png` through `review-06.png` show the final selection, in JSONL
order. The colour scale saturates at 30 mm/hour; titles report actual maxima.
`selection-audit.jsonl` includes the numerical screening measurements.
`candidates.jsonl` retains the unfiltered 289-candidate pool for inspection.
`validation.json` records the pairwise checks. Every final crop was reopened
from its source file and its dimensions and rainfall statistics verified.
The older `selected-100.june2023.jsonl` is an intermediate selection.

Reproduce from the repository root using the existing backend environment:

```sh
MPLCONFIGDIR=/private/tmp/rain-june-mpl Patch-Generator/backend/.venv/bin/python Patch-Generator/Tools/select_june_convective.py --max-count
```

Add `--reuse-candidates` to reuse the saved numerical candidate pool.
