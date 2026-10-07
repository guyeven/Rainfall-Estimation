import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('Compute-Link-Attenuations').resolve()))
from render_analysis_report import render_all_j_behavior_plots, plot_j_behavior_all_patches

p = Path('Compute-Link-Attenuations/June2023HundredPatches/pipeline')
out = p / 'report_june_combined_d3'
base = json.loads((p / 'batch_analyze_output_all_but_roy_dct/stats_report_cache.json').read_text())
payloads = [x for x in base['j_behavior_plots'] if x.get('solver_label') != 'Solver(ILDW)']
del base
added = p / 'batch_analyze_output_june_added_d3'
for name in ('stats_Solver_ILDW__light_shrinkage_report_cache.json', 'stats_Solver_ILDW__no_shrinkage_report_cache.json'):
    c = json.loads((added / name).read_text())
    payloads.extend(c.get('j_behavior_plots', []))
    del c
render_all_j_behavior_plots(payloads, output_dir=out, display_map={}, dpi=150)
roy = []
for f in sorted((p / 'solutions/sol_dir_roy_dct_ildw_outer50').glob('*optinfo.json')):
    c = json.loads(f.read_text())
    roy.append({'iterations': [{'J_native_total': row['objective']} for row in c.get('history', [])]})
plot_j_behavior_all_patches(out / 'images/j_behavior/ILDW-init_Roy_DCT/all_patches.png', title='Objective trace: ILDW-init Roy DCT — all patches (outer iterations)', payloads=roy, dpi=150)
print('Rendered objective summaries including', len(roy), 'Roy DCT patches', flush=True)
