from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import _benchmark_path


class BenchmarkPathTests(unittest.TestCase):
    def test_listed_npz_filename_is_not_double_suffixed(self) -> None:
        path = _benchmark_path("example.npz")
        self.assertEqual(path.name, "example.npz")

    def test_parent_components_are_discarded(self) -> None:
        path = _benchmark_path("../../example.npz")
        self.assertEqual(path.name, "example.npz")


if __name__ == "__main__":
    unittest.main()
