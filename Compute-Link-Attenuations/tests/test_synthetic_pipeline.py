from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cml_attenuation.idw_baseline import (
    idw_field_from_est_input,
    itu838_k_alpha,
    link_rain_from_attenuation,
)


class TinySyntheticPipelineTests(unittest.TestCase):
    def test_uniform_link_attenuation_round_trips_through_idw(self) -> None:
        rain_rate = 10.0
        frequency_ghz = 38.0
        length_km = 2.0
        k, alpha = itu838_k_alpha(frequency_ghz, "H")
        attenuation_db = length_km * float(k[0]) * rain_rate ** float(alpha[0])
        payload = {
            "header": {"H": 1, "W": 2, "pixel_size_m": 1000.0},
            "links": [
                {
                    "x0_m": 0.0,
                    "y0_m": 500.0,
                    "x1_m": 2000.0,
                    "y1_m": 500.0,
                    "A_db": attenuation_db,
                    "freq_ghz": frequency_ghz,
                    "pol": "H",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "est_input_tiny.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            reconstructed, per_link = idw_field_from_est_input(
                input_path,
                r_max_m=5000.0,
                power=2.0,
            )

        np.testing.assert_allclose(per_link, [rain_rate], rtol=1e-12)
        np.testing.assert_allclose(reconstructed, [[rain_rate, rain_rate]], rtol=1e-12)

    def test_nonpositive_attenuation_maps_to_zero_rain(self) -> None:
        value = link_rain_from_attenuation(
            np.array([-1.0]),
            np.array([1.0]),
            np.array([0.1]),
            np.array([1.0]),
        )
        np.testing.assert_array_equal(value, [0.0])


if __name__ == "__main__":
    unittest.main()
