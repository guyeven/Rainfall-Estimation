from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cities import CITY_COORDS, EU_CITIES, nearest_city


class NearestCityTests(unittest.TestCase):
    def test_every_catalogue_city_has_coordinates(self) -> None:
        self.assertTrue(EU_CITIES)
        self.assertTrue(all(name in CITY_COORDS for name, _ in EU_CITIES))

    def test_prefers_regional_city_over_distant_capital(self) -> None:
        self.assertEqual(nearest_city(52.0907, 5.1214), "Utrecht:NL")
        self.assertEqual(nearest_city(50.8503, 4.3517), "Brussels:BE")

    def test_uses_geographic_distance(self) -> None:
        self.assertEqual(nearest_city(48.2082, 16.3738), "Vienna:AT")


if __name__ == "__main__":
    unittest.main()
