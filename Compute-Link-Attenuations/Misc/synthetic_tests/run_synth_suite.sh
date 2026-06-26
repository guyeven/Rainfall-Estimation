#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTDIR="$SCRIPT_DIR/out"
mkdir -p "$OUTDIR"

# 0) zeros
python "$SCRIPT_DIR/generate_synth_h5.py" --out_dir "$OUTDIR" --name zeros --pattern zeros --ny 8 --nx 8
python "$SCRIPT_DIR/generate_synth_inputs.py" --out_dir "$OUTDIR/zeros" --h5_path "$OUTDIR/zeros.h5" --patch_id synth_zeros

# 1) uniform10
python "$SCRIPT_DIR/generate_synth_h5.py" --out_dir "$OUTDIR" --name uniform10 --pattern uniform10 --ny 8 --nx 8
python "$SCRIPT_DIR/generate_synth_inputs.py" --out_dir "$OUTDIR/uniform10" --h5_path "$OUTDIR/uniform10.h5" --patch_id synth_uniform10

# 2) half20
python "$SCRIPT_DIR/generate_synth_h5.py" --out_dir "$OUTDIR" --name half20 --pattern half20 --ny 8 --nx 8
python "$SCRIPT_DIR/generate_synth_inputs.py" --out_dir "$OUTDIR/half20" --h5_path "$OUTDIR/half20.h5" --patch_id synth_half20

# 3) impulse100
python "$SCRIPT_DIR/generate_synth_h5.py" --out_dir "$OUTDIR" --name impulse100 --pattern impulse100 --ny 8 --nx 8
python "$SCRIPT_DIR/generate_synth_inputs.py" --out_dir "$OUTDIR/impulse100" --h5_path "$OUTDIR/impulse100.h5" --patch_id synth_impulse100

echo "Now run your pipeline (main.py) four times, pointing to each folder's inputs."
echo "Example for uniform10:"
echo "  Patch list JSONL: $OUTDIR/uniform10/patches.jsonl"
echo "  Patch attrs JSONL: $OUTDIR/uniform10/patch_attrs.jsonl"
echo "  Links JSONL: $OUTDIR/uniform10/links.jsonl"
echo "  Output dir: $OUTDIR/uniform10/results"
echo "  k: 1"
echo "  Default pol: H"
echo "  Debug: y  (patch_id=synth_uniform10, link_index=0)"
