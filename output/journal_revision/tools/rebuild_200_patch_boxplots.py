#!/usr/bin/env python3
"""Rebuild the journal's rainy and non-rainy d3 box plots from 200 patches."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[3]
COMPUTE = ROOT / "Compute-Link-Attenuations"
ASSETS = Path(__file__).resolve().parents[1] / "images"
WINTER_CACHE = COMPUTE / "HundredPatches/pipeline/batch_analyze_output/stats_report_cache.json"
SUMMER_CACHE = COMPUTE / "June2023HundredPatches/pipeline/batch_analyze_output_all_but_roy_dct/stats_report_cache.json"
GT_SUMMER_CACHE = Path("/private/tmp/rain200_solvergt/stats_report_cache.json")

sys.path.insert(0, str(COMPUTE))
from render_analysis_report import (  # noqa: E402
    build_bin_tick_labels,
    ensure_label_present,
    filter_bins_by_zero_fraction,
    merge_distance_tail_bin,
    plot_box_whisker,
)


METHOD_MAP = [
    ("IDW", "IDW", "IDW"),
    ("ILDW", "ILDW", "ILDW"),
    ("Solver(ILDW)", "OPT_NORM_ILDW_MULT_ILDW_INIT_LIGHT_JTOTAL_LONG", "Solver(ILDW)"),
    ("Convex Solver", "OPT_NORM_VIRTUAL_CONVEX_CONST_INIT_LONG_LIGHT_JTOTAL", "Convex Solver light shrinkage"),
    ("Homotopy Solver", "OPT_NORM_VIRTUAL_HOMOTOPY_CONST_INIT_LONG_LIGHT_JTOTAL", "Homotopy Solver light shrinkage"),
    ("Solver(GT)", "OPT_NORM_ILDW_MULT_GT_INIT_LIGHT_JTOTAL", "Solver(GT)"),
]


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def method_data(cache: dict, name: str, category: str) -> dict:
    return cache["plot_data"][category]["3"][name]


def main() -> None:
    print("Loading winter, summer, and Solver(GT) caches", flush=True)
    winter, summer, gt_summer = map(read, (WINTER_CACHE, SUMMER_CACHE, GT_SUMMER_CACHE))
    print("Loaded caches", flush=True)
    bins = [str(x) for x in winter["labels"]["dist_labels"]]
    if bins != [str(x) for x in summer["labels"]["dist_labels"]] or bins != [str(x) for x in gt_summer["labels"]["dist_labels"]]:
        raise ValueError("Winter and summer distance-bin definitions differ")

    series = {category: {} for category in ("medians_rainy", "medians_nonrainy")}
    for display, winter_name, summer_name in METHOD_MAP:
        source_summer = gt_summer if display == "Solver(GT)" else summer
        for category in series:
            by_bin = {}
            winter_values = method_data(winter, winter_name, category)
            summer_values = method_data(source_summer, summer_name, category)
            for label in bins:
                by_bin[label] = list(winter_values.get(label, [])) + list(summer_values.get(label, []))
            series[category][display] = by_bin

    # Combine bin counts from both seasonal caches for the count annotations.
    counts = {class_name: {} for class_name in ("rainy", "nonrainy")}
    for class_name in counts:
        for label in bins:
            counts[class_name][label] = (
                list(winter["plot_data"]["bin_counts"]["3"][class_name].get(label, []))
                + list(summer["plot_data"]["bin_counts"]["3"][class_name].get(label, []))
            )
    labels_by_kind = {}
    values_by_kind = {}
    for category, class_name in (("medians_rainy", "rainy"), ("medians_nonrainy", "nonrainy")):
        labels, merged_counts, merged_maps = merge_distance_tail_bin(
            bins,
            counts[class_name],
            series[category],
        )
        values = merged_maps[0]
        labels = filter_bins_by_zero_fraction(labels, merged_counts, zero_frac_threshold=0.5)
        labels = ensure_label_present(labels, r"$(6000,\infty)$")
        labels_by_kind[category] = labels
        values_by_kind[category] = values
        tick_labels = build_bin_tick_labels(labels, merged_counts)
        title, ylabel, filename = (
            ("Distribution of patch-level median RAE over rainy pixels by distance bin",
             "Median rainy-pixel RAE per patch", "distance_iqr_medians_rainy_multi_k3_box_whisker.png")
            if category == "medians_rainy" else
            ("Distribution of patch-level median non-rainy-pixel absolute error by distance bin",
             "Median non-rainy-pixel absolute error per patch", "distance_iqr_medians_nonrainy_multi_k3_box_whisker.png")
        )
        plot_box_whisker(
            ASSETS / "distance_profiles_box_whisker/linear" / filename,
            title,
            values,
            labels,
            [item[0] for item in METHOD_MAP],
            dpi=150,
            bin_spacing=1.35,
            tick_labels=tick_labels,
            x_label="d3 bin(m)",
            y_label=ylabel,
            broken_y=True,
        )
        print(f"Rendered {category}", flush=True)

    payload = {
        "patches": {"winter": 100, "summer": 100},
        "distance_k": 3,
        "distance_bins": bins,
        "plotted_bins": labels_by_kind,
        "method_order": [item[0] for item in METHOD_MAP],
        "values": values_by_kind,
    }
    data_path = ASSETS / "distance_profiles_box_whisker/boxplot_patch_medians_200.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(data_path)
    print(ASSETS / "distance_profiles_box_whisker/linear/distance_iqr_medians_rainy_multi_k3_box_whisker.png")
    print(ASSETS / "distance_profiles_box_whisker/linear/distance_iqr_medians_nonrainy_multi_k3_box_whisker.png")


if __name__ == "__main__":
    main()
