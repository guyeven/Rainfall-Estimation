"""ITU-R P.838-3 rain specific attenuation wrapper.

We copy/adapt the implementation from the provided ITU code and expose
one small function:
    gamma_db_per_km(freq_ghz, rain_mmph, pol_hv)

where pol_hv is 'H' or 'V'.
"""

from __future__ import annotations

from typing import Literal

from itu_r_p_8383 import gamma_specific

PolHV = Literal["H", "V"]


def gamma_db_per_km(freq_ghz: float, rain_mmph: float, pol: PolHV) -> float:
    """Specific attenuation gamma_R in dB/km.

    Args:
      freq_ghz: frequency in GHz
      rain_mmph: rain rate in mm/h
      pol: 'H' or 'V'
    """
    pol_s = "horizontal" if pol == "H" else "vertical"
    return float(gamma_specific(float(freq_ghz), float(rain_mmph), pol_s))
