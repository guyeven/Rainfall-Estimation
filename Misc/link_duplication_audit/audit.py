"""Audit unordered endpoint multiplicity and exact distances at sampled pixel centers."""
import collections
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'Compute-Link-Attenuations/HundredPatches/est_dir'
SEED = 20260913
SAMPLES = 4096
TOL_M = 1e-6
rng = np.random.default_rng(SEED)
rows = []
examples = []
for path in sorted(SOURCE.glob('est_input*.json')):
    data = json.loads(path.read_text())
    groups = collections.defaultdict(list)
    links = data['links']
    for link in links:
        a = (link['x0_m'], link['y0_m'])
        b = (link['x1_m'], link['y1_m'])
        groups[tuple(sorted((a, b)))].append(link)
    multiplicities = np.array([len(v) for v in groups.values()])
    reverse_pairs = sum(
        len(v) == 2 and
        (v[0]['x0_m'], v[0]['y0_m'], v[0]['x1_m'], v[0]['y1_m']) ==
        (v[1]['x1_m'], v[1]['y1_m'], v[1]['x0_m'], v[1]['y0_m'])
        for v in groups.values()
    )
    assert set(multiplicities) <= {1, 2}
    assert reverse_pairs == int(np.sum(multiplicities == 2))
    endpoints = np.array(list(groups), dtype=float)
    start, end = endpoints[:, 0], endpoints[:, 1]
    vec = end - start
    norm2 = np.sum(vec * vec, axis=1)
    safe_norm2 = np.where(norm2 > 0, norm2, 1.0)
    h = data['header']
    ids = rng.choice(h['H'] * h['W'], min(SAMPLES, h['H'] * h['W']), replace=False)
    points = np.column_stack(((ids % h['W'] + .5) * h['pixel_size_m'],
                              (ids // h['W'] + .5) * h['pixel_size_m']))
    equal2 = equal3 = both_single = 0
    gaps = []
    for offset in range(0, len(points), 256):
        q = points[offset:offset+256]
        delta = q[:, None, :] - start[None, :, :]
        t = np.clip(np.sum(delta * vec, axis=2) / safe_norm2, 0, 1)
        ds = np.sqrt(np.sum((delta - t[:, :, None] * vec) ** 2, axis=2))
        # Exact distance to EVERY distinct segment; repeat distances by actual
        # record multiplicity to obtain the third-nearest record distance.
        distinct = np.partition(ds, 2, axis=1)[:, :3]
        distinct.sort(axis=1)
        record3 = np.partition(np.repeat(ds, multiplicities, axis=1), 2, axis=1)[:, 2]
        eq2 = np.abs(record3 - distinct[:, 1]) <= TOL_M
        eq3 = np.abs(record3 - distinct[:, 2]) <= TOL_M
        assert np.all(eq2 | eq3)
        nearest = np.argsort(ds, axis=1, kind='stable')[:, :2]
        both_single += int(np.sum(np.all(multiplicities[nearest] == 1, axis=1)))
        equal2 += int(eq2.sum())
        equal3 += int(eq3.sum())
        gaps.extend((record3 - distinct[:, 1]).tolist())
        if len(examples) < 5:
            for i in np.flatnonzero(~eq2)[:5-len(examples)]:
                pixel = int(ids[offset + i])
                examples.append(dict(patch=path.name, row=pixel // h['W'], col=pixel % h['W'],
                                     record_d3_m=float(record3[i]), distinct_d2_m=float(distinct[i, 1]),
                                     distinct_d3_m=float(distinct[i, 2])))
    rows.append(dict(patch=path.name, records=len(links), distinct_paths=len(groups),
                     reversed_pairs=reverse_pairs, singleton_paths=int(np.sum(multiplicities == 1)),
                     sampled_pixels=len(points), d3_equals_distinct_d2=equal2,
                     d3_equals_distinct_d3=equal3, nearest_two_both_singletons=both_single,
                     mean_d3_minus_distinct_d2_m=float(np.mean(gaps)),
                     max_d3_minus_distinct_d2_m=float(np.max(gaps))))

with (OUT / 'per_patch.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
total_keys = ['records', 'distinct_paths', 'reversed_pairs', 'singleton_paths', 'sampled_pixels',
              'd3_equals_distinct_d2', 'd3_equals_distinct_d3', 'nearest_two_both_singletons']
summary = dict(patches=len(rows), seed=SEED, samples_per_patch=SAMPLES, tolerance_m=TOL_M,
               totals={key: sum(r[key] for r in rows) for key in total_keys},
               per_patch_d2_equality_fraction_range=[
                   min(r['d3_equals_distinct_d2']/r['sampled_pixels'] for r in rows),
                   max(r['d3_equals_distinct_d2']/r['sampled_pixels'] for r in rows)],
               counterexamples=examples,
               method='Exact unordered endpoint grouping; exhaustive point-to-segment distances at uniformly sampled pixel centers. This checks mathematical distances, not the production KD-tree candidate approximation.')
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
