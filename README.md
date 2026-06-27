# Rainfall Estimation from Commercial Microwave Links

This repository contains an end-to-end workflow for building rainfall-reconstruction experiments from radar-derived rainfall patches and commercial microwave-link (CML) geometries.

## Repository Layout

- `Compute-Link-Attenuations/` contains the main numerical pipeline: forward attenuation modeling, interpolation baselines, inverse solvers, batch analysis, and report rendering.
- `Links-4TU-NL/` contains utilities and a small frontend for inspecting the 4TU-NL microwave-link data source.
- `Patch-Generator/` contains tools for selecting and inspecting radar-derived rainfall patches.
- `Link-Generator/` contains tools for generating and visualizing synthetic link geometries.
- `ITU-Calculator/` contains a small calculator/API for ITU-R P.838-3 rain-attenuation coefficients.
- `Misc/` contains auxiliary analysis artifacts and helper code that may have informed interpretation or write-up decisions, but are not part of the runnable pipeline.
- `Latex/` contains the LaTeX source and generated PDF for the write-up of results from the 100-patch benchmark experiments.

## Where To Start

The maintained benchmark lives under `Compute-Link-Attenuations/HundredPatches/`. That folder contains the 100-patch benchmark inputs, solver configurations, generated solution files, analysis/report configuration, and the report artifacts used to inspect the solver outputs.

For the already-existing 100-patch benchmark, start with `Compute-Link-Attenuations/README.md`. It explains how to run the configured solvers, rebuild the analysis cache, and render the report.

For creating or inspecting upstream inputs, use the folder-specific READMEs:

- `Patch-Generator/README.md` explains how candidate radar-derived rainfall patches are selected and exported.
- `Links-4TU-NL/README.md` explains how the 4TU-NL link data is converted and inspected.
- `Link-Generator/README.md` explains the separate synthetic-link geometry tool.
- `ITU-Calculator/README.md` explains how to query ITU-R rain-attenuation coefficients.

The intended flow is:

1. Select or inspect rainfall patches with `Patch-Generator/`.
2. Prepare or inspect CML link geometries with `Links-4TU-NL/` or, for synthetic experiments, `Link-Generator/`.
3. Run the maintained reconstruction benchmark from `Compute-Link-Attenuations/HundredPatches/pipeline/`.
4. Use `Compute-Link-Attenuations/HundredPatches/pipeline/report/` for result inspection.

The pipeline uses six solver outputs: IDW, ILDW, Solver(ILDW), Convex Solver, Homotopy Solver, and Solver(GT). When modifying or re-running the project, it is reasonable to use AI coding agents such as Codex to help navigate the scripts and configs, but the commands and expected inputs are documented in the folder READMEs so the workflow is not dependent on an agent.
