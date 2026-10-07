from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cml_attenuation.pipeline_validation import (
    validate_analysis_config,
    validate_batch_solve_config,
)


class PipelineValidationTests(unittest.TestCase):
    def test_valid_batch_config(self) -> None:
        validate_batch_solve_config(
            {
                "input": {"est_dir": "inputs"},
                "solvers": {"idw": {"name": "idw"}},
                "parallel": {"solver_workers": 1, "patch_workers": 2},
            }
        )

    def test_zero_workers_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "parallel.patch_workers"):
            validate_batch_solve_config(
                {
                    "input": {"est_dir": "inputs"},
                    "solvers": [{"name": "idw"}],
                    "parallel": {"patch_workers": 0},
                }
            )

    def test_analysis_requires_solution_directory(self) -> None:
        with self.assertRaisesRegex(ValueError, "sol_dir"):
            validate_analysis_config(
                {
                    "input": {
                        "gt_dir": "gt",
                        "est_input_dir": "est",
                        "solvers": [{"label": "missing"}],
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
