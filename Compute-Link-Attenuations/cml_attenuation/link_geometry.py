# link_geometry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from pyproj import Transformer

# WGS84 -> RD (EPSG:28992)
_TO_RD = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)

# Anchor Q: NW corner in WGS84 used to "hang" the 4TU patch
# (You can change these if you use a different anchor)
ANCHOR_NW_LON = 4.5
ANCHOR_NW_LAT = 52.4


@dataclass(frozen=True)
class PatchRectRD:
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def width_m(self) -> float:
        return self.x_max - self.x_min

    @property
    def height_m(self) -> float:
        return self.y_max - self.y_min

    def contains(self, x: float, y: float) -> bool:
        # boundary counts as inside
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


def _pid(patch: Dict) -> str:
    return str(patch.get("id") or patch.get("patch_id") or "").strip()


def patch_rect_rd(patch: Dict) -> PatchRectRD:
    """
    Compute patch rectangle in RD meters (EPSG:28992).

    Real patches (your patch generator JSONL) provide:
      - center_lon, center_lat (WGS84 degrees)
      - width_km, height_km

    We treat the patch as axis-aligned in RD, centered at projected center.
    """
    lon_c = float(patch["center_lon"])
    lat_c = float(patch["center_lat"])
    x_c, y_c = _TO_RD.transform(lon_c, lat_c)

    width_m = float(patch["width_km"]) * 1000.0
    height_m = float(patch["height_km"]) * 1000.0

    x_min = x_c - 0.5 * width_m
    x_max = x_c + 0.5 * width_m
    y_min = y_c - 0.5 * height_m
    y_max = y_c + 0.5 * height_m

    return PatchRectRD(x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max)


def translation_vector_rd(patch: Dict) -> Tuple[float, float]:
    """
    Translation vector t = P - Q in RD meters, where:
      - P = NW corner of the patch in RD meters
      - Q = fixed anchor point (ANCHOR_NW_LON/LAT) in RD meters

    Links are projected into RD and then translated by t to "glue" them onto the patch.
    """
    rect = patch_rect_rd(patch)
    px, py = rect.x_min, rect.y_max  # NW corner in RD

    qx, qy = _TO_RD.transform(ANCHOR_NW_LON, ANCHOR_NW_LAT)

    return px - qx, py - qy


def _get_link_lonlat(link: Dict) -> Tuple[float, float, float, float]:
    # 4TU JSONL uses XStart/YStart etc; X=lon, Y=lat
    return (
        float(link["XStart"]),
        float(link["YStart"]),
        float(link["XEnd"]),
        float(link["YEnd"]),
    )


def _get_freq_pol(
    link: Dict,
    default_freq_ghz: float,
    default_pol: str,
    link_index: int,
    verbose: bool,
) -> Tuple[float, str]:
    freq_val = link.get("Frequency", None)
    pol_val = link.get("Polarization", None)

    # Frequency (GHz in your JSON)
    if freq_val is None:
        freq_ghz = float(default_freq_ghz)
        if verbose:
            print(f"Missing frequency for link index {link_index}. Using default {freq_ghz} GHz.")
    else:
        freq_ghz = float(freq_val)

    # Polarization
    if pol_val is None:
        pol = default_pol
        if verbose:
            print(f"Missing polarization for link index {link_index}. Using default {pol}.")
    else:
        pol = str(pol_val).upper()
        if pol not in ("H", "V"):
            if verbose:
                print(f"Unrecognized polarization '{pol}' for link index {link_index}. Using default {default_pol}.")
            pol = default_pol

    return freq_ghz, pol


def translate_and_filter_links_for_patch(
    links: List[Dict],
    patch: Dict,
    default_freq_ghz: float,
    default_pol: str,
    verbose: bool = True,
) -> Tuple[PatchRectRD, List[Dict]]:
    """
    Project 4TU links (WGS84) -> RD, translate by (P-Q), then keep only links
    whose *translated endpoints* are inside the patch rectangle.

    Output link dict adds:
      - orig_index (index in input links list)
      - xs_m, ys_m, xe_m, ye_m (translated RD meters)
      - freq_ghz (GHz), pol ('H'/'V')
    """
    rect = patch_rect_rd(patch)
    tx, ty = translation_vector_rd(patch)

    out: List[Dict] = []
    for idx, link in enumerate(links):
        lon_s, lat_s, lon_e, lat_e = _get_link_lonlat(link)
        xs, ys = _TO_RD.transform(lon_s, lat_s)
        xe, ye = _TO_RD.transform(lon_e, lat_e)

        xs_t, ys_t = xs + tx, ys + ty
        xe_t, ye_t = xe + tx, ye + ty

        # both endpoints inside (boundary inclusive)
        if not rect.contains(xs_t, ys_t):
            continue
        if not rect.contains(xe_t, ye_t):
            continue

        freq_ghz, pol = _get_freq_pol(
            link=link,
            default_freq_ghz=default_freq_ghz,
            default_pol=default_pol,
            link_index=idx,
            verbose=verbose,
        )

        d = dict(link)
        d.update(
            {
                "orig_index": idx,
                "xs_m": float(xs_t),
                "ys_m": float(ys_t),
                "xe_m": float(xe_t),
                "ye_m": float(ye_t),
                "freq_ghz": float(freq_ghz),
                "pol": pol,
            }
        )
        out.append(d)

    return rect, out
