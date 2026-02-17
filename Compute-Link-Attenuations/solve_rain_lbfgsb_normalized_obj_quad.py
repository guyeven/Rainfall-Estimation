#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from solve_rain_lbfgsb_normalized_obj_log import solve_lbfgsb_and_save as _solve  # type: ignore


def solve_lbfgsb_and_save(est_input_json: str | Path, **kwargs):
    kwargs = dict(kwargs)
    kwargs["use_linear_j3"] = True
    return _solve(est_input_json, **kwargs)

