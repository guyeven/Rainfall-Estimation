# Link geometry duplication audit

Audited all 100 `est_input*.json` files in the input directory selected by
`Compute-Link-Attenuations/HundredPatches/pipeline/analyze.yaml`.
No pipeline inputs or analysis settings were changed.

## Exhaustive geometry inventory

Grouping uses exact unordered endpoint-coordinate pairs in each patch, ignoring
frequency. Totals count path occurrences across patches, not globally unique paths.

- 132,420 link records, representing 73,091 distinct endpoint-defined paths.
- 59,329 paths occur twice, always with endpoints exactly reversed.
- 13,762 paths occur once. Every patch contains singleton paths.
- No path occurs more than twice.
- A supplemental check rounding coordinates to millimetres gave identical counts.
- All 59,329 reversed pairs have different carrier frequencies. These are duplicate
  geometries, not necessarily duplicate measurements.

The importer `Links-4TU-NL/read-links.py` deduplicates using ordered endpoints.
The distance calculation in `batch_analyze_multi.py` removes repeated sample hits
on the same record index but does not merge reversed geometric paths.

## Numerical distance check

The reproducible `audit.py` samples 4,096 pixel centers without replacement per
patch (seed 20260913), for 409,600 sampled centers. It computes exact distances to
every endpoint-defined segment, including zero-length segments as points, then
compares the third record distance with distinct-path distances. Equality tolerance
is 1e-6 m. This checks the underlying geometric order statistic; it does not rerun
or validate the production KD-tree candidate approximation.

- 392,673 centers (95.87%): third-record distance equals second-distinct-path distance.
- Remaining 16,927 centers (4.13%): it is larger, and equals third-distinct-path distance.
- Second-path equality ranges from 93.41% to 97.39% across individual patches.

Distance ties mean the second- and third-distinct-path distances can both equal
the third-record distance. Accordingly, the two equality counters in `summary.json`
overlap; they must not be summed as mutually exclusive categories.

One counterexample is row 25, column 227 (zero-based) of
`est_input_RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301180600_patch000.json`:
second-distinct-path distance 137.37 m, third-record/third-distinct-path distance
453.73 m.

## Interpretation

The universal identity d3(records) = d2(distinct paths) is false for these inputs.
However, with at most two records per path, rank three is the smallest record rank
guaranteed to require at least two distinct endpoint-defined paths within its radius.
Rank two can still be supplied entirely by the two directions of one path.

This supports interpreting d3 as a local coverage measure that looks beyond a
single path. It does not establish independent measurement information, angular
diversity, or identifiability of the rainfall field. It also does not prove the
historical intent behind choosing k=3.

Run `audit.py` with Python and NumPy. It writes `per_patch.csv` and `summary.json`.
