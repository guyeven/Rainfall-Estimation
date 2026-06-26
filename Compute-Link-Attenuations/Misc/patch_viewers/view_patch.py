#!/usr/bin/env python3
"""
Interactive viewer: refined+smoothed rainfall + links + click-to-inspect.

Features:
- Load inputs from a JSON config file (--config) OR interactively.
- Supports patch id under keys 'id' or 'patch_id'.
- Automatically strips leading 'patch_' from patch_id if pasted.
- Background: refined + smoothed rainfall (Gaussian output).
- Click anywhere to select the nearest link; selected link is highlighted.
- Popup shows: link_index, attenuation_db, length_km, freq_ghz, pol.

Run:
  python view_patch.py
  python view_patch.py --config /path/to/view_patch_config.json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, TypeVar

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.widgets import Button

from cml_attenuation.rainfall_processing import prepare_rainfall_for_patch
from cml_attenuation.link_geometry import patch_rect_rd


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def prompt_path(msg: str, must_exist: bool = True) -> Path:
    while True:
        p = Path(input(msg).strip()).expanduser()
        if must_exist and not p.exists():
            print("Path does not exist. Try again.")
            continue
        return p


def prompt_str(msg: str) -> str:
    while True:
        s = input(msg).strip()
        if s:
            return s
        print("Empty input. Try again.")


T = TypeVar("T")


def _select_dir_with_dialog(msg: str) -> Path:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        print("Tkinter not available; falling back to manual path input.")
        return prompt_path(msg + ": ", must_exist=True)

    while True:
        root = tk.Tk()
        root.withdraw()
        try:
            raw = filedialog.askdirectory(title=msg, initialdir=str(Path.cwd()))
        finally:
            root.destroy()

        if not raw:
            print("No selection made. Please choose a directory.")
            continue
        p = Path(raw)
        if not p.exists() or not p.is_dir():
            print("Path is not a directory. Try again.")
            continue
        return p


def _choose_from_list(msg: str, items: Sequence[T], label_fn) -> T:
    if not items:
        raise ValueError("No items to choose from.")
    if len(items) == 1:
        return items[0]
    print(msg)
    for i, item in enumerate(items, start=1):
        print(f"  {i}) {label_fn(item)}")
    while True:
        raw = input(f"Select 1-{len(items)}: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("Invalid number. Try again.")
            continue
        if 1 <= idx <= len(items):
            return items[idx - 1]
        print("Out of range. Try again.")


def _pid(rec: dict) -> str:
    """Normalized patch id supporting both keys: 'patch_id' and 'id'."""
    return str(rec.get("patch_id") or rec.get("id") or "").strip()


def load_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def find_patch_by_id(patch_list_jsonl: Path, patch_id: str) -> Dict:
    target = patch_id.strip()
    with patch_list_jsonl.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if _pid(rec) == target:
                return rec
    raise KeyError(f"patch_id not found in patch list: {patch_id}")


def load_patch_map(patch_list_jsonl: Path) -> Dict[str, Dict]:
    patch_map: Dict[str, Dict] = {}
    with patch_list_jsonl.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pid = _pid(rec)
            if pid:
                patch_map[pid] = rec
    return patch_map


def load_config(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def resolve_config_path(path_value: str, config_path: Path) -> Path:
    p = Path(path_value).expanduser()
    if p.is_absolute():
        return p
    return (config_path.parent / p).resolve()


def _seg_dist2(px, py, x0, y0, x1, y1) -> float:
    """Squared distance from point to segment."""
    ax, ay = x0, y0
    bx, by = x1, y1
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0.0:
        return apx * apx + apy * apy
    t = (apx * abx + apy * aby) / ab2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    dx, dy = px - cx, py - cy
    return dx * dx + dy * dy


def _seg_len_km(x0, y0, x1, y1) -> float:
    return math.hypot(x1 - x0, y1 - y0) / 1000.0


@dataclass
class LinkArtist:
    rec: Dict
    line: any  # matplotlib Line2D


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default=None, help="Path to JSON config file")
    args = ap.parse_args()

    print("=== Patch viewer (refined+smoothed rainfall + clickable links) ===")

    # -----------------------------------------------------------------
    # Inputs: config OR interactive
    # -----------------------------------------------------------------
    if args.config:
        cfg_path = Path(args.config).expanduser().resolve()
        cfg = load_config(cfg_path)
        patch_list = resolve_config_path(str(cfg["patch_list_jsonl"]), cfg_path)
        patch_id = str(cfg["patch_id"]).strip()
        patch_out_jsonl = resolve_config_path(str(cfg["per_patch_output_jsonl"]), cfg_path)
    else:
        base_dir = _select_dir_with_dialog("Choose directory containing patch JSONL files")

        patch_files = sorted(base_dir.glob("patch_*.jsonl"))
        if patch_files:
            patch_out_jsonl = _choose_from_list(
                "Available patch outputs:",
                patch_files,
                label_fn=lambda p: p.name,
            )
            patch_id = patch_out_jsonl.stem[len("patch_") :]
        else:
            print("No patch_*.jsonl files found in the selected directory.")
            patch_out_jsonl = prompt_path(
                "Per-patch output JSONL path (e.g., patch_<patch_id>.jsonl): ",
                must_exist=True,
            )
            patch_id = prompt_str("Patch id to view: ")

        patch_list_candidates = [
            p
            for p in base_dir.glob("*.jsonl")
            if not p.name.startswith("patch_") and "patches" in p.stem.lower()
        ]
        if patch_list_candidates:
            patch_list = _choose_from_list(
                "Available patch list JSONL files:",
                sorted(patch_list_candidates),
                label_fn=lambda p: p.name,
            )
        else:
            patch_list = prompt_path("Patch list JSONL path: ")

    # Allow filename-style id
    if patch_id.startswith("patch_"):
        patch_id = patch_id[len("patch_"):]

    # -----------------------------------------------------------------
    # Load patch list once for browsing
    # -----------------------------------------------------------------
    patch_map = load_patch_map(patch_list)

    browsing = args.config is None and patch_files
    if browsing:
        patch_files_sorted = sorted(patch_files)
        patch_index = patch_files_sorted.index(patch_out_jsonl)
    else:
        patch_files_sorted = [patch_out_jsonl]
        patch_index = 0

    # -----------------------------------------------------------------
    # Plot background + links (initialized on first patch)
    # -----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 8))

    artists: List[LinkArtist] = []
    selected: Optional[LinkArtist] = None
    ann = ax.annotate(
        "",
        xy=(0, 0),
        xytext=(15, 15),
        textcoords="offset points",
        bbox=dict(boxstyle="round", fc="white", alpha=0.9),
        arrowprops=dict(arrowstyle="->"),
    )
    ann.set_visible(False)

    def _patch_id_from_file(path: Path) -> str:
        stem = path.stem
        return stem[len("patch_") :] if stem.startswith("patch_") else stem

    def _load_patch_for_file(path: Path):
        pid = _patch_id_from_file(path)
        if pid.startswith("patch_"):
            pid = pid[len("patch_") :]
        patch = patch_map.get(pid)
        if patch is None:
            raise KeyError(f"patch_id not found in patch list: {pid}")
        rain = prepare_rainfall_for_patch(patch)
        rect = patch_rect_rd(patch)
        link_recs = load_jsonl(path)
        return pid, patch, rect, rain.refined_smoothed_mmph, link_recs

    patch_id, patch, rect, img, link_recs = _load_patch_for_file(patch_out_jsonl)
    im = ax.imshow(
        img,
        origin="upper",
        extent=[rect.x_min, rect.x_max, rect.y_min, rect.y_max],
        interpolation="nearest",
        aspect="equal",
    )
    fig.colorbar(im, ax=ax, label="Rain rate (mm/h) [refined+smoothed]")
    ax.set_xlabel("x (m) EPSG:28992")
    ax.set_ylabel("y (m) EPSG:28992")

    label = fig.text(0.5, 0.01, "", ha="center")

    def _render_links(recs: List[Dict]) -> None:
        for la in artists:
            la.line.remove()
        artists.clear()
        for rec in recs:
            x0, y0, x1, y1 = (
                float(rec["xs_m"]),
                float(rec["ys_m"]),
                float(rec["xe_m"]),
                float(rec["ye_m"]),
            )
            (line,) = ax.plot([x0, x1], [y0, y1], linewidth=1.2)
            artists.append(LinkArtist(rec=rec, line=line))

    _render_links(link_recs)

    def _render_patch(index: int) -> None:
        nonlocal selected, patch_id
        path = patch_files_sorted[index]
        pid, _, rect, img, link_recs = _load_patch_for_file(path)
        patch_id = pid

        im.set_data(img)
        im.set_extent([rect.x_min, rect.x_max, rect.y_min, rect.y_max])
        im.set_clim(float(np.nanmin(img)), float(np.nanmax(img)))
        ax.set_xlim(rect.x_min, rect.x_max)
        ax.set_ylim(rect.y_min, rect.y_max)
        ax.set_title(f"Patch {patch_id}: refined+smoothed rainfall + links")

        label.set_text(path.name)

        selected = None
        ann.set_visible(False)
        _render_links(link_recs)
        fig.canvas.draw_idle()

    _render_patch(patch_index)

    # Annotation
    # -----------------------------------------------------------------
    # Click handler
    # -----------------------------------------------------------------
    def on_click(event):
        nonlocal selected
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return

        px, py = float(event.xdata), float(event.ydata)

        best = None
        best_d2 = float("inf")

        for la in artists:
            r = la.rec
            x0, y0, x1, y1 = (
                float(r["xs_m"]),
                float(r["ys_m"]),
                float(r["xe_m"]),
                float(r["ye_m"]),
            )
            d2 = _seg_dist2(px, py, x0, y0, x1, y1)
            if d2 < best_d2:
                best_d2 = d2
                best = la

        if best is None:
            return

        if selected is not None:
            selected.line.set_linewidth(1.2)

        selected = best
        selected.line.set_linewidth(3.0)

        r = selected.rec
        x0, y0, x1, y1 = (
            float(r["xs_m"]),
            float(r["ys_m"]),
            float(r["xe_m"]),
            float(r["ye_m"]),
        )

        info = (
            f"link_index: {r.get('link_index')}\n"
            f"attenuation_db: {r.get('attenuation_db')}\n"
            f"length_km: {_seg_len_km(x0, y0, x1, y1):.3f}\n"
            f"freq_ghz: {r.get('freq_ghz')}\n"
            f"pol: {r.get('pol')}\n"
            f"orig_index: {r.get('orig_index')}"
        )

        ann.xy = (px, py)
        ann.set_text(info)
        ann.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", on_click)

    # -----------------------------------------------------------------
    # Browse controls (interactive mode)
    # -----------------------------------------------------------------
    if browsing and len(patch_files_sorted) > 1:
        def go_prev(event=None):
            nonlocal patch_index
            patch_index = (patch_index - 1) % len(patch_files_sorted)
            _render_patch(patch_index)

        def go_next(event=None):
            nonlocal patch_index
            patch_index = (patch_index + 1) % len(patch_files_sorted)
            _render_patch(patch_index)

        ax_prev = plt.axes([0.72, 0.02, 0.1, 0.05])
        ax_next = plt.axes([0.83, 0.02, 0.1, 0.05])
        btn_prev = Button(ax_prev, "Prev")
        btn_next = Button(ax_next, "Next")
        btn_prev.on_clicked(go_prev)
        btn_next.on_clicked(go_next)

        def on_key(event):
            if event.key in ("left", "a"):
                go_prev()
            elif event.key in ("right", "d"):
                go_next()

        fig.canvas.mpl_connect("key_press_event", on_key)

    print("Viewer ready. Click a link to inspect its attenuation.")
    plt.show()


if __name__ == "__main__":
    main()
