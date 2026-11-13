from dataclasses import replace
import math
import unittest
from idleon_darts.models import Rect
from tests.unit.helpers import observation, profile


class ModelTests(unittest.TestCase):
    def test_rect_is_physical_integer_geometry(self):
        r = Rect(-100, 0, 10, 20)
        self.assertTrue(r.contains(Rect(-99, 1, 1, 1)))
        self.assertFalse(r.contains(Rect(-91, 1, 2, 1)))
        for values in [(0, 0, 0, 1), (0, 0, -1, 2), (True, 0, 1, 2), (0., 0, 1, 2)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                Rect(*values)

    def test_profile_requires_valid_roi_dpi_and_schema(self):
        for changes in [dict(roi=Rect(999, 0, 2, 2)), dict(dpi=0),
                        dict(schema_version=2), dict(schema_version=True),
                        dict(calibration_coverage=('x', 'x'))]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(profile(), **changes)

    def test_unknown_wind_is_distinct_from_zero_wind(self):
        self.assertEqual(observation().wind_features, (0.,))
        self.assertIsNone(observation(wind_features=None).wind_features)

    def test_bad_time_confidence_and_nonfinite_coordinates_rejected(self):
        for changes in [dict(capture_start_ns=3_000_000), dict(capture_end_ns=True),
                        dict(confidence=1.1), dict(confidence=math.nan),
                        dict(arm_angle=math.inf), dict(target_radius=-1),
                        dict(target_center=(math.nan, 1.)), dict(arm_direction=0),
                        dict(wind_features=())]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                observation(**changes)
