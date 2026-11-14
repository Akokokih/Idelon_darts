import math
import tempfile
from pathlib import Path
import unittest


class ImpactModelTests(unittest.TestCase):
    def test_accelerating_sweep_predicts_quadratic_crossing_and_rejects_turnaround(self):
        from idleon_darts.prediction import fit_impact_model, ReleasePredictor, fit_angular_motion, angular_crossing_time
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model=fit_impact_model(self.samples(),profile_id='synthetic',trigger_delay_ns=20_000_000,target_x_offset=-31.5)
        calibrated=replace(profile(),model_version=model.version,calibration_coverage=('wind-none',))
        aim=model.aim_angle((100.,200.),(700.,200.),'wind-none')
        predictor=ReleasePredictor(model,hold_ns=1_000_000)
        newest=1_200_000_000;omega=-1.4;alpha=-6.;theta=aim+.0447
        for i in range(10):
            end=newest-(9-i)*20_000_000;t=(end-newest)/1e9
            obs=observation(observation_id=str(i),capture_start_ns=end-1_000_000,capture_end_ns=end,
                            launcher_position=(100.,200.),target_center=(731.5,200.),target_half_height=20.,
                            arm_angle=theta+omega*t+.5*alpha*t*t,arm_direction=-1,context_key='wind-none')
            result=predictor.predict(obs,calibrated,now_ns=end)
            if i<9:self.assertIsNone(result)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.release_ns,newest+9_000_000,delta=10)
        fitted=fit_angular_motion(predictor.history)
        self.assertAlmostEqual(fitted[0],omega,places=7)
        self.assertAlmostEqual(fitted[1],alpha,places=7)
        self.assertTrue(predictor.last_motion['used_acceleration'])
        self.assertAlmostEqual(angular_crossing_time(theta,aim,omega,alpha),.03,places=8)
        self.assertIsNone(angular_crossing_time(.1,0.,-1.,10.))
        self.assertIsNone(angular_crossing_time(1.,0.,-1.,0.))
        self.assertEqual(fit_angular_motion(list(predictor.history)[:9])[1],0.)
        self.assertIsNone(fit_angular_motion(list(predictor.history)[:3]))
        noisy=[(n,a+(.02 if i%2 else -.02)) for i,(n,a) in enumerate(predictor.history)]
        self.assertIsNone(fit_angular_motion(noisy))
        # A phase correction must not postpone the command past a reversal,
        # even when the virtual aiming-angle crossing was on the descending arc.
        phased=replace(model,contexts={'wind-none':model.contexts['wind-none'] |
                       dict(phase_correction_ns=45_000_000,end_to_end_uncertainty_px=5.)})
        predictor=ReleasePredictor(phased,hold_ns=1_000_000)
        for i in range(10):
            end=newest-(9-i)*20_000_000;t=(end-newest)/1e9
            obs=replace(obs,observation_id=f'reversal-{i}',capture_start_ns=end-1_000_000,capture_end_ns=end,
                        arm_angle=aim-.0029-.2*t+9*t*t)
            result=predictor.predict(obs,calibrated,now_ns=end)
        self.assertTrue(predictor.last_motion['used_acceleration'])
        self.assertIsNone(result)

    def test_noisy_acceleration_uses_stable_speed_and_scene_changes_discard_motion(self):
        from idleon_darts.prediction import fit_angular_motion, fit_impact_model, ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        history=[]
        for i in range(10):
            t=(i-9)*.02
            history.append((1_000_000_000+i*20_000_000,.4-t+(.001 if i%2 else -.001)))
        motion=fit_angular_motion(history)
        self.assertIsNotNone(motion)
        self.assertEqual(motion[1],0.)
        model=fit_impact_model(self.samples(),profile_id='synthetic',trigger_delay_ns=20_000_000)
        model=replace(model,contexts=model.contexts | {'wind-diagonal':model.contexts['wind-none'].copy()})
        calibrated=replace(profile(),model_version=model.version,calibration_coverage=tuple(model.contexts))
        predictor=ReleasePredictor(model)
        for i,(stamp,angle) in enumerate(history):
            obs=observation(observation_id=str(i),capture_start_ns=stamp-1_000_000,capture_end_ns=stamp,
                            launcher_position=(100.,200.),target_center=(700.,200.),target_half_height=20.,
                            arm_angle=angle,arm_direction=-1,context_key='wind-none')
            predictor.predict(obs,calibrated,now_ns=stamp)
        changed=replace(obs,context_key='wind-diagonal',capture_start_ns=stamp+19_000_000,
                        capture_end_ns=stamp+20_000_000,arm_angle=angle-.02)
        self.assertIsNone(predictor.predict(changed,calibrated,now_ns=changed.capture_end_ns))
        self.assertEqual(len(predictor.history),1)
        self.assertIsNone(predictor.last_motion)

    def test_analytic_inverse_finds_both_arcs_without_endpoint_bracketing(self):
        from idleon_darts.prediction import ImpactModel
        case = dict(gain=1., curvature=.0005, dx_min=600., dx_max=600.,
                    angle_min=0., angle_max=1.29, sample_count=4,
                    loo_max_error_px=0., uncertainty_px=5.)
        model = ImpactModel('synthetic', {'wind-none':case})
        # Both interval endpoints miss below the centre; the lower arc still hits.
        self.assertGreater(model.impact((0.,0.), 0., 600., 'wind-none'), 0.)
        self.assertGreater(model.impact((0.,0.), 1.29, 600., 'wind-none'), 0.)
        angle = model.aim_angle((0.,0.), (600.,0.), 'wind-none')
        self.assertAlmostEqual(model.impact((0.,0.), angle, 600., 'wind-none'), 0., places=8)
        self.assertLess(angle, .5)
        self.assertIsNone(model.aim_angle((0.,0.), (600.,-1000.), 'wind-none'))
        restricted = ImpactModel('synthetic', {'wind-none':case | dict(angle_min=.5, angle_max=.6)})
        self.assertIsNone(restricted.aim_angle((0.,0.), (600.,0.), 'wind-none'))

    def test_context_phase_postpones_command_and_preserves_joint_uncertainty(self):
        from idleon_darts.prediction import fit_impact_model, ImpactModel, ReleasePredictor, load_impact_model
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        base = fit_impact_model(self.samples(), profile_id='synthetic',
                                trigger_delay_ns=20_000_000, target_x_offset=-31.5)
        model = replace(base, contexts={'wind-none':base.contexts['wind-none'] |
            dict(phase_correction_ns=45_000_000, end_to_end_uncertainty_px=85.)})
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'phase.json';model.save(p)
            self.assertEqual(load_impact_model(p), model)
        calibrated=replace(profile(), model_version=model.version, calibration_coverage=('wind-none',))
        aim=model.aim_angle((100.,200.),(700.,200.),'wind-none')
        predictor=ReleasePredictor(model, hold_ns=1_000_000)
        for i in range(10):
            end=1_000_000_000+i*10_000_000
            obs=observation(observation_id=str(i),capture_start_ns=end-1_000_000,capture_end_ns=end,
                            launcher_position=(100.,200.),target_center=(731.5,200.),target_half_height=20.,
                            arm_angle=aim+.085-i*.01,arm_direction=-1,context_key='wind-none')
            result=predictor.predict(obs,calibrated,now_ns=end)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.release_ns,end+19_000_000,delta=10)
        self.assertEqual(result.uncertainty_radius,85.)
        # Timing fields are paired, bounded and unavailable to the historical model.
        for extra in (dict(phase_correction_ns=1),
                      dict(phase_correction_ns=100_000_001,end_to_end_uncertainty_px=5.),
                      dict(phase_correction_ns=True,end_to_end_uncertainty_px=5.),
                      dict(phase_correction_ns=0,end_to_end_uncertainty_px=float('nan'))):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                replace(base,contexts={'wind-none':base.contexts['wind-none'] | extra})

    def test_flight_track_measures_launch_angle_and_rejects_bad_tracks(self):
        from idleon_darts.prediction import fit_launch_track
        angle = .3
        points = [(100.+x, 180.-math.tan(angle)*x+.0002*x*x) for x in range(150,1000,50)]
        result = fit_launch_track(points, (100.,200.))
        self.assertAlmostEqual(result['launch_angle'], angle, places=7)
        self.assertLess(result['residual_p95_px'], .001)
        # The yellow landmark can remain on the animated throwing hand initially.
        attached = [(210., 280.), (250., 270.), (290., 260.)]
        airborne = [p for p in points if p[0] > 300.]
        measured = fit_launch_track(attached + airborne, (100.,200.))
        self.assertAlmostEqual(measured['launch_angle'], angle, places=7)
        self.assertEqual(measured['excluded_near_launcher_points'], 3)
        for bad in (points[:4], points[::-1], [points[0]]*10,
                    [(x,y+(20 if i%2 else -20)) for i,(x,y) in enumerate(points)]):
            with self.subTest(points=bad), self.assertRaises(ValueError):
                fit_launch_track(bad, (100.,200.))

    def test_fresh_poses_separated_by_repeated_renders_can_predict(self):
        from idleon_darts.prediction import fit_impact_model, ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model=fit_impact_model(self.samples(),profile_id='synthetic',
                               trigger_delay_ns=20_000_000,target_x_offset=-31.5)
        calibrated=replace(profile(),model_version=model.version,calibration_coverage=('wind-none',))
        predictor=ReleasePredictor(model,hold_ns=1_000_000)
        aim=model.aim_angle((100.,200.),(700.,200.),'wind-none')
        for i in range(19):
            end=1_000_000_000+i*10_000_000
            obs=observation(observation_id=str(i),capture_start_ns=end-1_000_000,capture_end_ns=end,
                            launcher_position=(100.,200.),target_center=(731.5,200.),target_half_height=20.,
                            arm_angle=aim+.22-(i//2)*.02,arm_direction=-1,context_key='wind-none')
            result=predictor.predict(obs,calibrated,now_ns=end)
            if i%2:
                self.assertIsNone(result)
                self.assertEqual(predictor.history[-1][0],end-10_000_000)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.release_ns,end+19_000_000,delta=10)
        self.assertEqual(len(predictor.history),10)

    def samples(self):
        rows = []
        for x, y, degrees in [(100, 200, 5), (120, 220, 10), (80, 210, 15), (110, 190, 20), (90, 230, 25)]:
            angle = math.radians(degrees)
            dx = 700 - x
            impact = y - 1.05 * dx * math.tan(angle) + .0002 * (dx / math.cos(angle)) ** 2
            rows.append(dict(context='wind-none', launcher_x=x, launcher_y=y,
                             release_angle=angle, impact_x=700., impact_y=impact))
        return rows

    def test_fit_and_json_roundtrip_with_measured_error(self):
        from idleon_darts.prediction import fit_impact_model, load_impact_model
        model = fit_impact_model(self.samples(), profile_id='synthetic')
        case = model.contexts['wind-none']
        self.assertAlmostEqual(case['gain'], 1.05, places=5)
        self.assertAlmostEqual(case['curvature'], .0002, places=7)
        self.assertLess(case['loo_max_error_px'], .001)
        angle = model.aim_angle((100., 200.), (700., 200.), 'wind-none')
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(model.impact((100., 200.), angle, 700., 'wind-none'), 200., places=4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model.json'
            model.save(path)
            self.assertEqual(load_impact_model(path).profile_id, 'synthetic')

    def test_unknown_wind_and_outside_coverage_never_use_zero_wind_model(self):
        from idleon_darts.prediction import fit_impact_model
        model = fit_impact_model(self.samples(), profile_id='synthetic')
        self.assertIsNone(model.aim_angle((100., 200.), (700., 200.), 'wind-up'))
        self.assertIsNone(model.aim_angle((-1000., 200.), (700., 200.), 'wind-none'))

    def test_refuse_insufficient_degenerate_nonfinite_and_unphysical_samples(self):
        from idleon_darts.prediction import fit_impact_model
        for rows in [self.samples()[:3], [self.samples()[0]] * 5,
                     [self.samples()[0] | dict(impact_y=float('nan'))] + self.samples()[1:],
                     [r | dict(impact_y=-1e6) for r in self.samples()]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                fit_impact_model(rows, profile_id='synthetic')

    def test_release_forecast_and_unknown_context_abstention(self):
        from idleon_darts.prediction import fit_impact_model, ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model = fit_impact_model(self.samples(), profile_id='synthetic')
        calibrated = replace(profile(), model_version=model.version, calibration_coverage=('wind-none',))
        aim = model.aim_angle((100., 200.), (700., 200.), 'wind-none')
        predictor = ReleasePredictor(model)
        for i in range(4):
            end = 1_000_000_000 + i * 10_000_000
            obs = observation(observation_id=str(i), capture_start_ns=end-1_000_000, capture_end_ns=end,
                              launcher_position=(100.,200.), target_center=(700.,200.),
                              arm_angle=aim+.07-i*.01, arm_direction=-1, context_key='wind-none')
            result = predictor.predict(obs, calibrated, now_ns=end)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.release_ns, end+20_000_000, delta=10)
        self.assertIsNone(predictor.predict(replace(obs, context_key='unseen-wind'), calibrated, now_ns=end))
        self.assertIsNone(predictor.predict(replace(obs, arm_direction=1), calibrated, now_ns=end))

    def test_native_input_overhead_advances_command_without_changing_phase_delay(self):
        from types import SimpleNamespace
        from idleon_darts.prediction import ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model=SimpleNamespace(profile_id='synthetic',version='discrete-ballistics-v1',
            contexts={'wind-none':{}},clock_base=1.14,trigger_delay_ns=20_000_000,
            target_x_offset=0.,input_overhead_ns=0,forecast_horizon_ns=45_000_000,
            aim_angle=lambda *args:.2,forecast=lambda *args:(.04,-1.,0.,0.),
            effective_uncertainty=lambda context:100.)
        calibrated=replace(profile(),model_version=model.version)
        obs=observation(capture_start_ns=999_000_000,capture_end_ns=1_000_000_000,
            arm_angle=.24,arm_direction=-1,context_key='wind-none')
        original=ReleasePredictor(model,hold_ns=1_000_000).predict(obs,calibrated,now_ns=1_000_000_000)
        model.input_overhead_ns=8_000_000
        revised=ReleasePredictor(model,hold_ns=1_000_000).predict(obs,calibrated,now_ns=1_000_000_000)
        self.assertIsNotNone(original);self.assertIsNotNone(revised)
        self.assertEqual(original.release_ns-revised.release_ns,8_000_000)
        self.assertEqual(model.trigger_delay_ns,20_000_000)

    def test_unarmed_auto_test_does_not_construct_native_adapter(self):
        from idleon_darts.cli import main
        from unittest.mock import patch
        from contextlib import redirect_stdout
        import io
        with patch('idleon_darts.native_input.WindowsInputAdapter') as inputs, redirect_stdout(io.StringIO()):
            result = main(['auto-test', '--window-id', '123', '--calibration', 'missing',
                           '--model', 'missing', '--output', 'missing'])
        self.assertEqual(result, 0)
        inputs.assert_not_called()

    def test_measured_delay_projection_and_scene_changes(self):
        from idleon_darts.prediction import fit_impact_model, load_impact_model, ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model = fit_impact_model(self.samples(), profile_id='synthetic',
                                 trigger_delay_ns=20_000_000, target_x_offset=-31.5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'model.json'; model.save(path)
            self.assertEqual(load_impact_model(path), model)
        calibrated = replace(profile(), model_version=model.version, calibration_coverage=('wind-none',))
        aim = model.aim_angle((100.,200.), (700.,200.), 'wind-none')
        predictor = ReleasePredictor(model, hold_ns=1_000_000)
        for i in range(10):
            end = 1_000_000_000+i*10_000_000
            obs = observation(observation_id=str(i), capture_start_ns=end-1_000_000,
                              capture_end_ns=end, launcher_position=(100.,200.),
                              target_center=(731.5,200.), target_half_height=20.,
                              arm_angle=aim+.13-i*.01, arm_direction=-1, context_key='wind-none')
            result = predictor.predict(obs, calibrated, now_ns=end)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.release_ns, end+19_000_000, delta=10)
        self.assertEqual(result.uncertainty_axis, 'vertical')
        moved = replace(obs, capture_start_ns=end+9_000_000, capture_end_ns=end+10_000_000,
                        launcher_position=(110.,200.), arm_angle=obs.arm_angle-.01)
        self.assertIsNone(predictor.predict(moved, calibrated, now_ns=moved.capture_end_ns))
        self.assertEqual(len(predictor.history), 1)

    def test_game_pose_repeats_are_not_retimestamped_and_jumps_reset_forecast(self):
        from idleon_darts.prediction import fit_impact_model, ReleasePredictor
        from tests.unit.helpers import profile, observation
        from dataclasses import replace
        model = fit_impact_model(self.samples(), profile_id='synthetic', trigger_delay_ns=20_000_000)
        calibrated = replace(profile(), model_version=model.version, calibration_coverage=('wind-none',))
        for delta in (0., -.2):
            predictor = ReleasePredictor(model)
            for i, angle in enumerate((.5,.48,.46,.46+delta)):
                end = 1_000_000_000+i*20_000_000
                obs = observation(capture_start_ns=end-1_000_000,capture_end_ns=end,
                                  launcher_position=(100.,200.), target_center=(700.,200.),
                                  arm_angle=angle, arm_direction=-1, context_key='wind-none')
                result = predictor.predict(obs, calibrated, now_ns=end)
            self.assertIsNone(result)
            self.assertEqual(len(predictor.history), 3 if delta == 0. else 1)
            if delta == 0.:
                self.assertEqual(predictor.history[-1][0], end-20_000_000)
                # Repeated render poses cannot keep a stalled forecast alive.
                stale=replace(obs,capture_start_ns=end+60_000_000,capture_end_ns=end+61_000_000)
                self.assertIsNone(predictor.predict(stale,calibrated,now_ns=stale.capture_end_ns))
                self.assertEqual(len(predictor.history),1)
