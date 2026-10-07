"""Generate the case-ratio LaTeX report and its two boundary heatmaps.

Run with the bundled scientific Python runtime, for example:
  /Users/isoto/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
      Latex/generate_case_ratio_report.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO = Path(__file__).resolve().parents[1]
HUNDRED = REPO / "Compute-Link-Attenuations" / "HundredPatches"
LATEX_DIR = REPO / "Latex"
FIGURE_DIR = LATEX_DIR / "figures"
PREFIX = "RAD_OPERA_HOURLY_RAINFALL_ACCUMULATION_"
THRESHOLD = 2.0
RAIN_THRESHOLD = 0.6

SOLVER_GT_DIR = (
    HUNDRED
    / "pipeline"
    / "solutions"
    / "sol_dir_opt_norm_ildw_mult_gt_init_light_jtotal"
)
CONVEX_DIR = (
    HUNDRED
    / "pipeline"
    / "solutions"
    / "sol_dir_opt_norm_virtual_convex_const_init_long_light_jtotal"
)

FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
FONT_MONO = Path("/System/Library/Fonts/Supplemental/Andale Mono.ttf")


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def solution_path(directory: Path, patch: str) -> Path:
    return directory / f"est_input_{patch}_solution.npz"


def load_metrics() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for gt_path in sorted((HUNDRED / "gt_dir").glob("gt_*.npz")):
        patch = gt_path.stem.removeprefix("gt_")
        solver_gt_path = solution_path(SOLVER_GT_DIR, patch)
        convex_path = solution_path(CONVEX_DIR, patch)
        if not solver_gt_path.exists() or not convex_path.exists():
            continue

        gt = np.load(gt_path)["R_gt"].astype(np.float64)
        solver_gt = np.load(solver_gt_path)["R_hat"].astype(np.float64)
        convex = np.load(convex_path)["R_hat"].astype(np.float64)
        d_solver_gt = float(np.sqrt(np.mean((solver_gt - gt) ** 2)))
        d_convex = float(np.sqrt(np.mean((convex - gt) ** 2)))
        ratio = d_convex / d_solver_gt
        rows.append(
            {
                "patch": patch,
                "short_patch": patch.removeprefix(PREFIX),
                "d_solver_gt": d_solver_gt,
                "d_convex": d_convex,
                "ratio": ratio,
                "case": 1 if ratio >= THRESHOLD else 2,
            }
        )
    if len(rows) != 100:
        raise RuntimeError(f"Expected 100 complete patches, found {len(rows)}")
    return rows


def interpolate_lut(stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    positions = np.linspace(0.0, 1.0, 256)
    lut = np.zeros((256, 3), dtype=np.uint8)
    for channel in range(3):
        lut[:, channel] = np.interp(
            positions,
            [position for position, _ in stops],
            [color[channel] for _, color in stops],
        ).round().astype(np.uint8)
    return lut


VIRIDIS = interpolate_lut(
    [
        (0.00, (68, 1, 84)),
        (0.25, (59, 82, 139)),
        (0.50, (33, 145, 140)),
        (0.75, (94, 201, 98)),
        (1.00, (253, 231, 37)),
    ]
)
DIVERGING = interpolate_lut(
    [
        (0.00, (33, 102, 172)),
        (0.50, (247, 247, 247)),
        (1.00, (178, 24, 43)),
    ]
)


def colorize_rain(array: np.ndarray, vmax: float) -> Image.Image:
    scaled = np.clip(np.rint(array / max(vmax, 1e-12) * 255), 0, 255).astype(np.uint8)
    return Image.fromarray(VIRIDIS[scaled], mode="RGB")


def colorize_error(array: np.ndarray, vmax: float) -> Image.Image:
    valid = np.isfinite(array)
    scaled = np.zeros(array.shape, dtype=np.uint8)
    scaled[valid] = np.clip(
        np.rint((np.clip(array[valid] / max(vmax, 1e-12), -1.0, 1.0) + 1.0) * 127.5),
        0,
        255,
    ).astype(np.uint8)
    rgb = DIVERGING[scaled]
    rgb[~valid] = (122, 122, 122)
    return Image.fromarray(rgb, mode="RGB")


def draw_centered(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill=(25, 25, 25)) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(((left + right - width) / 2, (top + bottom - height) / 2), text, font=font, fill=fill)


def add_colorbar(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    lut: np.ndarray,
    x: int,
    y: int,
    height: int,
    vmax: float,
    signed: bool,
    font,
) -> None:
    width = 25
    gradient = np.repeat(lut[::-1, None, :], width, axis=1)
    bar = Image.fromarray(gradient, mode="RGB").resize((width, height), Image.Resampling.BILINEAR)
    canvas.paste(bar, (x, y))
    draw.rectangle((x, y, x + width, y + height), outline=(70, 70, 70), width=1)
    values = (vmax, 0.0, -vmax) if signed else (vmax, vmax / 2.0, 0.0)
    positions = (y, y + height // 2, y + height)
    for value, tick_y in zip(values, positions):
        draw.line((x + width, tick_y, x + width + 7, tick_y), fill=(40, 40, 40), width=2)
        label = f"{value:.2f}" if signed else f"{value:.1f}"
        draw.text((x + width + 11, tick_y - 10), label, font=font, fill=(30, 30, 30))


def paste_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    column: int,
    y: int,
    title: str,
    lut: np.ndarray,
    vmax: float,
    signed: bool,
    panel_width: int,
    panel_height: int,
    margin_x: int,
    gap: int,
    title_font,
    tick_font,
) -> None:
    column_x = margin_x + column * (panel_width + gap)
    title_height = 54
    draw_centered(draw, (column_x, y, column_x + panel_width, y + title_height), title, title_font)
    available_width = panel_width - 100
    available_height = panel_height - title_height
    scale = min(available_width / image.width, available_height / image.height)
    target_width = max(1, round(image.width * scale))
    target_height = max(1, round(image.height * scale))
    resized = image.resize(
        (target_width, target_height),
        Image.Resampling.NEAREST if signed else Image.Resampling.BILINEAR,
    )
    image_x = column_x + (available_width - target_width) // 2
    image_y = y + title_height + (available_height - target_height) // 2
    canvas.paste(resized, (image_x, image_y))
    draw.rectangle((image_x, image_y, image_x + target_width, image_y + target_height), outline=(55, 55, 55), width=2)
    add_colorbar(
        canvas,
        draw,
        lut,
        column_x + available_width + 15,
        image_y,
        target_height,
        vmax,
        signed,
        tick_font,
    )


def render_boundary_figure(row: dict[str, object], output_path: Path, boundary_label: str) -> None:
    patch = str(row["patch"])
    gt = np.load(HUNDRED / "gt_dir" / f"gt_{patch}.npz")["R_gt"].astype(np.float64)
    solver_gt = np.load(solution_path(SOLVER_GT_DIR, patch))["R_hat"].astype(np.float64)
    convex = np.load(solution_path(CONVEX_DIR, patch))["R_hat"].astype(np.float64)

    rain_max = float(max(np.nanmax(gt), np.nanmax(solver_gt), np.nanmax(convex)))
    rainy = gt >= RAIN_THRESHOLD
    rel_solver_gt = np.full_like(gt, np.nan)
    rel_convex = np.full_like(gt, np.nan)
    rel_solver_gt[rainy] = (solver_gt[rainy] - gt[rainy]) / gt[rainy]
    rel_convex[rainy] = (convex[rainy] - gt[rainy]) / gt[rainy]
    finite_abs_error = np.concatenate(
        [
            np.abs(rel_solver_gt[np.isfinite(rel_solver_gt)]),
            np.abs(rel_convex[np.isfinite(rel_convex)]),
        ]
    )
    error_max = float(max(np.quantile(finite_abs_error, 0.99), 1e-12))

    width = 2400
    height = 1500
    margin_x = 75
    gap = 50
    panel_width = (width - 2 * margin_x - 2 * gap) // 3
    top_panel_height = 570
    bottom_panel_height = 570
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(FONT_BOLD, 42)
    subtitle_font = load_font(FONT_REGULAR, 29)
    panel_title_font = load_font(FONT_BOLD, 29)
    tick_font = load_font(FONT_REGULAR, 22)
    note_font = load_font(FONT_REGULAR, 23)

    short_patch = str(row["short_patch"])
    title = f"{boundary_label}: {short_patch}"
    draw_centered(draw, (40, 20, width - 40, 85), title, title_font)
    metrics = (
        f"d_Solver(GT) = {float(row['d_solver_gt']):.4f} mm/h,  "
        f"d_Convex = {float(row['d_convex']):.4f} mm/h,  "
        f"ratio = {float(row['ratio']):.4f}"
    )
    draw_centered(draw, (40, 82, width - 40, 135), metrics, subtitle_font, fill=(70, 70, 70))

    top_y = 145
    paste_panel(canvas, draw, colorize_rain(gt, rain_max), 0, top_y, "Ground truth", VIRIDIS, rain_max, False, panel_width, top_panel_height, margin_x, gap, panel_title_font, tick_font)
    paste_panel(canvas, draw, colorize_rain(solver_gt, rain_max), 1, top_y, "Solver(GT)", VIRIDIS, rain_max, False, panel_width, top_panel_height, margin_x, gap, panel_title_font, tick_font)
    paste_panel(canvas, draw, colorize_rain(convex, rain_max), 2, top_y, "Convex Solver", VIRIDIS, rain_max, False, panel_width, top_panel_height, margin_x, gap, panel_title_font, tick_font)

    bottom_y = 730
    paste_panel(canvas, draw, colorize_error(rel_solver_gt, error_max), 1, bottom_y, "Solver(GT) relative error", DIVERGING, error_max, True, panel_width, bottom_panel_height, margin_x, gap, panel_title_font, tick_font)
    paste_panel(canvas, draw, colorize_error(rel_convex, error_max), 2, bottom_y, "Convex relative error", DIVERGING, error_max, True, panel_width, bottom_panel_height, margin_x, gap, panel_title_font, tick_font)

    note = (
        f"Rainfall scale: 0 to {rain_max:.1f} mm/h. Relative error is shown for ground-truth rainfall >= "
        f"{RAIN_THRESHOLD:.1f} mm/h; gray is non-rainy. Error colors are clipped at the shared 99th percentile (+/-{error_max:.2f})."
    )
    draw_centered(draw, (70, 1375, width - 70, 1450), note, note_font, fill=(75, 75, 75))
    canvas.save(output_path, dpi=(240, 240), optimize=True)


def latex_patch_list(rows: list[dict[str, object]], columns: int) -> str:
    lines = [
        f"\\begin{{multicols}}{{{columns}}}",
        "\\scriptsize",
        "\\setlength{\\parskip}{0.18em}",
    ]
    for row in rows:
        lines.append(f"\\patchitem{{{row['short_patch']}}}")
    lines.extend(["\\end{multicols}"])
    return "\n".join(lines)


def build_latex(rows: list[dict[str, object]], largest_case_2: dict[str, object], smallest_case_1: dict[str, object]) -> str:
    case_1 = sorted((row for row in rows if row["case"] == 1), key=lambda row: str(row["patch"]))
    case_2 = sorted((row for row in rows if row["case"] == 2), key=lambda row: str(row["patch"]))
    bin_counts = Counter(math.floor(float(row["ratio"])) for row in rows)
    bin_rows = []
    for lower in range(0, math.floor(max(float(row["ratio"]) for row in rows)) + 1):
        count = bin_counts[lower]
        bin_rows.append(f"$[{lower},{lower + 1})$ & {count} & {count:.1f}\\% \\\\")

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=23mm]{{geometry}}
\usepackage{{amsmath}}
\usepackage{{booktabs}}
\usepackage{{graphicx}}
\usepackage{{float}}
\usepackage{{microtype}}
\usepackage{{multicol}}
\usepackage[table]{{xcolor}}
\usepackage[hidelinks]{{hyperref}}

\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.55em}}
\setlength{{\columnsep}}{{1.2em}}
\setlength{{\multicolsep}}{{0.4em}}
\raggedcolumns
\newcommand{{\solverGT}}{{\textsc{{Solver(GT)}}}}
\newcommand{{\solverConvex}}{{\textsc{{Convex Solver}}}}
\newcommand{{\patchitem}}[1]{{\noindent\texttt{{\detokenize{{#1}}}}\par}}

\title{{Classification of the 100 Benchmark Patches by Solver-RMSE Ratio}}
\author{{}}
\date{{}}

\begin{{document}}
\maketitle

\section{{Criterion and counts}}

For each patch $P$ with $N_P$ pixels, define the two whole-patch root mean square errors
\begin{{align}}
d_{{\solverGT}}(P)
  &= \sqrt{{\frac{{1}}{{N_P}}\sum_{{p=1}}^{{N_P}}
      \left(\widehat{{R}}_{{P,\solverGT}}(p)-R_P(p)\right)^2}},\\
d_{{\solverConvex}}(P)
  &= \sqrt{{\frac{{1}}{{N_P}}\sum_{{p=1}}^{{N_P}}
      \left(\widehat{{R}}_{{P,\solverConvex}}(p)-R_P(p)\right)^2}}.
\end{{align}}
The classification ratio is
\begin{{equation}}
q(P)=\frac{{d_{{\solverConvex}}(P)}}{{d_{{\solverGT}}(P)}}.
\end{{equation}}
A patch belongs to \textbf{{Case 1}} when $q(P)\geq 2$: the Convex Solver's RMSE is at least twice the RMSE of \solverGT, so \solverGT\ is much closer to the ground truth. A patch belongs to \textbf{{Case 2}} when $q(P)<2$: the two RMSE values are comparatively close. The equality is assigned to Case 1 by definition.

Applying this rule to all 100 patches gives
\begin{{center}}
\begin{{tabular}}{{lrr}}
\toprule
Classification & Number of patches & Percentage \\
\midrule
Case 1 ($q\geq 2$) & {len(case_1)} & {len(case_1):.1f}\% \\
Case 2 ($q<2$) & {len(case_2)} & {len(case_2):.1f}\% \\
\midrule
Total & {len(rows)} & 100.0\% \\
\bottomrule
\end{{tabular}}
\end{{center}}

The observed ratios range from {min(float(row['ratio']) for row in rows):.4f} to {max(float(row['ratio']) for row in rows):.4f}. There is no patch in the interval between the largest Case 2 ratio ({float(largest_case_2['ratio']):.4f}) and the smallest Case 1 ratio ({float(smallest_case_1['ratio']):.4f}).

\section{{Distribution of the ratio}}

Table~\ref{{tab:ratio-distribution}} reports the distribution of $q(P)$ across all 100 patches, independently of the assigned case. The intervals have width one and are left-closed and right-open.

\begin{{table}}[H]
\centering
\begin{{tabular}}{{crr}}
\toprule
Ratio interval & Number of patches & Percentage \\
\midrule
{chr(10).join(bin_rows)}
\midrule
Total & 100 & 100.0\% \\
\bottomrule
\end{{tabular}}
\caption{{Distribution of $d_{{\solverConvex}}/d_{{\solverGT}}$ in bins of width one.}}
\label{{tab:ratio-distribution}}
\end{{table}}

\section{{Patch assignments}}

The common identifier prefix \texttt{{RAD\_OPERA\_HOURLY\_RAINFALL\_ACCUMULATION\_}} is omitted below.

\subsection{{Case 1: {len(case_1)} patches}}
{latex_patch_list(case_1, 2)}

\subsection{{Case 2: {len(case_2)} patches}}
{latex_patch_list(case_2, 3)}

\clearpage
\section{{Boundary heatmaps}}

The following figures show the two patches closest to the threshold from either side. All rainfall panels within a figure use the same color scale. Relative errors are computed as $(\widehat{{R}}-R)/R$ for rainy ground-truth pixels with $R\geq 0.6$~mm/h; non-rainy pixels are gray. To keep the spatial error patterns legible, the symmetric error scale is clipped at the shared 99th percentile of the absolute relative errors from the two solvers.

\begin{{figure}}[H]
  \centering
  \includegraphics[width=\textwidth]{{figures/largest_case2_ratio_heatmaps.png}}
  \caption{{Largest ratio in Case 2: \texttt{{\detokenize{{{largest_case_2['short_patch']}}}}}. Here $d_{{\solverGT}}={float(largest_case_2['d_solver_gt']):.4f}$~mm/h, $d_{{\solverConvex}}={float(largest_case_2['d_convex']):.4f}$~mm/h, and $q={float(largest_case_2['ratio']):.4f}<2$.}}
  \label{{fig:largest-case2-ratio}}
\end{{figure}}

\begin{{figure}}[H]
  \centering
  \includegraphics[width=\textwidth]{{figures/smallest_case1_ratio_heatmaps.png}}
  \caption{{Smallest ratio in Case 1: \texttt{{\detokenize{{{smallest_case_1['short_patch']}}}}}. Here $d_{{\solverGT}}={float(smallest_case_1['d_solver_gt']):.4f}$~mm/h, $d_{{\solverConvex}}={float(smallest_case_1['d_convex']):.4f}$~mm/h, and $q={float(smallest_case_1['ratio']):.4f}\geq 2$.}}
  \label{{fig:smallest-case1-ratio}}
\end{{figure}}

\end{{document}}
"""


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_metrics()
    case_1 = [row for row in rows if row["case"] == 1]
    case_2 = [row for row in rows if row["case"] == 2]
    largest_case_2 = max(case_2, key=lambda row: float(row["ratio"]))
    smallest_case_1 = min(case_1, key=lambda row: float(row["ratio"]))

    render_boundary_figure(
        largest_case_2,
        FIGURE_DIR / "largest_case2_ratio_heatmaps.png",
        "Largest Case 2 ratio",
    )
    render_boundary_figure(
        smallest_case_1,
        FIGURE_DIR / "smallest_case1_ratio_heatmaps.png",
        "Smallest Case 1 ratio",
    )
    (LATEX_DIR / "case_ratio_classification.tex").write_text(
        build_latex(rows, largest_case_2, smallest_case_1),
        encoding="utf-8",
    )

    print(f"Case 1: {len(case_1)}")
    print(f"Case 2: {len(case_2)}")
    print(
        "Largest Case 2:",
        largest_case_2["short_patch"],
        f"q={float(largest_case_2['ratio']):.6f}",
    )
    print(
        "Smallest Case 1:",
        smallest_case_1["short_patch"],
        f"q={float(smallest_case_1['ratio']):.6f}",
    )


if __name__ == "__main__":
    main()
