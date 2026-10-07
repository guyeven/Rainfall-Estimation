#!/usr/bin/env python3
"""
read-links.py

Read either:
  (A) RawCMLdata.zip  -> contains many *.csv.gz raw vendor files
  (B) IDRawCMLdata.zip -> contains IDRawCMLdata.dat (or .dat.gz) in RAINLINK format

Output:
  JSON Lines (.jsonl): one JSON object per UNIQUE link (no duplicates)

Keeps ONLY:
  XStart, YStart, XEnd, YEnd, Frequency, PathLength

Progress:
  Prints "read XXX lines, accumulated YYY links" every 1000 input rows.

Usage:
  python read-links.py /path/to/IDRawCMLdata.zip unique_links.jsonl
  python read-links.py /path/to/RawCMLdata.zip   unique_links.jsonl
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import zipfile
from pathlib import Path

RAINLINK_ORDER = [
    "YStart", "XStart", "YEnd", "XEnd", "Frequency", "DateTime",
    "ES", "SES", "Pmin", "Pmax", "PathLength", "Vendor", "ID"
]


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in km (fast, no external deps)."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def looks_like_header(tokens: list[str]) -> bool:
    # Header typically contains letters; data rows mostly numeric.
    return any(any(c.isalpha() for c in t) for t in tokens)


def open_text_from_zip(zf: zipfile.ZipFile, name: str) -> io.TextIOBase:
    """Open a member from zip as a text stream. If member ends with .gz, gunzip it."""
    raw = zf.open(name)
    if name.endswith(".gz"):
        return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8", errors="replace")
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


def process_processed_dat(
    zf: zipfile.ZipFile,
    dat_name: str,
    out_path: Path,
    coord_round: int,
    report_every: int,
) -> int:
    """
    Process IDRawCMLdata.dat (RAINLINK format): whitespace-delimited.
    Dedup key: (YStart,XStart,YEnd,XEnd)
    """
    seen: set[tuple[float, float, float, float]] = set()
    line_count = 0

    with out_path.open("w", encoding="utf-8") as out, open_text_from_zip(zf, dat_name) as f:
        first = f.readline()
        if not first:
            print("Processed .dat is empty.")
            return 0

        tokens = first.strip().split()
        if not tokens:
            print("First line of processed .dat is blank.")
            return 0

        has_header = looks_like_header(tokens)
        header = tokens if has_header else RAINLINK_ORDER
        idx = {c: i for i, c in enumerate(header)}

        required = ["XStart", "YStart", "XEnd", "YEnd", "Frequency", "PathLength"]
        missing = [c for c in required if c not in idx]
        if missing:
            raise RuntimeError(f"Missing columns in processed file: {missing}. Header={header}")

        def handle(parts: list[str]) -> None:
            xs = round(float(parts[idx["XStart"]]), coord_round)
            ys = round(float(parts[idx["YStart"]]), coord_round)
            xe = round(float(parts[idx["XEnd"]]), coord_round)
            ye = round(float(parts[idx["YEnd"]]), coord_round)

            key = (ys, xs, ye, xe)  # match R grouping order
            if key in seen:
                return
            seen.add(key)

            rec = {
                "XStart": xs,
                "YStart": ys,
                "XEnd": xe,
                "YEnd": ye,
                "Frequency": float(parts[idx["Frequency"]]),
                "PathLength": float(parts[idx["PathLength"]]),
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # If no header, first line was data
        if not has_header:
            line_count += 1
            if line_count % report_every == 0:
                print(f"read {line_count:,} lines, accumulated {len(seen):,} links")
            handle(tokens)

        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split()
            if len(parts) < len(header):
                continue

            line_count += 1
            if line_count % report_every == 0:
                print(f"read {line_count:,} lines, accumulated {len(seen):,} links")

            handle(parts)

    return len(seen)


def process_raw_csv_gz(
    zf: zipfile.ZipFile,
    out_path: Path,
    coord_round: int,
    report_every: int,
) -> int:
    """
    Process raw vendor files (*.csv.gz) inside RawCMLdata.zip.
    Dedup key: (YStart,XStart,YEnd,XEnd) in degrees rounded to coord_round.
    Frequency: kHz -> GHz
    PathLength: computed via haversine (km), rounded to 3 decimals (like R script)
    """
    seen: set[tuple[float, float, float, float]] = set()
    line_count = 0

    with out_path.open("w", encoding="utf-8") as out:
        for name in zf.namelist():
            if not name.endswith(".csv.gz"):
                continue

            with zf.open(name) as zmember, gzip.open(zmember, mode="rt") as gz:
                reader = csv.DictReader(gz)

                for row in reader:
                    line_count += 1
                    if line_count % report_every == 0:
                        print(f"read {line_count:,} lines, accumulated {len(seen):,} links")

                    xs = round(float(row["SITE_LON_SECS"]) / (3600 * 1000), coord_round)
                    ys = round(float(row["SITE_LAT_SECS"]) / (3600 * 1000), coord_round)
                    xe = round(float(row["FAR_END_LON_SECS"]) / (3600 * 1000), coord_round)
                    ye = round(float(row["FAR_END_LAT_SECS"]) / (3600 * 1000), coord_round)

                    key = (ys, xs, ye, xe)
                    if key in seen:
                        continue
                    seen.add(key)

                    freq = float(row["FREQ"]) / 1_000_000  # kHz -> GHz
                    path_len = round(haversine_km(xs, ys, xe, ye), 3)

                    rec = {
                        "XStart": xs,
                        "YStart": ys,
                        "XEnd": xe,
                        "YEnd": ye,
                        "Frequency": freq,
                        "PathLength": path_len,
                    }
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return len(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zipfile", type=Path, help="Path to RawCMLdata.zip or IDRawCMLdata.zip")
    ap.add_argument("output", type=Path, help="Output JSONL file path")
    ap.add_argument("--round", type=int, default=6, help="Round coords to N decimals (default 6)")
    ap.add_argument("--report-every", type=int, default=1000, help="Progress print interval (default 1000)")
    args = ap.parse_args()

    with zipfile.ZipFile(args.zipfile) as zf:
        names = zf.namelist()
        has_raw = any(n.endswith(".csv.gz") for n in names)
        dat_candidates = [n for n in names if n.endswith(".dat") or n.endswith(".dat.gz")]

        if has_raw:
            n = process_raw_csv_gz(zf, args.output, coord_round=args.round, report_every=args.report_every)
            print(f"Done (raw csv.gz). Unique links: {n}")
            return

        if dat_candidates:
            dat_name = dat_candidates[0]  # usually just one
            n = process_processed_dat(zf, dat_name, args.output, coord_round=args.round, report_every=args.report_every)
            print(f"Done (processed {dat_name}). Unique links: {n}")
            return

        print("No *.csv.gz or *.dat/*.dat.gz found in the ZIP. Nothing to do.")
        print("First 30 entries:")
        for n in names[:30]:
            print(" ", n)


if __name__ == "__main__":
    main()
