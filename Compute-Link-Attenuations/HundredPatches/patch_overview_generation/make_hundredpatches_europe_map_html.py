#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
PATCH_LIST = PROJECT_ROOT / "JSON-files/benchmark-500-files-758-patches.local.jsonl"
HUNDRED_DIR = HERE / "patch_jsonl_files"
OUT = PROJECT_ROOT / "HundredPatches/pipeline/report/images/patch_overview/hundredpatches_europe_overview.html"


def load_patch_metadata() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    with PATCH_LIST.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            pid = str(row.get("id") or "").strip()
            if pid:
                meta[pid] = row
    return meta


def hundred_patch_ids() -> list[str]:
    ids: list[str] = []
    for p in sorted(HUNDRED_DIR.glob("patch_*.jsonl")):
        name = p.name
        ids.append(name[len("patch_"):-len(".jsonl")])
    return ids


def main() -> None:
    meta = load_patch_metadata()
    ids = hundred_patch_ids()
    rows = [meta[pid] for pid in ids if pid in meta]
    if len(rows) != len(ids):
        missing = [pid for pid in ids if pid not in meta]
        raise SystemExit(f"Missing metadata for patch ids: {missing[:5]}")

    patch_rows = []
    for row in rows:
        patch_rows.append(
            {
                "id": row["id"],
                "center_lat": float(row["center_lat"]),
                "center_lon": float(row["center_lon"]),
                "width_km": float(row["width_km"]),
                "height_km": float(row["height_km"]),
                "nearest_city": row.get("nearest_city"),
            }
        )

    data_json = json.dumps(patch_rows, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Geographic Distribution of the 100 Benchmark Patches</title>
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: #f7f4ee;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      color: #222;
    }}
    .wrap {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 18px 18px 24px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 36px;
      line-height: 1.1;
      text-align: center;
      font-weight: 800;
    }}
    .sub {{
      text-align: center;
      font-size: 18px;
      color: #555;
      margin-bottom: 14px;
    }}
    #map {{
      height: 880px;
      border: 1px solid #c8c2b8;
      box-shadow: 0 8px 28px rgba(0,0,0,0.08);
      background: white;
    }}
    .legend {{
      background: rgba(255,255,255,0.92);
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid #d6d0c8;
      box-shadow: 0 4px 14px rgba(0,0,0,0.08);
      font-size: 14px;
      line-height: 1.35;
    }}
    .legend-row {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .legend-box {{
      width: 24px;
      height: 14px;
      border: 2px solid #d6291c;
      background: transparent;
      box-sizing: border-box;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Geographic Distribution of the 100 Benchmark Patches</h1>
    <div class="sub">Each patch is shown as a red outline rectangle over a Europe basemap.</div>
    <div id="map"></div>
  </div>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script>
    const patches = {data_json};

    const map = L.map('map', {{
      zoomSnap: 0.25,
      zoomDelta: 0.25
    }});

    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    function latDegPerKm() {{
      return 1.0 / 111.32;
    }}

    function lonDegPerKm(lat) {{
      return 1.0 / (111.32 * Math.cos(lat * Math.PI / 180.0));
    }}

    const bounds = [];
    for (const p of patches) {{
      const halfLat = 0.5 * p.height_km * latDegPerKm();
      const halfLon = 0.5 * p.width_km * lonDegPerKm(p.center_lat);
      const south = p.center_lat - halfLat;
      const north = p.center_lat + halfLat;
      const west = p.center_lon - halfLon;
      const east = p.center_lon + halfLon;
      const rect = L.rectangle([[south, west], [north, east]], {{
        color: '#d6291c',
        weight: 1.6,
        fill: false,
        opacity: 0.72
      }});
      rect.bindTooltip(
        `<b>${{p.id}}</b><br>` +
        `center: ${{p.center_lat.toFixed(2)}}, ${{p.center_lon.toFixed(2)}}<br>` +
        `size: ${{p.width_km.toFixed(0)}} × ${{p.height_km.toFixed(0)}} km` +
        (p.nearest_city ? `<br>nearest city: ${{p.nearest_city}}` : ''),
        {{sticky: true}}
      );
      rect.addTo(map);
      bounds.push([south, west], [north, east]);
    }}

    map.fitBounds(bounds, {{padding: [18, 18]}});

    const legend = L.control({{position: 'topright'}});
    legend.onAdd = function() {{
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML = `
        <div class="legend-row">
          <div class="legend-box"></div>
          <div>Patch footprint</div>
        </div>
      `;
      return div;
    }};
    legend.addTo(map);
  </script>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
