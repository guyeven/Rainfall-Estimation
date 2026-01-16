#!/usr/bin/env python3
"""
Main entry point for patch-based link attenuation computation.

CLI-only program.

- Reads patch list JSONL and patch attributes JSONL.
- Selected patches are those that appear in attributes JSONL.
- Processes the first k selected patches in patch-list order.
- For each patch:
    - load/crop rainfall from patch['source_file'] H5
    - NaN->0, refine 16x16, gaussian smooth (sigma=1, mode='nearest')
    - translate 4TU links into patch coordinates (EPSG:28992)
    - keep links with both endpoints inside the patch rectangle
    - compute per-link attenuation (dB)
    - write per-patch JSONL containing all link original data + attenuation

- Optional debug:
    - if k==1: ask only for link_index
    - if k>1: ask for patch_id + link_index
    - writes per-pixel trace JSON next to the per-patch JSONL

Notes:
- Patch list may store the patch identifier under key 'id' (real data) or 'patch_id' (synthetic).
- Attributes file stores patch identifier under key 'patch_id'.
- We normalize both via _pid(rec).

All prompts show allowed answers in parentheses and repeat until valid.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


# -----------------------------
# Optional: TAB completion (best-effort only)
# -----------------------------
def _enable_path_completion() -> None:
    # Kept as best-effort; user can drag-and-drop paths (recommended).
    try:
        try:
            import gnureadline as readline  # type: ignore
        except Exception:
            import readline  # type: ignore

        import glob

        def completer(text: str, state: int):
            expanded = os.path.expanduser(os.path.expandvars(text))
            dirname = os.path.dirname(expanded) or "."
            basename = os.path.basename(expanded)
            pattern = os.path.join(dirname, basename + "*")
            matches = sorted(glob.glob(pattern))
            # Append / for directories
            out = [m + os.sep if os.path.isdir(m) else m for m in matches]
            return out[state] if state < len(out) else None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
    except Exception:
        pass


_enable_path_completion()


# -----------------------------
# Helpers
# -----------------------------
def _pid(rec: dict) -> str:
    """Normalized patch id, supporting both keys: 'patch_id' and 'id'."""
    return str(rec.get("patch_id") or rec.get("id") or "").strip()


def prompt_path_exists(msg: str, *, must_be_dir: bool = False, must_be_file: bool = False) -> Path:
    while True:
        raw = input(msg).strip()
        p = Path(os.path.expanduser(os.path.expandvars(raw)))

        if not p.exists():
            print("Path does not exist. Try again.")
            continue
        if must_be_dir and not p.is_dir():
            print("Path is not a directory. Try again.")
            continue
        if must_be_file and not p.is_file():
            print("Path is not a file. Try again.")
            continue
        return p


def prompt_int(msg: str) -> int:
    while True:
        s = input(msg).strip()
        try:
            return int(s)
        except ValueError:
            print("Invalid integer. Try again.")


def prompt_choice(msg: str, choices):
    choices_norm = {c.lower(): c for c in choices}
    while True:
        raw = input(f"{msg} ({'/'.join(choices)}): ").strip().lower()
        if raw in choices_norm:
            return choices_norm[raw]
        print(f"Invalid choice. Allowed answers: ({'/'.join(choices)})")


def load_jsonl(path: Path):
    # utf-8-sig strips BOM if present
    with path.open("r", encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                print(f"\nERROR: Invalid JSON in {path} at line {lineno}")
                print("Line starts with:", repr(line[:200]))
                raise


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    print("=== Patch-based link attenuation ===")

    patch_list_path = prompt_path_exists("Patch list JSONL path: ", must_be_file=True)
    patch_attr_path = prompt_path_exists("Patch attributes JSONL path: ", must_be_file=True)
    links_path = prompt_path_exists("4TU links JSONL path: ", must_be_file=True)
    out_dir = prompt_path_exists("Output directory: ", must_be_dir=True)

    k = prompt_int("Number of patches to process (k): ")
    default_pol = prompt_choice("Default polarization if missing", ["H", "V"]).upper()

    debug_mode = prompt_choice("Debug mode?", ["y", "n"]).lower() == "y"
    debug_patch_id = None
    debug_link_index = None
    if debug_mode:
        if k == 1:
            print("k=1 → debugging the single processed patch")
            debug_link_index = prompt_int("Link index to debug: ")
        else:
            debug_patch_id = input("Patch id to debug: ").strip()
            debug_link_index = prompt_int("Link index to debug: ")

    patches = list(load_jsonl(patch_list_path))
    attrs = {_pid(rec): rec for rec in load_jsonl(patch_attr_path) if _pid(rec)}
    links = list(load_jsonl(links_path))

    # Selected patches = those appearing in attrs; keep patch-list order
    selected = [p for p in patches if _pid(p) in attrs]
    selected = selected[:k]

    print(f"Processing {len(selected)} patches")

    if not selected:
        # Helpful hint
        some_patch = _pid(patches[0]) if patches else None
        some_attr = next(iter(attrs.keys())) if attrs else None
        print("No selected patches found.")
        print("Example patch id from patch list:", some_patch)
        print("Example patch id from attributes:", some_attr)
        return

    from rainfall_processing import prepare_rainfall_for_patch
    from link_geometry import translate_and_filter_links_for_patch
    from attenuation import compute_attenuation_for_patch, DebugRequest

    for p in selected:
        pid = _pid(p)
        print(f"[PATCH {pid}] processing")

        # Merge patch base + attributes (attributes may include extra fields)
        merged = dict(attrs.get(pid, {}))
        merged.update(p)

        rain = prepare_rainfall_for_patch(merged)

        rect_rd, links_in_patch = translate_and_filter_links_for_patch(
            links=links,
            patch=merged,
            default_freq_ghz=10.0,
            default_pol=default_pol,
            verbose=True,
        )

        out_path = out_dir / f"patch_{pid}.jsonl"

        dbg = None
        if debug_mode:
            if k == 1:
                dbg = DebugRequest(patch_id=pid, link_index=int(debug_link_index))
            else:
                if (debug_patch_id or "").strip() == pid.strip():
                    dbg = DebugRequest(patch_id=pid, link_index=int(debug_link_index))

        compute_attenuation_for_patch(
            patch=merged,
            rect_rd=rect_rd,
            links_in_patch=links_in_patch,
            refined_smoothed_mmph=rain.refined_smoothed_mmph,
            out_jsonl_path=out_path,
            debug=dbg,
        )

        print(f"[PATCH {pid}] links_in_patch={len(links_in_patch)} wrote {out_path}")


if __name__ == "__main__":
    main()
