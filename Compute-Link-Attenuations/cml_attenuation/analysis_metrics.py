"""Pure numerical metrics shared by analysis and regression tests."""

from __future__ import annotations

from typing import Any

import numpy as np


def pixel_errors(
    ground_truth: np.ndarray,
    prediction: np.ndarray,
    rainy_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return signed/absolute rainy-relative and dry-absolute errors."""
    gt = np.asarray(ground_truth, dtype=np.float64)
    pred = np.asarray(prediction, dtype=np.float64)
    rainy = np.asarray(rainy_mask, dtype=bool)
    if gt.shape != pred.shape or gt.shape != rainy.shape:
        raise ValueError("ground truth, prediction, and rainy mask must have equal shapes")

    gt_rainy = gt[rainy]
    pred_rainy = pred[rainy]
    denominator = np.where(gt_rainy == 0.0, 1.0, gt_rainy)
    signed_rainy = (gt_rainy - pred_rainy) / denominator

    gt_dry = gt[~rainy]
    pred_dry = pred[~rainy]
    signed_dry = pred_dry - gt_dry
    return signed_rainy, np.abs(signed_rainy), signed_dry, np.abs(signed_dry)


def distribution_stats(
    signed_error: np.ndarray,
    absolute_error: np.ndarray,
    *,
    l1_rae_sum: float,
    l1_abs_mmph_sum: float,
) -> dict[str, Any]:
    """Summarize an error distribution using the report's stable column names."""
    signed = np.asarray(signed_error, dtype=np.float64)
    absolute = np.asarray(absolute_error, dtype=np.float64)
    if signed.shape != absolute.shape:
        raise ValueError("signed and absolute errors must have equal shapes")
    if absolute.size == 0:
        return {
            "n_pixels": 0,
            "mean_signed": 0.0,
            "median_signed": 0.0,
            "mean_abs": 0.0,
            "std_abs": 0.0,
            "median_abs": 0.0,
            "p90_abs": 0.0,
            "p95_abs": 0.0,
            "p99_abs": 0.0,
            "linf_abs": 0.0,
            "l1_rae_sum": 0.0,
            "l1_abs_mmph_sum": 0.0,
        }
    return {
        "n_pixels": int(absolute.size),
        "mean_signed": float(np.mean(signed)),
        "median_signed": float(np.median(signed)),
        "mean_abs": float(np.mean(absolute)),
        "std_abs": float(np.std(absolute, ddof=0)),
        "median_abs": float(np.median(absolute)),
        "p90_abs": float(np.percentile(absolute, 90)),
        "p95_abs": float(np.percentile(absolute, 95)),
        "p99_abs": float(np.percentile(absolute, 99)),
        "linf_abs": float(np.max(absolute)),
        "l1_rae_sum": float(l1_rae_sum),
        "l1_abs_mmph_sum": float(l1_abs_mmph_sum),
    }


def attenuation_l1_and_legacy_j1(
    observed: np.ndarray,
    predicted: np.ndarray,
    lengths_km: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float, int]:
    """Return attenuation L1 and the retained legacy sum((error/L)^2)."""
    selected = np.flatnonzero(mask)
    if selected.size == 0:
        return 0.0, 0.0, 0
    lengths = np.asarray(lengths_km, dtype=np.float64)[selected]
    if np.any(lengths <= 0.0):
        raise ValueError("selected link lengths must be positive")
    difference = np.asarray(predicted)[selected] - np.asarray(observed)[selected]
    return (
        float(np.sum(np.abs(difference))),
        float(np.sum((difference / lengths) ** 2)),
        int(selected.size),
    )


def attenuation_error_per_km(
    observed: np.ndarray,
    predicted: np.ndarray,
    lengths_km: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float]:
    """Return mean per-link and total-length-weighted absolute error per km."""
    selected = np.flatnonzero(mask)
    if selected.size == 0:
        return 0.0, 0.0
    lengths = np.asarray(lengths_km, dtype=np.float64)[selected]
    if np.any(lengths <= 0.0):
        raise ValueError("selected link lengths must be positive")
    difference = np.abs(np.asarray(predicted)[selected] - np.asarray(observed)[selected])
    return float(np.mean(difference / lengths)), float(np.sum(difference) / np.sum(lengths))


def absolute_difference_summary(
    observed: np.ndarray,
    predicted: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float, float]:
    """Return maximum, 95th percentile, and 99th percentile absolute errors."""
    selected = np.flatnonzero(mask)
    if selected.size == 0:
        return 0.0, 0.0, 0.0
    difference = np.abs(np.asarray(predicted)[selected] - np.asarray(observed)[selected])
    return (
        float(np.max(difference)),
        float(np.percentile(difference, 95)),
        float(np.percentile(difference, 99)),
    )
