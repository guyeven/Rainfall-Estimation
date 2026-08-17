from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cml_attenuation.config_io import deep_get, load_config_file, resolve_path


class ConfigIoTests(unittest.TestCase):
    def test_json_mapping_and_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            config_path.write_text(json.dumps({"input": {"directory": "data"}}))

            config = load_config_file(config_path)

            self.assertEqual(deep_get(config, "input.directory"), "data")
            self.assertEqual(resolve_path("data", base_dir=root), (root / "data").resolve())

    def test_non_mapping_document_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "top level"):
                load_config_file(path)

    def test_unknown_extension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_config_file("config.txt")


if __name__ == "__main__":
    unittest.main()
