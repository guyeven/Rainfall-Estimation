import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C, inputs_lib as IL
from cml_attenuation.ildw_baseline import ildw_field_from_est_input
import numpy as np
IL.CACHE.mkdir(exist_ok=True)
jobs = [('none', 0)] + [('N1', s) for s in range(5)] + [('N2const', 0)] + [('N2', s) for s in range(5)]
for m, s in jobs:
    p = IL.write_input(m, s)
    t = time.time()
    g, _ = ildw_field_from_est_input(Path(p), **IL.ILDW_KW)
    np.save(IL.CACHE / f'{p.stem}.npy', np.asarray(g))
    (IL.CACHE / f'{p.stem}.json').write_text(json.dumps({'sha256': IL.sha(p), 'kw': IL.ILDW_KW, 'dtype': str(np.asarray(g).dtype)}))
    print(m, s, p.name, round(time.time() - t, 1), flush=True)
print('ILDWDONE')
