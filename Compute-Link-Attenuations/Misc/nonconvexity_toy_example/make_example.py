#!/usr/bin/env python3
"""Generate a minimal 3x3 counterexample to convexity of the CML data term."""

from __future__ import annotations

import csv
import html
import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from cml_attenuation.itu_r_p_8383 import k_alpha  # noqa: E402


FREQUENCY_GHZ = 38.003
POLARIZATION = "horizontal"
PIXEL_LENGTH_KM = 0.125
N_LINK_PIXELS = 3
LINK_LENGTH_KM = PIXEL_LENGTH_KM * N_LINK_PIXELS
BACKGROUND_RAIN = 1.0
HEAVY_RAIN = 20.0


def link_attenuation(field: list[list[float]], *, k: float, alpha: float) -> float:
    """Attenuation for one horizontal link through the middle grid row."""
    return PIXEL_LENGTH_KM * k * sum(value**alpha for value in field[1])


def normalized_data_term(a_hat: float, a_obs: float) -> float:
    """The one-link J_atten scaling used by the normalized solver."""
    return (a_hat - a_obs) ** 2 / LINK_LENGTH_KM


def interpolate_fields(
    left: list[list[float]], right: list[list[float]], theta: float
) -> list[list[float]]:
    return [
        [(1.0 - theta) * a + theta * b for a, b in zip(left_row, right_row)]
        for left_row, right_row in zip(left, right)
    ]


def rain_color(value: float) -> str:
    """A small white-to-blue ramp used in the SVG."""
    t = max(0.0, min(1.0, value / HEAVY_RAIN))
    low = (247, 251, 255)
    high = (8, 48, 107)
    rgb = tuple(round((1.0 - t) * lo + t * hi) for lo, hi in zip(low, high))
    return "#" + "".join(f"{channel:02x}" for channel in rgb)


def svg_text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 18,
    anchor: str = "middle",
    weight: str = "normal",
    fill: str = "#202020",
) -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}">{html.escape(value)}</text>'
    )


def grid_panel(
    field: list[list[float]],
    *,
    x: float,
    y: float,
    cell: float,
    title: str,
    attenuation: float,
    loss: float,
) -> list[str]:
    parts = [svg_text(x + 1.5 * cell, y - 18, title, size=22, weight="bold")]
    for row in range(3):
        for col in range(3):
            value = field[row][col]
            px = x + col * cell
            py = y + row * cell
            parts.append(
                f'<rect x="{px:.2f}" y="{py:.2f}" width="{cell:.2f}" height="{cell:.2f}" '
                f'fill="{rain_color(value)}" stroke="#303030" stroke-width="1.3"/>'
            )
    # The red/white line is the CML crossing the three middle-row pixels.
    link_y = y + 1.22 * cell
    parts.append(
        f'<rect x="{x + 4:.2f}" y="{link_y - 4:.2f}" width="{3 * cell - 8:.2f}" height="8" '
        'rx="4" fill="#e45756"/>'
    )
    parts.append(
        f'<rect x="{x + 4:.2f}" y="{link_y - 1.2:.2f}" width="{3 * cell - 8:.2f}" height="2.4" '
        'rx="1.2" fill="white"/>'
    )
    for row in range(3):
        for col in range(3):
            value = field[row][col]
            fill = "white" if value >= 0.55 * HEAVY_RAIN else "#202020"
            parts.append(
                svg_text(
                    x + (col + 0.5) * cell,
                    y + (row + 0.59) * cell,
                    f"{value:g}",
                    size=21,
                    weight="bold",
                    fill=fill,
                )
            )
    parts.append(
        svg_text(
            x + 1.5 * cell,
            y + 3 * cell + 30,
            f"A-hat = {attenuation:.4f} dB;  J_atten = {loss:.5f}",
            size=16,
        )
    )
    return parts


