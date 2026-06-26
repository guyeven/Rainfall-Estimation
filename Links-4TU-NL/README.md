# Links-4TU-NL

Utilities and data helpers for the 4TU-NL commercial microwave-link data source. The link data provides realistic CML endpoints, lengths, and frequencies. In the maintained 100-patch workflow, these geometries are used as realistic link-network structure and are placed into selected radar-derived patch coordinate systems before simulated attenuations are generated.

## Contents

- `read-links.py`: converts raw 4TU/RAINLINK ZIP files into a deduplicated JSONL of unique links.
- `unique_links.jsonl`: deduplicated link records used by the helper tools.
- `LIST-OF-LINKS.jsonl`: link list used by the maintained attenuation pipeline.
- `patch-links-filter.py`: FastAPI backend for filtering links inside a rectangular patch footprint.
- `patch-map-frontend/`: React/Vite frontend for inspecting patch/link maps.
- `phase1_links_map.py`: script for creating static Folium HTML maps.
- `phase1_all_links*.html`: generated static map outputs.

## Python Setup

From the repository root:

```bash
cd Links-4TU-NL
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Convert Raw Link Data

If you have a raw ZIP from the 4TU/RAINLINK data source, convert it to a unique-link JSONL with:

```bash
python read-links.py /path/to/IDRawCMLdata.zip unique_links.jsonl
```

or:

```bash
python read-links.py /path/to/RawCMLdata.zip unique_links.jsonl
```

The output is one JSON object per unique physical link, keeping only:

```text
XStart, YStart, XEnd, YEnd, Frequency, PathLength
```

## Static Map Generation

To create or refresh a static map of all links:

```bash
python phase1_links_map.py
```

This produces HTML files that can be opened directly in a browser, such as `phase1_all_links.html` or the rectangle-overlay variants if enabled in the script.

## Run The Patch/Link Filter Backend

```bash
LINKS_JSONL=/full/path/to/unique_links.jsonl uvicorn patch-links-filter:app --host 127.0.0.1 --port 8300 --reload
```

If `LINKS_JSONL` is omitted, the backend looks for `unique_links.jsonl` in this folder. The main endpoint is:

```text
http://127.0.0.1:8300/patch?width_km=50&height_km=50
```

It returns the rectangle bounds and all links whose two endpoints fall inside the rectangle.

## Run The Frontend

In another terminal:

```bash
cd Links-4TU-NL/patch-map-frontend
npm install
npm run dev
```

Open the Vite URL printed by the command, usually:

```text
http://127.0.0.1:5173
```

Keep the backend running on port `8300` while using the frontend.

## Relation To The Main Pipeline

This folder prepares and inspects link records. The numerical rainfall-reconstruction workflow itself is in `Compute-Link-Attenuations/HundredPatches/pipeline/`.

AI coding agents such as Codex can help adapt the scripts to a different link-data export, but verify coordinate conventions and units carefully: link endpoints are stored as longitude/latitude, while some filtering computations project them to meters.
