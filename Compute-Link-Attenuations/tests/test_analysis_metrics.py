from __future__ import annotations

import unittest
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cml_attenuation.analysis_metrics import (
    absolute_difference_summary,
    attenuation_error_per_km,
    attenuation_l1_and_legacy_j1,
    distribution_stats,
    pixel_errors,
)


class PixelMetricTests(unittest.TestCase):
    def test_rainy_errors_are_relative_and_dry_errors_are_absolute(self) -> None:
        ground_truth = np.array([[10.0, 0.0], [20.0, 0.0]])
        prediction = np.array([[8.0, 2.0], [30.0, 0.5]])
        rainy = ground_truth > 0.0

        signed_rainy, absolute_rainy, signed_dry, absolute_dry = pixel_errors(
            ground_truth, prediction, rainy
        )

        np.testing.assert_allclose(signed_rainy, [0.2, -0.5])
        np.testing.assert_allclose(absolute_rainy, [0.2, 0.5])
        np.testing.assert_allclose(signed_dry, [2.0, 0.5])
        np.testing.assert_allclose(absolute_dry, [2.0, 0.5])

    def test_shape_mismatch_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pixel_errors(np.zeros((2, 2)), np.zeros((4,)), np.zeros((2, 2), dtype=bool))

    def test_distribution_columns_remain_stable(self) -> None:
        row = distribution_stats(
            np.array([-1.0, 1.0]),
            np.array([1.0, 1.0]),
            l1_rae_sum=2.0,
            l1_abs_mmph_sum=4.0,
        )
        self.assertEqual(row["n_pixels"], 2)
        self.assertEqual(row["mean_signed"], 0.0)
        self.assertEqual(row["linf_abs"], 1.0)
        self.assertEqual(row["l1_abs_mmph_sum"], 4.0)


class LinkMetricTests(unittest.TestCase):
    def test_link_metrics_have_explicit_length_semantics(self) -> None:
        observed = np.array([1.0, 3.0, 100.0])
        predicted = np.array([3.0, 7.0, -100.0])
        lengths = np.array([2.0, 4.0, 0.0])
        mask = np.array([True, True, False])

        attenuation_l1, legacy_j1, count = attenuation_l1_and_legacy_j1(
            observed, predicted, lengths, mask
        )
        mean_per_link, weighted = attenuation_error_per_km(
            observed, predicted, lengths, mask
        )

        self.assertEqual((attenuation_l1, legacy_j1, count), (6.0, 2.0, 2))
        self.assertEqual(mean_per_link, 1.0)
        self.assertEqual(weighted, 1.0)
        maximum, p95, p99 = absolute_difference_summary(observed, predicted, mask)
        self.assertEqual(maximum, 4.0)
        self.assertGreaterEqual(p99, p95)

    def test_selected_zero_length_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            attenuation_error_per_km(
                np.array([0.0]), np.array([1.0]), np.array([0.0]), np.array([True])
            )


if __name__ == "__main__":
    unittest.main()
