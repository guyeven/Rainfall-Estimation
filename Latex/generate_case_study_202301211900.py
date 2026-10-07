"""Render patch 202301211900_patch000 in the appendix case-study layout."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from generate_case_ratio_report import (
    DIVERGING,
    FONT_BOLD,
    FONT_REGULAR,
    RAIN_THRESHOLD,
    VIRIDIS,
    colorize_error,
    colorize_rain,
    load_font,
)


REPO = Path(__file__).resolve().parents[1]
PATCH = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_202301211900_patch000"
SHORT_PATCH = "202301211900_patch000"
LOCATION = "Western Herzegovina, Bosnia and Herzegovina"
EVENT_TIME = "21 January 2023, 19:00 UTC"
CENTER_LAT = 43.468383007011475
CENTER_LON = 17.43439237681499
WIDTH_KM = 58.0
HEIGHT_KM = 82.0
ZOOM = 7
TILE_X = range(69, 72)
TILE_Y = range(45, 49)

HUNDRED = REPO / "Compute-Link-Attenuations" / "HundredPatches"
SOLUTIONS = HUNDRED / "pipeline" / "solutions"
TILE_DIR = REPO / "Latex" / "figures" / "osm_tiles_z7"
OUTPUT = (
    REPO
    / "output"
    / "journal_revision"
    / "images"
    / "case_studies"
    / "new_pattern_one"
    / f"{PATCH}.png"
)


def load_npz(path: Path, key: str) -> np.ndarray:
    return np.load(path)[key].astype(np.float64)


def world_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    scale = 256.0 * (2**zoom)
    x = scale * (lon + 180.0) / 360.0
    lat_rad = math.radians(lat)
    y = scale * (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0
    return x, y


def make_map() -> Image.Image:
    tile_size = 256
    x_values = list(TILE_X)
    y_values = list(TILE_Y)
    mosaic = Image.new("RGB", (len(x_values) * tile_size, len(y_values) * tile_size))
    for col, x in enumerate(x_values):
        for row, y in enumerate(y_values):
            tile = Image.open(TILE_DIR / f"{x}_{y}.png").convert("RGB")
            mosaic.paste(tile, (col * tile_size, row * tile_size))

    half_h_deg = (HEIGHT_KM / 2.0) / 111.32
    half_w_deg = (WIDTH_KM / 2.0) / (111.32 * math.cos(math.radians(CENTER_LAT)))
    patch_lon_min = CENTER_LON - half_w_deg
    patch_lon_max = CENTER_LON + half_w_deg
    patch_lat_min = CENTER_LAT - half_h_deg
    patch_lat_max = CENTER_LAT + half_h_deg

    # Match the appendix maps: the visible context extends four patch widths/heights
    # beyond the red patch footprint on each side.
    lon_pad = 4.0 * (patch_lon_max - patch_lon_min)
    lat_pad = 4.0 * (patch_lat_max - patch_lat_min)
    view_lon_min = patch_lon_min - lon_pad
    view_lon_max = patch_lon_max + lon_pad
    view_lat_min = patch_lat_min - lat_pad
    view_lat_max = patch_lat_max + lat_pad

    world_origin_x = min(x_values) * tile_size
    world_origin_y = min(y_values) * tile_size
    left, top = world_pixel(view_lon_min, view_lat_max, ZOOM)
    right, bottom = world_pixel(view_lon_max, view_lat_min, ZOOM)
    crop_box = (
        int(round(left - world_origin_x)),
        int(round(top - world_origin_y)),
        int(round(right - world_origin_x)),
        int(round(bottom - world_origin_y)),
    )
    map_image = mosaic.crop(crop_box)

    px0, py0 = world_pixel(patch_lon_min, patch_lat_max, ZOOM)
    px1, py1 = world_pixel(patch_lon_max, patch_lat_min, ZOOM)
    draw = ImageDraw.Draw(map_image)
    draw.rectangle(
        (
            int(round(px0 - left)),
            int(round(py0 - top)),
            int(round(px1 - left)),
            int(round(py1 - top)),
        ),
        outline="#d62828",
        width=4,
    )
    return map_image


def fit(image: Image.Image, box: tuple[int, int, int, int], *, nearest: bool = False) -> tuple[Image.Image, int, int]:
    x0, y0, x1, y1 = box
    scale = min((x1 - x0) / image.width, (y1 - y0) / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.NEAREST if nearest else Image.Resampling.BILINEAR)
    return resized, x0 + ((x1 - x0) - size[0]) // 2, y0 + ((y1 - y0) - size[1]) // 2


def text_center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill="black") -> None:
    bounds = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=2)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - bounds[1]
    draw.multiline_text((x, y), text, font=font, fill=fill, align="center", spacing=2)


def colorbar(canvas: Image.Image, x: int, y: int, height: int, vmax: float, *, signed: bool, font) -> None:
    width = 22
    lut = DIVERGING if signed else VIRIDIS
    gradient = Image.fromarray(lut[::-1].reshape(256, 1, 3), mode="RGB").resize((width, height))
    canvas.paste(gradient, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((x, y, x + width, y + height), outline="#444444", width=1)
    ticks = [(0.0, vmax), (0.5, 0.0 if signed else vmax / 2.0), (1.0, -vmax if signed else 0.0)]
    for fraction, value in ticks:
        ty = y + round(fraction * height)
        draw.line((x + width, ty, x + width + 7, ty), fill="#333333", width=2)
        label = f"{value:.2f}" if signed else f"{value:.1f}"
        draw.text((x + width + 11, ty), label, font=font, fill="#222222", anchor="lm")


def panel(
    canvas: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
    title: str,
    vmax: float,
    *,
    signed: bool,
    title_font,
    tick_font,
) -> None:
    draw = ImageDraw.Draw(canvas)
    title_box = (box[0], box[1], box[2], box[1] + 48)
    text_center(draw, title_box, title, title_font)
    image_box = (box[0], box[1] + 52, box[2] - 58, box[3])
    resized, x, y = fit(image, image_box, nearest=signed)
    canvas.paste(resized, (x, y))
    draw.rectangle((x, y, x + resized.width, y + resized.height), outline="#444444", width=2)
    colorbar(canvas, box[2] - 47, y, resized.height, vmax, signed=signed, font=tick_font)


def main() -> None:
    gt = load_npz(HUNDRED / "gt_dir" / f"gt_{PATCH}.npz", "R_gt")
    idw = load_npz(SOLUTIONS / "sol_dir_idw" / f"est_input_{PATCH}_solution.npz", "R_hat")
    solver_gt = load_npz(
        SOLUTIONS / "sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal" / f"est_input_{PATCH}_solution.npz",
        "R_hat",
    )
    convex = load_npz(
        SOLUTIONS / "sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal" / f"est_input_{PATCH}_solution.npz",
        "R_hat",
    )

    rainfall = [gt, idw, solver_gt, convex]
    rain_max = max(float(np.nanmax(array)) for array in rainfall)
    rainy = gt >= RAIN_THRESHOLD
    relative_errors = []
    for prediction in (idw, solver_gt, convex):
        rel = np.full_like(gt, np.nan)
        rel[rainy] = (prediction[rainy] - gt[rainy]) / gt[rainy]
        relative_errors.append(rel)
    rel_max = max(float(np.nanmax(np.abs(rel))) for rel in relative_errors)

    d_solver_gt = float(np.sqrt(np.mean((solver_gt - gt) ** 2)))
    d_convex = float(np.sqrt(np.mean((convex - gt) ** 2)))
    ratio = d_convex / d_solver_gt

    canvas = Image.new("RGB", (3600, 1380), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(FONT_BOLD, 36)
    subtitle_font = load_font(FONT_REGULAR, 25)
    panel_title_font = load_font(FONT_BOLD, 25)
    tick_font = load_font(FONT_REGULAR, 20)
    footer_font = load_font(FONT_REGULAR, 19)

    text_center(draw, (60, 5, 3540, 52), f"Rain event | {LOCATION} | {EVENT_TIME}", title_font)
    text_center(
        draw,
        (60, 52, 3540, 95),
        f"Patch {SHORT_PATCH} | Ground truth, solver predictions, and signed relative error over rainy pixels",
        subtitle_font,
    )
    text_center(
        draw,
        (60, 91, 3540, 130),
        f"d_Solver(GT) = {d_solver_gt:.4f} mm/h | d_Convex = {d_convex:.4f} mm/h | ratio = {ratio:.4f} (Case 1)",
        subtitle_font,
        fill="#555555",
    )

    # Map and ground truth occupy both rows, as in the appendix case studies.
    map_box = (110, 250, 720, 1180)
    text_center(draw, (map_box[0], map_box[1] - 48, map_box[2], map_box[1]), "Map", panel_title_font)
    map_image, map_x, map_y = fit(make_map(), map_box)
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

    solver_boxes_top = [(1510, 145, 2160, 630), (2220, 145, 2870, 630), (2930, 145, 3580, 630)]
    solver_boxes_bottom = [(1510, 700, 2160, 1190), (2220, 700, 2870, 1190), (2930, 700, 3580, 1190)]
    solver_names = ["IDW", "Solver(GT)", "Convex Solver"]
    for name, prediction, top_box in zip(solver_names, (idw, solver_gt, convex), solver_boxes_top):
        panel(
            canvas,
            colorize_rain(prediction, rain_max),
            top_box,
            name,
            rain_max,
            signed=False,
            title_font=panel_title_font,
            tick_font=tick_font,
        )
    error_title = "(predicted - observed)/observed\nrainy pixels only; gray = non-rainy"
    for rel, bottom_box in zip(relative_errors, solver_boxes_bottom):
        panel(
            canvas,
            colorize_error(rel, rel_max),
            bottom_box,
            error_title,
            rel_max,
            signed=True,
            title_font=subtitle_font,
            tick_font=tick_font,
        )

    draw.text(
        (85, 1340),
        "Rainfall data: EURADCLIM, derived from OPERA radar composites.",
        font=footer_font,
        fill="#555555",
        anchor="lm",
    )
    draw.text(
        (3515, 1340),
        "Map data © OpenStreetMap contributors",
        font=footer_font,
        fill="#555555",
        anchor="rm",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, dpi=(200, 200), optimize=True)
    print(f"Wrote {OUTPUT}")
    print(f"ratio={ratio:.10f}, d_solver_gt={d_solver_gt:.10f}, d_convex={d_convex:.10f}")


if __name__ == "__main__":
    main()
