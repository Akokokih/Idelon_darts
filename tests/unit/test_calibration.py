from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from idleon_darts.calibration import load_profile
from tests.unit.helpers import profile


class CalibrationTests(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'profile.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            return load_profile(path)

    def test_valid_profile_roundtrip(self):
        self.assertEqual(self.load(asdict(profile())), profile())

    def test_rejects_unrecognised_fields_schema_and_noninteger_geometry(self):
        for changes in [dict(extra='ignored?'), dict(schema_version=3),
                        dict(dpi=True), dict(roi=dict(left=1.5, top=2, width=2, height=2))]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.load(asdict(profile()) | changes)

    def test_rejects_missing_fields_and_duplicate_json_keys(self):
        data = asdict(profile())
        del data['roi']
        with self.assertRaises(ValueError):
            self.load(data)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'profile.json'
            path.write_text('{"dpi": 96, "dpi": 144}')
            with self.assertRaises(ValueError):
                load_profile(path)
