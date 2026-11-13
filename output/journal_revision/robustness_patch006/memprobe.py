import sys, time, resource
from pathlib import Path
OUT = Path(__file__).resolve().parent; sys.path.insert(0, str(OUT))
import common as C
from cml_attenuation.ildw_baseline import ildw_field_from_est_input
from cml_attenuation.solvers.solve_rain_lbfgsb import load_est_input_json
r = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
print('after common', round(r()), flush=True)
p = load_est_input_json(C.EST, warn=False); print('after load', round(r()), flush=True)
t = time.time(); g, _ = ildw_field_from_est_input(C.EST, r_max_m=15000.0, power=2.0, eps_m=1.0, default_value=0.0)
print('after ildw', round(r()), round(time.time() - t, 1), flush=True)
