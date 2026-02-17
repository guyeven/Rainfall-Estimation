# main.py
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import numpy as np


def _pid(rec: Dict) -> str:
    return str(rec.get("patch_id") or rec.get("id") or "").strip()


def load_jsonl(path: Path) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid JSON in {path} at line {lineno}: {e}") from e


def _choose_path_dialog(msg: str, *, must_exist: bool, must_be_dir: bool) -> Optional[Path]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if must_be_dir:
            selected = filedialog.askdirectory(title=msg)
        else:
            selected = filedialog.askopenfilename(title=msg)
        root.destroy()
    except Exception:
        return None

    if not selected:
        return None
    p = Path(selected).expanduser()
    if must_exist and not p.exists():
        return None
    if must_be_dir and p.exists() and not p.is_dir():
        return None
    return p


def prompt_path(
    msg: str,
    *,
    must_exist: bool = True,
    must_be_dir: bool = False,
    use_dialog: bool = True,
) -> Path:
    while True:
        p = _choose_path_dialog(msg, must_exist=must_exist, must_be_dir=must_be_dir) if use_dialog else None
        if p is None:
            raw = input(msg).strip()
            if not raw:
                print("Empty path. Try again.")
                continue
            p = Path(os.path.expanduser(os.path.expandvars(raw))).expanduser()
        if must_exist and not p.exists():
            print("Path does not exist. Try again.")
            continue
        if must_be_dir and p.exists() and not p.is_dir():
            print("Path is not a directory. Try again.")
            continue
        return p


def prompt_int(msg: str) -> int:
    while True:
        raw = input(msg).strip()
        try:
            v = int(raw)
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            print("Invalid integer. Try again.")


def prompt_int_default(msg: str, *, default: int) -> int:
    while True:
        raw = input(msg).strip()
        if raw == "":
            return int(default)
        try:
            v = int(raw)
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            print("Invalid integer. Try again.")


def prompt_choice(msg: str, allowed: List[str]) -> str:
    allowed_u = {a.upper() for a in allowed}
    while True:
        raw = input(f"{msg} ({'/'.join(allowed)}): ").strip().upper()
        if raw in allowed_u:
            return raw
        print(f"Invalid input. Allowed: ({'/'.join(allowed)})")


def prompt_yes_default_yes(msg: str) -> bool:
    while True:
        raw = input(msg).strip().lower()
        if raw == "":
            return True
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Invalid input. Allowed: (Y/n)")


def prompt_yes_default_no(msg: str) -> bool:
    while True:
        raw = input(msg).strip().lower()
        if raw == "":
            return False
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Invalid input. Allowed: (y/N)")