def make_svg(
    *,
    left: list[list[float]],
    midpoint: list[list[float]],
    right: list[list[float]],
    a_obs: float,
    a_mid: float,
    j_mid: float,
    alpha: float,
    theta: list[float],
    j_path: list[float],
) -> str:
    width, height = 1200, 820
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        svg_text(
            width / 2,
            38,
            "A 3×3 counterexample for the physical CML attenuation data term",
            size=25,
            weight="bold",
        ),
        svg_text(
            width / 2,
            65,
            f"one 375 m link, {FREQUENCY_GHZ:.3f} GHz H polarization; each crossed pixel contributes 125 m",
            size=16,
            fill="#505050",
        ),
    ]

    cell = 76.0
    panel_y = 115.0
    panel_x = [120.0, 486.0, 852.0]
    panels = [
        (left, "R(L)", a_obs, 0.0),
        (midpoint, "[R(L) + R(R)] / 2", a_mid, j_mid),
        (right, "R(R)", a_obs, 0.0),
    ]
    for x, (field, title, attenuation, loss) in zip(panel_x, panels):
        parts.extend(
            grid_panel(
                field,
                x=x,
                y=panel_y,
                cell=cell,
                title=title,
                attenuation=attenuation,
                loss=loss,
            )
        )

    plot_x, plot_y = 105.0, 495.0
    plot_w, plot_h = 990.0, 245.0
    max_j = max(j_path)
    y_limit = max_j * 1.18

    def px(t: float) -> float:
        return plot_x + t * plot_w

    def py(value: float) -> float:
        return plot_y + plot_h - value / y_limit * plot_h

    for i in range(5):
        value = y_limit * i / 4
        yy = py(value)
        parts.append(
            f'<line x1="{plot_x:.2f}" y1="{yy:.2f}" x2="{plot_x + plot_w:.2f}" y2="{yy:.2f}" '
            'stroke="#d7d7d7" stroke-width="1" stroke-dasharray="3,5"/>'
        )
        parts.append(svg_text(plot_x - 12, yy + 6, f"{value:.3f}", size=14, anchor="end"))
    for i in range(5):
        value = i / 4
        xx = px(value)
        parts.append(
            f'<line x1="{xx:.2f}" y1="{plot_y:.2f}" x2="{xx:.2f}" y2="{plot_y + plot_h:.2f}" '
            'stroke="#e3e3e3" stroke-width="1" stroke-dasharray="3,5"/>'
        )
        parts.append(svg_text(xx, plot_y + plot_h + 25, f"{value:.2f}", size=14))
    parts.append(
        f'<line x1="{plot_x:.2f}" y1="{plot_y:.2f}" x2="{plot_x:.2f}" y2="{plot_y + plot_h:.2f}" '
        'stroke="#303030" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{plot_x:.2f}" y1="{plot_y + plot_h:.2f}" x2="{plot_x + plot_w:.2f}" '
        f'y2="{plot_y + plot_h:.2f}" stroke="#303030" stroke-width="1.5"/>'
    )

    # A path with a moderate number of vertices renders reliably in lightweight
    # SVG converters while remaining visually smooth.
    sampled_path = list(zip(theta, j_path))[::5]
    if sampled_path[-1][0] != theta[-1]:
        sampled_path.append((theta[-1], j_path[-1]))
    upper = [(px(t), py(j) - 2.0) for t, j in sampled_path]
    lower = [(px(t), py(j) + 2.0) for t, j in reversed(sampled_path)]
    curve_polygon = " ".join(f"{x:.2f},{y:.2f}" for x, y in upper + lower)
    parts.append(
        f'<polygon points="{curve_polygon}" fill="#e45756"/>'
    )
    # For alpha=1 attenuation is affine; on this constant-sum slice its loss is flat at zero.
    dash_x = plot_x
    while dash_x < plot_x + plot_w:
        dash_width = min(9.0, plot_x + plot_w - dash_x)
        parts.append(
            f'<rect x="{dash_x:.2f}" y="{py(0.0) - 3.5:.2f}" width="{dash_width:.2f}" height="3" '
            'fill="#4c78a8"/>'
        )
        dash_x += 16.0
    for t, value in [(0.0, 0.0), (0.5, j_mid), (1.0, 0.0)]:
        parts.append(
            f'<circle cx="{px(t):.2f}" cy="{py(value):.2f}" r="6" fill="#e45756" stroke="white" stroke-width="2"/>'
        )

    parts.append(
        f'<line x1="{px(0.5):.2f}" y1="{py(j_mid) - 8:.2f}" x2="{px(0.64):.2f}" '
        f'y2="{py(0.82 * max_j):.2f}" stroke="#505050" stroke-width="1.5"/>'
    )
    parts.append(
        svg_text(
            px(0.65),
            py(0.82 * max_j) - 4,
            f"midpoint loss = {j_mid:.5f} > 0",
            size=16,
            anchor="start",
        )
    )

    parts.append(
        svg_text(
            plot_x + plot_w / 2,
            plot_y - 22,
            "Convexity fails: J(1/2) > [J(0) + J(1)] / 2 = 0",
            size=20,
            weight="bold",
        )
    )
    parts.append(
        svg_text(
            plot_x + plot_w / 2,
            plot_y + plot_h + 51,
            "Interpolation  R(theta) = (1 − theta) R(L) + theta R(R)",
            size=17,
        )
    )
    parts.append(
        f'<text x="31" y="{plot_y + plot_h / 2:.2f}" text-anchor="middle" '
        'font-family="Arial, Helvetica, sans-serif" font-size="17" fill="#202020" '
        f'transform="rotate(-90 31 {plot_y + plot_h / 2:.2f})">J_atten(R(theta))</text>'
    )

    legend_x, legend_y = plot_x + 25, plot_y + 25
    parts.append(
        f'<rect x="{legend_x}" y="{legend_y - 2}" width="45" height="4" fill="#e45756"/>'
    )
    parts.append(
        svg_text(
            legend_x + 57,
            legend_y + 6,
            f"physical link: alpha = {alpha:.6f}",
            size=15,
            anchor="start",
        )
    )
    for offset in (0, 16, 32):
        parts.append(
            f'<rect x="{legend_x + offset}" y="{legend_y + 25.5}" width="9" height="3" fill="#4c78a8"/>'
        )
    parts.append(
        svg_text(
            legend_x + 57,
            legend_y + 33,
            "linear surrogate: alpha = 1",
            size=15,
            anchor="start",
        )
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    k, alpha = k_alpha(FREQUENCY_GHZ, POLARIZATION)

    left = [[BACKGROUND_RAIN for _ in range(3)] for _ in range(3)]
    right = [[BACKGROUND_RAIN for _ in range(3)] for _ in range(3)]
    left[1][0] = HEAVY_RAIN
    right[1][2] = HEAVY_RAIN
    midpoint = interpolate_fields(left, right, 0.5)

    a_obs = link_attenuation(left, k=k, alpha=alpha)
    a_right = link_attenuation(right, k=k, alpha=alpha)
    a_mid = link_attenuation(midpoint, k=k, alpha=alpha)
    j_left = normalized_data_term(a_obs, a_obs)
    j_right = normalized_data_term(a_right, a_obs)
    j_mid = normalized_data_term(a_mid, a_obs)

    theta = [i / 500 for i in range(501)]
    j_path = []
    for value in theta:
        field = interpolate_fields(left, right, value)
        a_hat = link_attenuation(field, k=k, alpha=alpha)
        j_path.append(normalized_data_term(a_hat, a_obs))

    svg_path = HERE / "nonconvexity_3x3.svg"
    svg_path.write_text(
        make_svg(
            left=left,
            midpoint=midpoint,
            right=right,
            a_obs=a_obs,
            a_mid=a_mid,
            j_mid=j_mid,
            alpha=alpha,
            theta=theta,
            j_path=j_path,
        ),
        encoding="utf-8",
    )

    png_path = HERE / "nonconvexity_3x3.png"
    magick = shutil.which("magick")
    if magick is not None:
        conversion = subprocess.run(
            [magick, "-density", "180", str(svg_path), str(png_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if conversion.returncode != 0:
            print("warning: PNG conversion failed; the SVG was still generated", file=sys.stderr)
            print(conversion.stderr.strip(), file=sys.stderr)
    else:
        print("warning: ImageMagick not found; the SVG was generated without a PNG", file=sys.stderr)

    csv_path = HERE / "nonconvexity_3x3_numbers.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["quantity", "value"])
        writer.writerow(["frequency_ghz", f"{FREQUENCY_GHZ:.12g}"])
        writer.writerow(["k", f"{k:.12g}"])
        writer.writerow(["alpha", f"{alpha:.12g}"])
        writer.writerow(["pixel_length_km", f"{PIXEL_LENGTH_KM:.12g}"])
        writer.writerow(["link_length_km", f"{LINK_LENGTH_KM:.12g}"])
        writer.writerow(["A_obs_db", f"{a_obs:.12g}"])
        writer.writerow(["A_midpoint_db", f"{a_mid:.12g}"])
        writer.writerow(["midpoint_attenuation_ratio", f"{a_mid / a_obs:.12g}"])
        writer.writerow(["J_left", f"{j_left:.12g}"])
        writer.writerow(["J_midpoint", f"{j_mid:.12g}"])
        writer.writerow(["J_right", f"{j_right:.12g}"])

    print(f"k={k:.12f}")
    print(f"alpha={alpha:.12f}")
    print(f"A_obs=A_left=A_right={a_obs:.12f} dB")
    print(f"A_midpoint={a_mid:.12f} dB")
    print(f"J_left={j_left:.12f}")
    print(f"J_midpoint={j_mid:.12f}")
    print(f"J_right={j_right:.12f}")
    print(f"wrote {svg_path}")
    if png_path.exists():
        print(f"wrote {png_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
