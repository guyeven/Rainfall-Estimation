#!/usr/bin/env python3
import argparse
from pathlib import Path
import h5py
import numpy as np

def write_h5(path: Path, arr: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.create_dataset("/dataset1/data1/data", data=arr.astype(np.float32))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--name", required=True, help="base name, without extension")
    ap.add_argument("--ny", type=int, default=8)
    ap.add_argument("--nx", type=int, default=8)
    ap.add_argument("--pattern", required=True, choices=["zeros", "uniform10", "half20", "impulse100"])
    args = ap.parse_args()

    ny, nx = args.ny, args.nx
    a = np.zeros((ny, nx), dtype=float)

    if args.pattern == "zeros":
        pass
    elif args.pattern == "uniform10":
        a[:] = 10.0
    elif args.pattern == "half20":
        a[:, nx//2:] = 20.0
    elif args.pattern == "impulse100":
        a[ny//2, nx//2] = 100.0

    out = Path(args.out_dir) / f"{args.name}.h5"
    write_h5(out, a)
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
