"""Render the minimum-ratio patch in each unit ratio interval as a case study."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from generate_case_ratio_report import (
    FONT_BOLD,
    FONT_REGULAR,
    RAIN_THRESHOLD,
    colorize_error,
    colorize_rain,
    load_font,
    load_metrics,
)
from generate_case_study_202301211900 import fit, panel, text_center, world_pixel


REPO = Path(__file__).resolve().parents[1]
HUNDRED = REPO / "Compute-Link-Attenuations" / "HundredPatches"
SOLUTIONS = HUNDRED / "pipeline" / "solutions"
CATALOG = REPO / "Patch-Generator" / "Benchmark-Patches" / "benchmark-500-files-758-patches.local.jan2023.jsonl"
TILE_ROOT = REPO / "Latex" / "figures" / "osm_tiles_ratio_bins"
OUTPUT_DIR = REPO / "output" / "journal_revision" / "images" / "case_studies" / "ratio_bins_minimum"
CONTACT_SHEET = REPO / "Latex" / "figures" / "smallest_ratio_patch_each_interval_contact_sheet.png"
ZOOM = 6

LOCATION_LABELS = {
    "202301301000_patch000": "Southeastern Latvia",
    "202301292300_patch001": "Western Latvia",
    "202301241700_patch000": "Vestland coast, Norway",
    "202301260000_patch000": "Northern Sardinia, Italy",
    "202301272100_patch001": "Western Black Sea, off Bulgaria",
    "202301190300_patch001": "Bay of Biscay, off southwestern France",
    "202301242200_patch001": "Gulf of Lion, western Mediterranean",
    "202301250200_patch001": "Friuli-Venezia Giulia, northeastern Italy",
    "202301210800_patch002": "Northwestern Sardinia, Italy",
    "202301281000_patch001": "Mediterranean Sea, south of Provence",
    "202301222100_patch000": "Bukovina, northeastern Romania",
    "202301270700_patch000": "Bay of Biscay, off the Basque coast",
}


def load_catalog() -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    with CATALOG.open() as handle:
        for line in handle:
            record = json.loads(line)
            records[str(record["id"])] = record
    return records


def select_rows() -> list[dict[str, object]]:
    rows = load_metrics()
    selected = []
    for lower in range(12):
        candidates = [row for row in rows if lower <= float(row["ratio"]) < lower + 1]
        if candidates:
            row = dict(min(candidates, key=lambda item: float(item["ratio"])))
            row["bin_lower"] = lower
            selected.append(row)
    return selected


def patch_view(meta: dict[str, object]) -> dict[str, float]:
    lat = float(meta["center_lat"])
    lon = float(meta["center_lon"])
    width_km = float(meta["width_km"])
    height_km = float(meta["height_km"])
    half_h = (height_km / 2.0) / 111.32
    half_w = (width_km / 2.0) / (111.32 * max(1e-6, math.cos(math.radians(lat))))
    lon_min = lon - half_w
    lon_max = lon + half_w
    lat_min = lat - half_h
    lat_max = lat + half_h
    return {
        "patch_lon_min": lon_min,
        "patch_lon_max": lon_max,
        "patch_lat_min": lat_min,
        "patch_lat_max": lat_max,
        "view_lon_min": lon_min - 4.0 * (lon_max - lon_min),
        "view_lon_max": lon_max + 4.0 * (lon_max - lon_min),
        "view_lat_min": lat_min - 4.0 * (lat_max - lat_min),
        "view_lat_max": lat_max + 4.0 * (lat_max - lat_min),
    }


def tile_bounds(view: dict[str, float]) -> tuple[int, int, int, int]:
    left, top = world_pixel(view["view_lon_min"], view["view_lat_max"], ZOOM)
    right, bottom = world_pixel(view["view_lon_max"], view["view_lat_min"], ZOOM)
    return (
        math.floor(left / 256),
        math.floor((right - 1e-9) / 256),
        math.floor(top / 256),
        math.floor((bottom - 1e-9) / 256),
    )


def tile_manifest(selected: list[dict[str, object]], catalog: dict[str, dict[str, object]]) -> list[dict[str, str]]:
    entries: dict[tuple[int, int], dict[str, str]] = {}
    for row in selected:
        view = patch_view(catalog[str(row["patch"])])
        x_min, x_max, y_min, y_max = tile_bounds(view)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                path = TILE_ROOT / f"z{ZOOM}" / f"{x}_{y}.png"
                entries[(x, y)] = {
                    "path": str(path),
                    "url": f"https://tile.openstreetmap.org/{ZOOM}/{x}/{y}.png",
                }
    return [entries[key] for key in sorted(entries)]


def render_map(meta: dict[str, object]) -> Image.Image:
    view = patch_view(meta)
    x_min, x_max, y_min, y_max = tile_bounds(view)
    mosaic = Image.new("RGB", ((x_max - x_min + 1) * 256, (y_max - y_min + 1) * 256))
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            tile_path = TILE_ROOT / f"z{ZOOM}" / f"{x}_{y}.png"
            if not tile_path.exists():
                raise FileNotFoundError(f"Missing map tile: {tile_path}")
            tile = Image.open(tile_path).convert("RGB")
            mosaic.paste(tile, ((x - x_min) * 256, (y - y_min) * 256))

    origin_x = x_min * 256
    origin_y = y_min * 256
    left, top = world_pixel(view["view_lon_min"], view["view_lat_max"], ZOOM)
    right, bottom = world_pixel(view["view_lon_max"], view["view_lat_min"], ZOOM)
    map_image = mosaic.crop(
        (
            round(left - origin_x),
            round(top - origin_y),
            round(right - origin_x),
            round(bottom - origin_y),
        )
    )
    patch_left, patch_top = world_pixel(view["patch_lon_min"], view["patch_lat_max"], ZOOM)
    patch_right, patch_bottom = world_pixel(view["patch_lon_max"], view["patch_lat_min"], ZOOM)
    draw = ImageDraw.Draw(map_image)
    draw.rectangle(
        (
            round(patch_left - left),
            round(patch_top - top),
            round(patch_right - left),
            round(patch_bottom - top),
        ),
        outline="#d62828",
        width=4,
    )
    return map_image


def load_solution(directory: str, patch: str) -> np.ndarray:
    path = SOLUTIONS / directory / f"est_input_{patch}_solution.npz"
    return np.load(path)["R_hat"].astype(np.float64)


def event_time(short_patch: str) -> str:
    dt = datetime.strptime(short_patch[:12], "%Y%m%d%H%M")
    return dt.strftime("%d %B %Y, %H:%M UTC")


def render_case(row: dict[str, object], meta: dict[str, object]) -> Path:
    patch = str(row["patch"])
    short_patch = str(row["short_patch"])
    lower = int(row["bin_lower"])
    gt = np.load(HUNDRED / "gt_dir" / f"gt_{patch}.npz")["R_gt"].astype(np.float64)
    idw = load_solution("sol_dir_idw", patch)
    solver_gt = load_solution("sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal", patch)
    convex = load_solution("sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal", patch)
    rainfall = [gt, idw, solver_gt, convex]
    rain_max = max(float(np.nanmax(array)) for array in rainfall)
    rainy = gt >= RAIN_THRESHOLD
    relative_errors = []
    for prediction in (idw, solver_gt, convex):
        rel = np.full_like(gt, np.nan)
        rel[rainy] = (prediction[rainy] - gt[rainy]) / gt[rainy]
        relative_errors.append(rel)
    rel_max = max(float(np.nanmax(np.abs(rel))) for rel in relative_errors)

    canvas = Image.new("RGB", (3600, 1380), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(FONT_BOLD, 36)
    subtitle_font = load_font(FONT_REGULAR, 25)
    panel_title_font = load_font(FONT_BOLD, 25)
    tick_font = load_font(FONT_REGULAR, 20)
    footer_font = load_font(FONT_REGULAR, 19)
    location = LOCATION_LABELS.get(short_patch, "European OPERA domain")

    text_center(
        draw,
        (50, 5, 3550, 52),
        f"Minimum-ratio event in [{lower},{lower + 1}) | {location} | {event_time(short_patch)}",
        title_font,
    )
    text_center(
        draw,
        (50, 52, 3550, 95),
        f"Patch {short_patch} | Ground truth, solver predictions, and signed relative error over rainy pixels",
        subtitle_font,
    )
    text_center(
        draw,
        (50, 91, 3550, 130),
        f"d_Solver(GT) = {float(row['d_solver_gt']):.4f} mm/h | d_Convex = {float(row['d_convex']):.4f} mm/h | ratio = {float(row['ratio']):.4f} (Case {int(row['case'])})",
        subtitle_font,
        fill="#555555",
    )

    map_box = (110, 250, 720, 1180)
    text_center(draw, (map_box[0], map_box[1] - 48, map_box[2], map_box[1]), "Map", panel_title_font)
    map_image, map_x, map_y = fit(render_map(meta), map_box)
    canvas.paste(map_image, (map_x, map_y))
    draw.rectangle((map_x, map_y, map_x + map_image.width, map_y + map_image.height), outline="#444444", width=2)

    panel(
        canvas,
        colorize_rain(gt, rain_max),
        (800, 235, 1440, 1180),
        "Ground Truth",
        rain_max,
        signed=False,
        title_font=panel_title_font,
        tick_font=tick_font,
    )
    top_boxes = [(1510, 145, 2160, 630), (2220, 145, 2870, 630), (2930, 145, 3580, 630)]
    bottom_boxes = [(1510, 700, 2160, 1190), (2220, 700, 2870, 1190), (2930, 700, 3580, 1190)]
    for name, prediction, box in zip(("IDW", "Solver(GT)", "Convex Solver"), (idw, solver_gt, convex), top_boxes):
        panel(canvas, colorize_rain(prediction, rain_max), box, name, rain_max, signed=False, title_font=panel_title_font, tick_font=tick_font)
    error_title = "(predicted - observed)/observed\nrainy pixels only; gray = non-rainy"
    for rel, box in zip(relative_errors, bottom_boxes):
        panel(canvas, colorize_error(rel, rel_max), box, error_title, rel_max, signed=True, title_font=subtitle_font, tick_font=tick_font)

    draw.text((85, 1340), "Rainfall data: EURADCLIM, derived from OPERA radar composites.", font=footer_font, fill="#555555", anchor="lm")
    draw.text((3515, 1340), "Map data © OpenStreetMap contributors", font=footer_font, fill="#555555", anchor="rm")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / f"ratio_{lower:02d}_{lower + 1:02d}_{patch}.png"
    canvas.save(output, dpi=(200, 200), optimize=True)
    return output


def make_contact_sheet(paths: list[Path]) -> None:
    thumb_width = 1700
    thumb_height = round(1380 * thumb_width / 3600)
    gap = 24
    sheet = Image.new("RGB", (thumb_width * 2 + gap * 3, thumb_height * 6 + gap * 7), "white")
    for index, path in enumerate(paths):
        thumb = Image.open(path).convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        col = index % 2
        row = index // 2
        sheet.paste(thumb, (gap + col * (thumb_width + gap), gap + row * (thumb_height + gap)))
    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(CONTACT_SHEET, dpi=(160, 160), optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tile-manifest", action="store_true")
    args = parser.parse_args()
    selected = select_rows()
    catalog = load_catalog()
    if args.tile_manifest:
        print(json.dumps(tile_manifest(selected, catalog)))
        return
    outputs = [render_case(row, catalog[str(row["patch"])]) for row in selected]
    make_contact_sheet(outputs)
    for row, output in zip(selected, outputs):
        lower = int(row["bin_lower"])
        print(f"[{lower},{lower + 1}) {row['short_patch']} q={float(row['ratio']):.10f} -> {output}")
    print(f"Contact sheet -> {CONTACT_SHEET}")


if __name__ == "__main__":
    main()
