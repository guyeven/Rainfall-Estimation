import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('Compute-Link-Attenuations').resolve()))
import render_analysis_report as r

cache = json.loads(Path('tmp/june_d3_slim_cache.json').read_text())
out = Path('Compute-Link-Attenuations/June2023HundredPatches/pipeline/report_june_combined_d3/images')
labels = cache['labels']['dist_labels']
requested_order = [
    'IDW',
    'ILDW',
    'Solver(ILDW) light shrinkage',
    'Solver(ILDW) no shrinkage',
    'Convex Solver light shrinkage',
    'Convex Solver no shrinkage',
    'Homotopy Solver light shrinkage',
    'Homotopy Solver no shrinkage',
    'ILDW-init Roy DCT',
]
methods = [x for x in requested_order if x in cache['plot_data']['medians_rainy']['3'] or x == 'Solver(ILDW) light shrinkage']
display = {
    'Solver(ILDW)': 'Solver(ILDW) light shrinkage',
    'Solver(ILDW) light shrinkage': 'Solver(ILDW) light shrinkage',
    'Solver(ILDW) no shrinkage': 'Solver(ILDW) no shrinkage',
    'ILDW-init Roy DCT': 'ILDW-init Roy DCT',
    'Convex Solver light shrinkage': 'Convex Solver light',
    'Homotopy Solver light shrinkage': 'Homotopy Solver light',
}
methods = list(dict.fromkeys(display.get(x, x) for x in methods))
def remap(data):
    return {display.get(k, k): v for k, v in data.items()}

for kind, key, title, ylabel in [
    ('rainy', 'medians_rainy', 'Rainy pixels: d3 distance profile', 'Median rainy-pixel RAE per patch'),
    ('nonrainy', 'medians_nonrainy', 'Non-rainy pixels: d3 distance profile', 'Median non-rainy-pixel absolute error per patch'),
]:
    vals = remap(cache['plot_data'][key]['3'])
    for mode, fn in [('linear', r.plot_box_whisker), ('log', r.plot_box_whisker)]:
        p = out / 'distance_profiles_box_whisker' / mode / 'k3' / f'distance_iqr_medians_{kind}_multi_k3_box_whisker.png'
        fn(p, title + (' (log scale)' if mode == 'log' else ''), vals, labels, methods, dpi=150, x_label='d3 bin(m)', y_label=ylabel, log_scale=(mode == 'log'), broken_y=(mode == 'linear'))

vals = remap(cache['plot_data']['jatten_medians']['3'])
p = out / 'jatten_profiles_box_whisker' / 'distance_iqr_medians_jatten_multi_k3_box_whisker.png'
r.plot_box_whisker(p, 'J-attenuation: d3 profile', vals, cache['labels']['jatten_dist_labels'], [x for x in methods if x in vals], dpi=150, x_label='d3 bin(m)', y_label='J-attenuation median per patch')
print('wrote direct D3 figures for:', ', '.join(methods))
