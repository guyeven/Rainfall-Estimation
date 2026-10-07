# Synthetic Tests

This folder contains small controlled rainfall/link fixtures for debugging the attenuation-input generation path. It is not part of the maintained 100-patch benchmark pipeline.

The synthetic rainfall fields are simple toy patterns, such as:

- `zeros`,
- `uniform10`,
- `half20`,
- `impulse100`.

These fixtures were useful for checking whether generated links, patch metadata, HDF5 rainfall inputs, and debug attenuation traces behaved as expected on tiny examples.

## Files

- `generate_synth_h5.py`: writes a tiny HDF5 rainfall field for a selected toy pattern.
- `generate_synth_inputs.py`: creates patch/link JSONL inputs around a synthetic HDF5 field.
- `generate_disjoint_links.py`: helper for creating controlled disjoint link layouts.
- `run_synth_suite.sh`: regenerates the toy synthetic inputs under `out/`.
- `out/`: committed example synthetic outputs and debug traces.

## Usage

From `Compute-Link-Attenuations/`, run:

```bash
bash Misc/synthetic_tests/run_synth_suite.sh
```

The script writes outputs under `Misc/synthetic_tests/out/` and prints example values to provide to `main.py` if you want to run the normal input-generation path on one synthetic case.

## Status

Use these files for controlled debugging only. They are not used by the configured 100-patch benchmark.