def main() -> None:
    print("=== Patch-based link attenuation + estimator export ===")
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--gaussian-gt", action="store_true", help="Use Gaussian GT instead of H5 rainfall.")
    ap.add_argument("--no-gaussian-gt", action="store_true", help="Force real H5 rainfall (no Gaussian).")
    args, _ = ap.parse_known_args()

    patch_list_path = prompt_path("Patch list JSONL path: ")
    patch_attr_path = prompt_path("Patch attributes JSONL path: ")
    links_path = prompt_path("4TU links JSONL path: ")
    out_dir = prompt_path("Output directory: ", must_exist=False, must_be_dir=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    k = prompt_int("Number of patches to process (k): ")
    start_patch_1based = prompt_int_default(
        f"Start patch index in patch-list JSONL "
        f"(press Enter for 1; input 1 means patches [1,{k}] are considered): ",
        default=1,
    )
    default_pol = prompt_choice("Default polarization if missing", ["H", "V"])
    export_gt = prompt_yes_default_yes("Export ground truth as gt_<patch_id>.npz? (Y/n): ")
    if args.gaussian_gt and args.no_gaussian_gt:
        raise SystemExit("Choose only one of --gaussian-gt or --no-gaussian-gt.")
    if args.gaussian_gt:
        use_gaussian_gt = True
    elif args.no_gaussian_gt:
        use_gaussian_gt = False
    else:
        use_gaussian_gt = prompt_yes_default_no("Use Gaussian GT instead of H5 rainfall? (y/N): ")
    debug_mode = prompt_choice("Debug mode?", ["Y", "N"]) == "Y"

    debug_patch_id = ""
    debug_link_index = -1
    if debug_mode:
        if k > 1:
            debug_patch_id = input("Patch id to debug: ").strip()
        else:
            print("k=1 → debugging the single processed patch")
        debug_link_index = prompt_int("Link index to debug: ") - 1
        if debug_link_index < 0:
            print("Link index must be >= 1")
            return

    patches = list(load_jsonl(patch_list_path))
    attr_ids: Set[str] = {_pid(r) for r in load_jsonl(patch_attr_path) if _pid(r)}
    links = list(load_jsonl(links_path))

    start0 = max(0, int(start_patch_1based) - 1)
    end0 = start0 + int(k)
    window = patches[start0:end0]
    selected = [p for p in window if _pid(p) in attr_ids]
    n_skipped = len(window) - len(selected)
    print(
        f"Requested patch-list window [{start0 + 1},{min(len(patches), end0)}] "
        f"({len(window)} records); processing {len(selected)} after attr-id filter"
        + (f" (skipped {n_skipped} without matching attrs)." if n_skipped > 0 else ".")
    )
    if not selected:
        print("No selected patches found. Check that patch ids match between files.")
        return

    from rainfall_processing import prepare_rainfall_for_patch
    from link_geometry import translate_and_filter_links_for_patch
    from attenuation import compute_attenuation_for_patch, DebugRequest
    from estimator_io import write_estimator_input_json, write_ground_truth_npz

    for patch in selected:
        pid = _pid(patch)
        print(f"[PATCH {pid}] processing")

        rain = prepare_rainfall_for_patch(patch)
        gt_real = rain.refined_smoothed_mmph.astype(np.float32)
        if use_gaussian_gt:
            H, W = gt_real.shape
            M = float(np.percentile(gt_real, 95))
            ys = np.arange(H, dtype=np.float64)
            xs = np.arange(W, dtype=np.float64)
            cy = H / 2.0
            cx = W / 2.0
            yy = (ys[:, None] - cy) / float(H)
            xx = (xs[None, :] - cx) / float(W)
            gt = (M * np.exp(-18.0 * (yy * yy + xx * xx))).astype(np.float32)
            print(f"[PATCH {pid}] Gaussian GT with M(p95)={M:.3f} mm/h")
        else:
            gt = gt_real

        rect_rd, links_in_patch = translate_and_filter_links_for_patch(
            links=links,
            patch=patch,
            default_freq_ghz=10.0,
            default_pol=default_pol,
            verbose=True,
        )

        if export_gt:
            write_ground_truth_npz(out_dir / f"gt_{pid}.npz", patch_id=pid, R_gt_mmph=gt)

        dbg = None
        if debug_mode:
            if k == 1 or pid == debug_patch_id:
                dbg = DebugRequest(patch_id=pid, link_index=int(debug_link_index))

        patch_out = out_dir / f"patch_{pid}.jsonl"
        link_recs, segments_by_link, _ = compute_attenuation_for_patch(
            patch=patch,
            rect_rd=rect_rd,
            links_in_patch=links_in_patch,
            refined_smoothed_mmph=gt,
            out_jsonl_path=patch_out,
            debug=dbg,
        )

        H, W = gt.shape
        est_out = out_dir / f"est_input_{pid}.json"
        write_estimator_input_json(
            est_out,
            patch_id=pid,
            rect_rd=rect_rd,
            H=int(H),
            W=int(W),
            links=link_recs,
            segments_by_link=segments_by_link,
            pixel_size_m=125.0,
        )

        print(f"[PATCH {pid}] wrote {patch_out.name} and {est_out.name}" + (f" and gt_{pid}.npz" if export_gt else ""))

    print("Done.")


if __name__ == "__main__":
    main()
