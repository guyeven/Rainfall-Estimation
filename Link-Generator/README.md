# Link-Generator

Utilities for generating and inspecting synthetic microwave-link geometries. This tool is separate from the maintained 100-patch benchmark, which uses 4TU-derived link geometries under `Compute-Link-Attenuations/HundredPatches/`. Use this folder when you want to experiment with generated link layouts and frequency feasibility.

## Contents

- `backend/`: FastAPI backend that generates link geometries and assigns/checks frequencies using ITU-style attenuation limits.
- `frontend/`: React/Vite interface for visual inspection and parameter tweaking.
- `backend/requirements.txt`: Python dependencies for the backend.
- `backend/install-and-run-commands.txt`: older short command notes; the commands below are the maintained version.

## Setup And Run The Backend

From the repository root:

```bash
cd Link-Generator/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8100
```

The main backend endpoint is:

```text
POST http://127.0.0.1:8100/generate_links
```

It accepts geometry parameters such as patch width/height, grid scale, candidate frequencies, rain-rate assumptions, attenuation limit, and optional random seed. The response contains generated points, links, link lengths, and assigned/allowed frequencies.

## Setup And Run The Frontend

In another terminal:

```bash
cd Link-Generator/frontend
npm install
npm run dev
```

The Vite dev server uses port `5175` according to `package.json`:

```text
http://127.0.0.1:5175
```

Keep the backend running on port `8100` while using the frontend.

## Expected Workflow

1. Start the backend.
2. Start the frontend.
3. Adjust link-generation parameters in the UI.
4. Inspect the generated network visually and/or use the backend JSON response for downstream experiments.

The generated layouts are exploratory. They are not required to reproduce the maintained 100-patch benchmark in `Compute-Link-Attenuations/HundredPatches/pipeline/`.

AI coding agents such as Codex can be useful for modifying the generation rules or adding export formats, but check generated geometries and parameter meanings manually before using them in experiments.

## Browser Preview

After following the backend and frontend instructions above, the browser app should open to a parameter form for generating synthetic link layouts:

![Link Generator browser preview](docs/link-generator-screenshot.png)
