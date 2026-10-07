from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


COMPUTE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = COMPUTE_ROOT.parent
sys.path.insert(0, str(COMPUTE_ROOT))

import batch_analyze_multi
import batch_solve_multi
from cml_attenuation.solvers.solve_rain_lbfgsb_normalized_ildw_multipliers_virtual_homotopy import (
    _beta_schedule,
)


class HomotopyScheduleTests(unittest.TestCase):
    def test_decimal_schedule_has_one_exact_final_stage(self) -> None:
        schedule = _beta_schedule(0.1)

        self.assertEqual(len(schedule), 11)
        self.assertEqual(schedule[-1], 1.0)
        self.assertEqual(sum(np.isclose(beta, 1.0) for beta in schedule), 1)
        self.assertTrue(all(left < right for left, right in zip(schedule, schedule[1:])))

    def test_non_divisor_delta_still_ends_at_one(self) -> None:
        self.assertEqual(_beta_schedule(0.3), [0.0, 0.3, 0.6, 0.8999999999999999, 1.0])

    def test_invalid_delta_is_rejected(self) -> None:
        for delta in (0.0, -0.1, float("nan"), float("inf")):
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    _beta_schedule(delta)


class BatchRunnerTests(unittest.TestCase):
    def test_duplicate_stems_are_detected(self) -> None:
        paths = [
            Path("first/est_input_same.json"),
            Path("second/est_input_same.json"),
            Path("second/est_input_unique.json"),
        ]

        duplicates = batch_solve_multi.duplicate_input_stems(paths)

        self.assertEqual(set(duplicates), {"est_input_same"})
        self.assertEqual(duplicates["est_input_same"], paths[:2])

    def test_main_returns_failure_when_a_patch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "inputs"
            input_dir.mkdir()
            (input_dir / "est_input_one.json").write_text("{}", encoding="utf-8")
            config_path = tmp_path / "config.yaml"
            config = {
                "input": {
                    "est_dir": str(input_dir),
                    "file_pattern": "est_input_*.json",
                    "recursive": False,
                },
                "solvers": [{"name": "test_solver"}],
                "parallel": {"solver_workers": 1, "patch_workers": 1},
            }

            with (
                mock.patch.object(batch_solve_multi, "load_config_file", return_value=config),
                mock.patch.object(
                    batch_solve_multi,
                    "run_solver_batch",
                    return_value=("test_solver", 1, 1),
                ),
                mock.patch.object(sys, "argv", ["batch_solve_multi.py", "--config", str(config_path)]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                status = batch_solve_multi.main()

        self.assertEqual(status, 1)


class AnalysisDefinitionTests(unittest.TestCase):
    def test_exported_j_atten_definition_uses_one_length_factor(self) -> None:
        rows = batch_analyze_multi.append_native_objective_definition_rows([])
        definition = next(row["definition"] for row in rows if row.get("solver") == "J_atten")

        self.assertIn("(A_hat - A_obs)^2/L_km", definition)
        self.assertNotIn("((A_hat - A_obs)/L_km)^2", definition)

    def test_paired_analysis_resolves_repo_and_uses_absolute_bias(self) -> None:
        script_path = REPO_ROOT / "Misc/paired_solver_analysis/build_paired_solver_analysis.py"
        spec = importlib.util.spec_from_file_location("paired_solver_analysis_regression", script_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        solver_labels = dict(module.SOLVERS)
        solver_keys = set(solver_labels)
        self.assertEqual(module.ROOT, REPO_ROOT)
        self.assertEqual(module.NOTE_DIR, script_path.parent)
        self.assertIn("OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG", solver_keys)
        self.assertEqual(
            solver_labels["OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG"],
            "Solver(ILDW)",
        )
        self.assertNotIn("OPT_NORM_ILDW_MULT_ILDW_INIT", solver_keys)
        self.assertEqual(module.METRICS["abs_bias_mmph"], "Absolute Bias")
        self.assertNotIn("bias_mmph", module.METRICS)


if __name__ == "__main__":
    unittest.main()
