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


def _undirected_edge_key_from_rec(rec: Dict, *, ndigits: int = 6):
    a = (round(float(rec["xs_m"]), ndigits), round(float(rec["ys_m"]), ndigits))
    b = (round(float(rec["xe_m"]), ndigits), round(float(rec["ye_m"]), ndigits))
    return tuple(sorted((a, b)))


def dedup_patch_links_keep_min_atten(
    link_recs: List[Dict],
    segments_by_link: Dict[str, List[Dict]],
) -> tuple[List[Dict], Dict[str, List[Dict]], int]:
    """
    Deduplicate undirected parallel/reversed links and keep the one with the
    smallest observed attenuation_db. Reindexes links/segments consistently.
    """
    best: Dict[tuple, tuple[Dict, int]] = {}
    for old_idx, rec in enumerate(link_recs):
        key = _undirected_edge_key_from_rec(rec)
        att = float(rec.get("attenuation_db", 0.0))
        prev = best.get(key)
        if prev is None or att < float(prev[0].get("attenuation_db", 0.0)):
            best[key] = (rec, old_idx)

    kept = sorted(best.values(), key=lambda t: t[1])
    new_recs: List[Dict] = []
    new_segments: Dict[str, List[Dict]] = {}
    for new_idx, (rec, old_idx) in enumerate(kept):
        rec2 = dict(rec)
        rec2["link_index"] = int(new_idx)
        new_recs.append(rec2)
        new_segments[str(new_idx)] = list(segments_by_link.get(str(old_idx), []))

    removed = max(0, len(link_recs) - len(new_recs))
    return new_recs, new_segments, removed


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


def prompt_patch_ids_exact_k(k: int) -> List[str]:
    while True:
        raw = input(f"Enter exactly {k} patch IDs, comma-separated: ").strip()
        if not raw:
            print("Empty input. Try again.")
            continue
        ids = [p.strip() for p in raw.split(",") if p.strip()]
        if len(ids) != k:
            print(f"You entered {len(ids)} IDs, but k={k}. Try again.")
            continue
        if len(set(ids)) != len(ids):
            print("Duplicate patch IDs found. Please provide unique IDs.")
            continue
        return ids


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
    use_named_patches = prompt_yes_default_no(
        "Do you want to specify exact patch IDs to process? (y/N): "
    )
    named_patch_ids: List[str] = []
    start_patch_1based = 1
    if use_named_patches:
        named_patch_ids = prompt_patch_ids_exact_k(k)
    else:
        start_patch_1based = prompt_int_default(
            f"Start patch index after attr filtering "
            f"(press Enter for 1; input 1 means filtered patches [1,{k}] are considered): ",
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
    dedup_parallel_links = prompt_yes_default_no(
        "Deduplicate parallel/reversed links in est_input (keep link with smallest A_db)? (y/N): "
    )
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

    gt_dir = out_dir / "gt_dir"
    est_dir = out_dir / "est_dir"
    patch_jsonl_dir = out_dir / "patch_jsonl_files"
    if export_gt:
        gt_dir.mkdir(parents=True, exist_ok=True)
    est_dir.mkdir(parents=True, exist_ok=True)
    patch_jsonl_dir.mkdir(parents=True, exist_ok=True)

    if use_named_patches:
        by_id = {_pid(p): p for p in patches if _pid(p)}
        missing = [pid for pid in named_patch_ids if pid not in by_id]
        if missing:
            print("These requested patch IDs were not found in patch-list JSONL:")
            for pid in missing:
                print(f"  - {pid}")
            print("Aborting. Please check spelling/case.")
            return
        selected = [by_id[pid] for pid in named_patch_ids]
        print(
            f"Found {len(patches)} total patch(es); "
            f"processing {len(selected)} explicitly requested patch(es) "
            f"(attr filter bypassed)."
        )
    else:
        filtered = [p for p in patches if _pid(p) in attr_ids]
        skipped_ids = [_pid(p) for p in patches if _pid(p) not in attr_ids]
        start0 = max(0, int(start_patch_1based) - 1)
        end0 = start0 + int(k)
        selected = filtered[start0:end0]
        print(
            f"Found {len(filtered)} patch(es) with attrs out of {len(patches)} total; "
            f"processing filtered window [{start0 + 1},{min(len(filtered), end0)}] "
            f"({len(selected)} patches selected)."
        )
        if skipped_ids:
            preview_max = 30
            if len(skipped_ids) <= preview_max:
                print(f"Skipped patch IDs (no attrs): {', '.join(skipped_ids)}")
            else:
                head = ", ".join(skipped_ids[:preview_max])
                print(f"Skipped patch IDs (no attrs, first {preview_max}/{len(skipped_ids)}): {head}")
    if not selected:
        print("No selected patches found. Check that patch ids match between files.")
        return

    from cml_attenuation.rainfall_processing import prepare_rainfall_for_patch
    from cml_attenuation.link_geometry import translate_and_filter_links_for_patch
    from cml_attenuation.attenuation import compute_attenuation_for_patch, DebugRequest
    from cml_attenuation.estimator_io import write_estimator_input_json, write_ground_truth_npz

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
            write_ground_truth_npz(gt_dir / f"gt_{pid}.npz", patch_id=pid, R_gt_mmph=gt)

        dbg = None
        if debug_mode:
            if k == 1 or pid == debug_patch_id:
                dbg = DebugRequest(patch_id=pid, link_index=int(debug_link_index))

        patch_out = patch_jsonl_dir / f"patch_{pid}.jsonl"
        link_recs, segments_by_link, _ = compute_attenuation_for_patch(
            patch=patch,
            rect_rd=rect_rd,
            links_in_patch=links_in_patch,
            refined_smoothed_mmph=gt,
            out_jsonl_path=patch_out,
            debug=dbg,
        )
        if dedup_parallel_links:
            link_recs, segments_by_link, removed = dedup_patch_links_keep_min_atten(link_recs, segments_by_link)
            if removed > 0:
                print(f"[PATCH {pid}] dedup removed {removed} parallel/reversed link(s)")

        H, W = gt.shape
        est_out = est_dir / f"est_input_{pid}.json"
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

        print(
            f"[PATCH {pid}] wrote "
            f"{patch_out.relative_to(out_dir)}, "
            f"{est_out.relative_to(out_dir)}"
            + (f", and {(gt_dir / f'gt_{pid}.npz').relative_to(out_dir)}" if export_gt else "")
        )

    print("Done.")


if __name__ == "__main__":
    main()
