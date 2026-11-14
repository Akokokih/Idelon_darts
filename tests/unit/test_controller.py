from dataclasses import replace
import unittest
from idleon_darts.controller import Controller
from idleon_darts.models import Rect, Result, State
from tests.unit.helpers import context, observation, prediction, profile


class ControllerTests(unittest.TestCase):
    def test_supervised_uncertain_shot_keeps_centre_context_and_freshness_guards(self):
        c=Controller(profile(),min_confidence=.9,require_centre_precision=False)
        self.arm(c)
        self.assertTrue(self.ready(c,pred=prediction(uncertainty_radius=100.)).allowed)
        self.assertFalse(self.ready(c,pred=prediction(predicted_impact=(500.,500.),uncertainty_radius=100.)).allowed)
        self.assertFalse(self.ready(c,obs=observation(invalid_reasons=('wind-unknown',))).allowed)

    def test_vertical_collision_projection_uses_measured_height_and_still_checks_alignment(self):
        for axis, height, x, uncertainty, allowed in [
                ('vertical', 20., 300., 15., True),
                ('radial', 20., 300., 15., False),
                ('vertical', None, 300., 15., False),
                ('vertical', 20., 301., 15., False),
                ('vertical', 20., 300., 21., False)]:
            with self.subTest(axis=axis, height=height, x=x, uncertainty=uncertainty):
                c = self.make(); self.arm(c)
                decision = self.ready(c, obs=observation(target_half_height=height),
                                      pred=prediction(uncertainty_axis=axis,
                                                      predicted_impact=(x, 200.),
                                                      uncertainty_radius=uncertainty))
                self.assertEqual(decision.allowed, allowed)

    def make(self):
        return Controller(profile(), min_confidence=0.9, result_timeout_ns=10_000_000)

    def arm(self, c):
        c.arm(context(), now_ns=0)

    def ready(self, c, obs=None, pred=None, ctx=None, now=3_000_000):
        return c.evaluate(obs or observation(), pred or prediction(), ctx or context(), now_ns=now)

    def test_starts_paused_and_requires_arm(self):
        c = self.make()
        self.assertEqual(c.state, State.PAUSED)
        self.assertFalse(self.ready(c).allowed)
        c.arm(context(), now_ns=3_000_000)
        self.assertTrue(self.ready(c).allowed)

    def test_profile_must_be_calibrated_before_arm(self):
        for changes in [dict(model_version=None), dict(calibration_coverage=())]:
            c = Controller(replace(profile(), **changes), min_confidence=0.9)
            with self.assertRaises(ValueError):
                self.arm(c)
            self.assertEqual(c.state, State.PAUSED)

    def test_focus_geometry_dpi_and_identity_each_suspend(self):
        for changes in [dict(foreground=False), dict(game_visible=False), dict(dpi=96),
                        dict(rect=Rect(1, 0, 1000, 800)), dict(window_id=99)]:
            with self.subTest(changes=changes):
                c = self.make()
                self.arm(c)
                self.assertFalse(self.ready(c, ctx=context(**changes)).allowed)
                self.assertEqual(c.state, State.PAUSED)
                self.assertFalse(self.ready(c).allowed)  # No automatic resumption.

    def test_future_stale_and_slow_grab_suspend(self):
        for obs, now in [(observation(), 1_000_000),
                         (observation(), 102_000_001),
                         (observation(capture_start_ns=0, capture_end_ns=101_000_000), 101_000_000)]:
            with self.subTest(now=now):
                c = self.make()
                self.arm(c)
                self.assertFalse(self.ready(c, obs=obs, now=now).allowed)
                self.assertEqual(c.state, State.PAUSED)

    def test_missing_low_confidence_and_out_of_coverage_suspend(self):
        cases = [dict(wind_features=None), dict(arm_direction=None), dict(target_center=None),
                 dict(context_key='unseen'), dict(confidence=0.5), dict(invalid_reasons=('occluded',))]
        for change in cases:
            with self.subTest(change=change):
                c = self.make()
                self.arm(c)
                self.assertFalse(self.ready(c, obs=observation(**change)).allowed)
                self.assertEqual(c.state, State.PAUSED)

    def test_prediction_identity_coverage_and_timing_checked(self):
        cases = [dict(model_version='other'), dict(observation_id='old'),
                 dict(profile_id='other'), dict(context_key='other'),
                 dict(predicted_impact=(320., 200.)), dict(uncertainty_radius=20.),
                 dict(release_ns=4_000_000), dict(valid_until_ns=2_000_000, release_ns=2_000_000)]
        for change in cases:
            with self.subTest(change=change):
                c = self.make()
                self.arm(c)
                self.assertFalse(self.ready(c, pred=prediction(**change)).allowed)

    def test_no_prediction_cannot_authorise_a_shot(self):
        c = self.make()
        self.arm(c)
        self.assertFalse(c.evaluate(observation(), None, context(), now_ns=3_000_000).allowed)

    def test_reservation_rechecks_current_window_and_prevents_double_shot(self):
        c = self.make()
        self.arm(c)
        self.assertTrue(self.ready(c).allowed)
        self.assertFalse(c.reserve_shot('shot1', observation(), prediction(),
                                        context(foreground=False), now_ns=3_000_001).allowed)
        self.assertIsNone(c.pending_shot_id)
        c.arm(context(), now_ns=3_000_002)
        self.assertTrue(c.reserve_shot('shot1', observation(), prediction(), context(),
                                       now_ns=3_000_003).allowed)
        self.assertFalse(c.reserve_shot('shot2', observation(), prediction(), context(),
                                        now_ns=3_000_004).allowed)
        self.assertEqual(c.pending_shot_id, 'shot1')

    def test_pause_and_timeout_preserve_unresolved_shot(self):
        for timeout in (False, True):
            c = self.make()
            self.arm(c)
            c.reserve_shot('shot1', observation(), prediction(), context(), now_ns=3_000_000)
            if timeout:
                self.ready(c, now=13_000_001)
            else:
                c.pause('user')
            self.assertEqual(c.state, State.PAUSED)
            with self.assertRaises(ValueError):
                c.arm(context(), now_ns=14_000_000)
            c.confirm_result('shot1', Result.UNKNOWN, now_ns=15_000_000)
            self.assertEqual(c.state, State.PAUSED)
            self.assertIsNone(c.pending_shot_id)

    def test_confirmation_requires_new_observation_and_matches_shot_id(self):
        c = self.make()
        self.arm(c)
        c.reserve_shot('shot1', observation(), prediction(), context(), now_ns=3_000_000)
        with self.assertRaises(ValueError):
            c.confirm_result('wrong', Result.CENTRE, now_ns=3_500_000)
        c.confirm_result('shot1', Result.CENTRE, now_ns=4_000_000)
        self.assertEqual(c.state, State.OBSERVING)
        self.assertFalse(self.ready(c, now=4_000_001).allowed)

    def test_stop_is_terminal_and_time_cannot_go_backwards(self):
        c = self.make()
        self.arm(c)
        self.ready(c)
        with self.assertRaises(ValueError):
            self.ready(c, now=2_999_999)
        self.assertEqual(c.state, State.PAUSED)
        c.stop()
        with self.assertRaises(ValueError):
            c.arm(context(), now_ns=5_000_000)
