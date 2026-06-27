# Compute-Link-Attenuations Misc

This folder contains auxiliary code and artifacts that are useful for debugging, exploratory checks, or small controlled experiments. These files are not part of the maintained 100-patch benchmark pipeline.

The maintained pipeline remains under `../HundredPatches/pipeline/`, with entry points documented in `../README.md`.

## Contents

- `fullarea_d3_links/`: standalone helper for mosaicking patch-level distance-to-third-closest-link bins and overlaying retained links across a larger area.
- `link_diagnostics_report/`: a one-off diagnostic report script for inspecting per-link attenuation errors and related link-crowding summaries.
- `synthetic_tests/`: small synthetic rainfall/link fixtures used for controlled checks of attenuation and input-generation behavior.
