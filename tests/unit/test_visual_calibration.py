"""Entirely synthetic images, created in temporary external directories."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

HAS_VISION = importlib.util.find_spec('cv2') is not None and importlib.util.find_spec('numpy') is not None


@unittest.skipUnless(HAS_VISION, 'Installer l extra vision pour ces tests')
class VisualTests(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np
        from idleon_darts.models import Rect, WindowContext
        self.cv, self.np = cv2, np
        self.region = Rect(0, 0, 400, 300)
        self.context = WindowContext(123, self.region, 144, True, True)
        self.regions = dict(arm=Rect(85, 20, 180, 215), board=Rect(330, 30, 50, 200),
                            anchor=Rect(10, 240, 60, 40), wind_none=Rect(10, 10, 75, 25))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'visual'

    def image(self, angle):
        image = self.np.zeros((300, 400, 3), dtype='uint8')
        for y in range(240, 280, 4):
            image[y:y + 2, 10:70] = (50, 140, 210)
        self.cv.putText(image, 'None', (12, 29), self.cv.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
        image[100:130, 340:370] = (25, 35, 240)
        endpoints = [(round(100 + r * math.cos(angle)), round(190 - r * math.sin(angle))) for r in (60, 160)]
        self.cv.line(image, *endpoints, (220, 220, 220), 7)
        return image

    def frame(self, angle, index=1):
        from idleon_darts.capture import Frame
        return Frame(str(index), index * 20_000_000, index * 20_000_000 + 1_000_000,
                     self.region, self.image(angle).tobytes())

    def build(self):
        from idleon_darts.calibration import calibrate_visual
        return calibrate_visual((self.frame(float(angle), i + 1) for i, angle in
                                 enumerate(self.np.linspace(-.25, 1., 40))),
                                self.context, self.regions, self.output)

    def test_pivot_and_target_are_measured_without_arming_a_model(self):
        calibration = self.build()
        self.assertAlmostEqual(calibration.pivot[0], 100, delta=2)
        self.assertAlmostEqual(calibration.pivot[1], 190, delta=2)
        self.assertEqual(calibration.target_size, (30, 30))
        self.assertFalse(calibration.profile.calibrated)
        self.assertEqual(calibration.profile.calibration_coverage, ())
        self.assertTrue((self.output / 'reference.png').is_file())

    def test_roundtrip_and_untrusted_metadata_rejected(self):
        from idleon_darts.calibration import load_visual_calibration
        original = self.build()
        loaded = load_visual_calibration(self.output)
        self.assertEqual(loaded.pivot, original.pivot)
        path = self.output / 'visual.json'
        data = json.loads(path.read_text())
        data['pivot'][0] = float('nan')
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_visual_calibration(self.output)

    def test_static_or_missing_blade_refuses_calibration(self):
        from idleon_darts.calibration import calibrate_visual
        for angle in [0., None]:
            frames = []
            for i in range(40):
                frame = self.frame(angle or 0., i + 1)
                if angle is None:
                    from dataclasses import replace
                    image = self.image(0.)
                    image[20:235, 85:265] = 0
                    frame = replace(frame, bgr=image.tobytes())
                frames.append(frame)
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                calibrate_visual(frames, self.context, self.regions, self.output)
        self.assertFalse(self.output.exists())

    def test_templates_do_not_turn_unknown_wind_into_zero(self):
        from idleon_darts.perception import CalibratedPerception
        from dataclasses import replace
        detector = CalibratedPerception(self.build())
        first = detector.detect(self.frame(.1, 50), detector.profile, session_id='synthetic', segment_index=1)
        self.assertEqual(first.wind_features, (0.,))
        self.assertIsNone(first.arm_direction)
        second = detector.detect(self.frame(.2, 51), detector.profile, session_id='synthetic', segment_index=1)
        self.assertEqual(second.arm_direction, 1)
        self.assertAlmostEqual(second.arm_angle, .2, delta=.025)
        self.assertEqual(second.target_center, (355., 115.))
        image = self.image(.3)
        image[10:35, 10:85] = 0
        unknown = detector.detect(replace(self.frame(.3, 52), bgr=image.tobytes()), detector.profile,
                                  session_id='synthetic', segment_index=1)
        self.assertIsNone(unknown.wind_features)
        self.assertIsNone(unknown.context_key)
        self.assertIn('wind-unknown', unknown.invalid_reasons)

    def test_missing_target_anchor_and_history_gap_abstain(self):
        from idleon_darts.perception import CalibratedPerception
        from dataclasses import replace
        detector = CalibratedPerception(self.build())
        detector.detect(self.frame(.1, 50), detector.profile, session_id='synthetic', segment_index=1)
        image = self.image(.2)
        image[100:130, 340:370] = 0
        image[240:280, 10:70] = 0
        result = detector.detect(replace(self.frame(.2, 51), bgr=image.tobytes()), detector.profile,
                                 session_id='synthetic', segment_index=1)
        self.assertIsNone(result.launcher_position)
        self.assertIsNone(result.target_center)
        self.assertFalse(result.complete)
        detector.detect(self.frame(.3, 52), detector.profile, session_id='synthetic', segment_index=1)
        result = detector.detect(self.frame(.4, 70), detector.profile, session_id='synthetic', segment_index=1)
        self.assertIsNone(result.arm_direction)

    def test_annotated_wind_matches_uniquely_and_conflicts_abstain(self):
        from idleon_darts.perception import CalibratedPerception
        from dataclasses import replace
        calibration = self.build()
        image = self.image(.2)
        image[10:35, 10:85] = 0
        self.cv.putText(image, '4 >', (12,29), self.cv.FONT_HERSHEY_SIMPLEX, .5, (255,255,255), 1)
        self.cv.imwrite(str(self.output/'wind-right-4mph.png'), image[10:35,10:85])
        entry = dict(key='wind-right-4mph', region=dict(left=10,top=10,width=75,height=25),
                     features=[4.,0.], threshold=.99)
        library = self.output/'wind-library.json'
        library.write_text(json.dumps([entry]))
        detector = CalibratedPerception(calibration)
        frame = replace(self.frame(.2, 50), bgr=image.tobytes())
        result = detector.detect(frame, detector.profile, session_id='wind', segment_index=1)
        self.assertEqual(result.context_key, 'wind-right-4mph')
        self.assertEqual(result.wind_features, (4.,0.))
        self.cv.imwrite(str(self.output/'wind-other.png'), image[10:35,10:85])
        library.write_text(json.dumps([entry, entry | dict(key='wind-other')]))
        detector = CalibratedPerception(calibration)
        result = detector.detect(frame, detector.profile, session_id='wind', segment_index=1)
        self.assertIsNone(result.context_key)
        self.assertIn('wind-unknown', result.invalid_reasons)

    def test_two_targets_and_ambiguous_blades_are_unknown(self):
        from idleon_darts.vision import find_red_target, find_blade
        image = self.image(.1)
        image[160:190, 340:370] = (25, 35, 240)
        self.assertIsNone(find_red_target(image, self.regions['board']))
        image = self.image(.1)
        self.cv.line(image, (110, 100), (210, 100), (220, 220, 220), 7)
        self.assertIsNone(find_blade(image, self.regions['arm']))

    def test_launcher_translation_is_measured_from_anchor(self):
        from idleon_darts.perception import CalibratedPerception
        from idleon_darts.vision import crop
        from dataclasses import replace
        detector = CalibratedPerception(self.build())
        original = self.image(.3)
        moved = original.copy()
        for key in ('arm', 'anchor'):
            region = self.regions[key]
            moved[region.top:region.top + region.height, region.left:region.left + region.width] = 0
        for key in ('arm', 'anchor'):
            region = self.regions[key]
            moved[region.top - 10:region.top - 10 + region.height,
                  region.left + 20:region.left + 20 + region.width] = crop(original, region)
        result = detector.detect(replace(self.frame(.3, 60), bgr=moved.tobytes()), detector.profile,
                                 session_id='translated', segment_index=1)
        self.assertIsNotNone(result.launcher_position)
        self.assertAlmostEqual(result.launcher_position[0], 120, delta=2)
        self.assertAlmostEqual(result.launcher_position[1], 180, delta=2)
        self.assertAlmostEqual(result.arm_angle, .3, delta=.03)

    def test_partial_red_target_does_not_move_the_calibrated_center(self):
        from idleon_darts.perception import CalibratedPerception
        from dataclasses import replace
        detector = CalibratedPerception(self.build())
        image = self.image(.2)
        image[100:108, 340:370] = 0
        result = detector.detect(replace(self.frame(.2, 50), bgr=image.tobytes()), detector.profile,
                                 session_id='occluded', segment_index=1)
        self.assertIsNone(result.target_center)
        self.assertIn('target-unknown', result.invalid_reasons)

    def test_no_private_captures_written_inside_repository(self):
        from idleon_darts.calibration import calibrate_visual
        output = Path(__file__).resolve().parents[2] / 'forbidden-visual-calibration'
        with self.assertRaisesRegex(ValueError, 'exterieur'):
            calibrate_visual([], self.context, self.regions, output)
        self.assertFalse(output.exists())

    def test_live_check_refuses_dpi_change_before_grabbing(self):
        from contextlib import redirect_stderr
        from dataclasses import replace
        from unittest.mock import patch
        from idleon_darts.cli import main
        import io
        self.build()
        with patch('idleon_darts.windows_io.WindowsDesktop') as desktop, \
                patch('idleon_darts.capture.WindowsFrameSource') as source, redirect_stderr(io.StringIO()):
            desktop.return_value.snapshot.return_value = replace(self.context, dpi=192)
            self.assertEqual(main(['check-calibration', '--window-id', '123', '--calibration',
                                   str(self.output), '--delay', '0']), 1)
            source.assert_not_called()

    def test_live_check_reports_observations_without_sending_inputs(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        from idleon_darts.cli import main
        import io
        self.build()
        out = io.StringIO()
        with patch('idleon_darts.windows_io.WindowsDesktop') as desktop, \
                patch('idleon_darts.capture.WindowsFrameSource') as source, redirect_stdout(out):
            desktop.return_value.snapshot.return_value = self.context
            source.return_value.__enter__.return_value.grab.side_effect = [self.frame(.1, 50), self.frame(.2, 51)]
            self.assertEqual(main(['check-calibration', '--window-id', '123', '--calibration',
                                   str(self.output), '--frames', '2', '--delay', '0']), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report['frames'], 2)
        self.assertEqual(report['counts']['arm_angle'], 2)
        self.assertFalse(report['inputs_sent'])
