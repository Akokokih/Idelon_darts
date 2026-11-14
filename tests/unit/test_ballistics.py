import math
import unittest
from types import SimpleNamespace
from idleon_darts.ballistics import DiscreteBallisticsModel


class BallisticsTests(unittest.TestCase):
    def test_application_calibration_uses_the_scheduled_release_algorithm(self):
        from idleon_darts.ballistics import application_model
        for scale in (1.,2.5):
            data=application_model('new-profile',scale,38.,47*scale,-2*scale)
            model=DiscreteBallisticsModel(data)
            self.assertEqual(model.profile_id,'new-profile')
            self.assertTrue(model.absolute_mouse_up);self.assertFalse(model.tick_mode)
            self.assertEqual(model.press_lead_ms,30.)
            self.assertEqual(model.forecast_policy,'phase-clock-v2')
            self.assertAlmostEqual(model.target_x_offset,-13*scale)
            self.assertAlmostEqual(model.launch_dx/scale,56.6871557235)

    def model(self):
        return DiscreteBallisticsModel(dict(profile_id='synthetic',scale=1.,launch_dx=110.,launch_dy=-51.))

    def test_discrete_update_order_and_launch_geometry(self):
        model=self.model();visible=model.intrinsic
        # Three updates, with gravity added after each position update.
        y=model.impact((300.,350.),visible,425.,'wind-none')
        self.assertAlmostEqual(y,299.+.033*3)
        model.wind=(6.,3.)
        self.assertAlmostEqual(model.impact((300.,350.),visible,425.,'wind-vector'),299.+(.033+3/750)*3)

    def test_aim_recomputed_for_position_and_diagonal_wind(self):
        model=self.model();target=(916.,310.)
        angles=[]
        for launcher,wind in [((300.,350.),(0.,0.)),((240.,290.),(0.,0.)),((240.,290.),(2.,4.))]:
            model.wind=wind;angle=model.aim_angle(launcher,target,'wind-vector')
            self.assertIsNotNone(angle)
            self.assertLess(abs(model.impact(launcher,angle,target[0],'wind-vector')-target[1]),2.)
            angles.append(angle)
        self.assertGreater(abs(angles[0]-angles[1]),.01)
        self.assertGreater(abs(angles[1]-angles[2]),.001)

    def test_harmonic_forecast_includes_acceleration(self):
        model=self.model();frequency=2.4;phase=2.7
        history=[(int((1+t)*1e9),model.centre+model.amplitude*math.sin(phase+frequency*t))
                 for t in (-.25,-.20,-.15,-.10,-.05,0.)]
        aim=model.centre+model.amplitude*math.sin(phase+frequency*.07)
        crossing,omega,alpha,residual=model.forecast(history,history[-1][1],aim)
        self.assertAlmostEqual(crossing,.07,places=8)
        self.assertLess(omega,0);self.assertNotEqual(alpha,0);self.assertLess(residual,1e-10)

    def test_long_distance_target_with_two_arcs_does_not_require_endpoint_bracketing(self):
        model=DiscreteBallisticsModel(dict(profile_id='synthetic',scale=1.,amplitude_deg=46.,launch_dx=110.,launch_dy=-51.))
        launcher=(100.,350.);target=(916.,310.)
        self.assertGreater(model.impact(launcher,model.centre+model.amplitude-.01,target[0],'wind-none'),target[1])
        angle=model.aim_angle(launcher,target,'wind-none')
        self.assertIsNotNone(angle);self.assertLess(angle,.8)
        self.assertLess(abs(model.impact(launcher,angle,target[0],'wind-none')-target[1]),3.)

    def test_phase_clock_uses_multiple_poses_and_does_not_redate_duplicates(self):
        model=DiscreteBallisticsModel(dict(profile_id='synthetic',scale=1.,phase_clock_base=1.14))
        hits=30*(42-38)/(53-42);frequency=1.14*(1.5+2.1*hits/(hits+25))
        history=[]
        for index in range(21):
            t=-.8+index*.04;phase=3.+frequency*t;angle=model.centre+model.amplitude*math.sin(phase)
            observation=SimpleNamespace(session_id='s',segment_index=1,launcher_position=(100.,200.),
                target_center=(800.,200.),context_key='wind-none',wind_features=(0.,0.),
                arm_angle=angle,arm_direction=1 if math.cos(phase)>0 else -1,
                sample_ns=int((1+t)*1e9),capture_end_ns=int((1+t)*1e9))
            model.observe_motion(observation);history.append((observation.sample_ns,angle))
        count=len(model.phase_samples);last=model.phase_samples[-1]
        observation.sample_ns+=10_000_000;model.observe_motion(observation)
        self.assertEqual(len(model.phase_samples),count);self.assertEqual(model.phase_samples[-1],last)
        aim=model.centre+model.amplitude*math.sin(3.+frequency*.04)
        result=model.forecast(history,history[-1][1],aim)
        self.assertIsNotNone(result);self.assertAlmostEqual(result[0],.04,places=7)
        self.assertLessEqual(model.forecast_horizon_ns,45_000_000)
        self.assertGreaterEqual(model.phase_diagnostics['points'],6)
        observation.target_center=(801.,200.);observation.arm_angle-=.01;model.observe_motion(observation)
        self.assertIsNone(model.clock_forecast(observation.sample_ns,aim))

    def test_discrete_clock_targets_safe_red_ticks_and_scales_delay_with_cadence(self):
        for period in (.020,.025):
            model=DiscreteBallisticsModel(dict(profile_id='synthetic',scale=1.,phase_clock_base=1.14,
                phase_tick_mode=True,tick_delay_fraction=1.6,launch_dx=110.,launch_dy=-51.))
            hits=30*(42-38)/(53-42);step=math.radians(1.3)*(1.5+2.1*hits/(hits+25))
            launcher=(100.,350.);plane=916.
            angles=[model.centre+model.amplitude*math.sin(n*step) for n in (64,65)]
            cy=sum(model.impact(launcher,a,plane,'wind-none') for a in angles)/2
            target=(plane-model.target_x_offset,cy)
            for tick in range(33,63):
                for delta,pose in ((-.003,tick-1),(.003,tick)):
                    phase=pose*step;angle=model.centre+model.amplitude*math.sin(phase)
                    stamp=round((2+tick*period+delta)*1e9)
                    observation=SimpleNamespace(session_id='s',segment_index=1,launcher_position=launcher,
                        target_center=target,context_key='wind-none',wind_features=(0.,0.),target_half_height=30.,
                        arm_angle=angle,arm_direction=1 if math.cos(phase)>0 else -1,sample_ns=stamp,capture_end_ns=stamp)
                    model.observe_motion(observation)
            aim=sum(angles)/2;forecast=model.tick_forecast(stamp,aim)
            self.assertIsNotNone(forecast)
            diagnostic=model.phase_diagnostics
            self.assertGreaterEqual(diagnostic['safe_tick_count'],2)
            self.assertAlmostEqual(diagnostic['tick_period_ms'],period*1000,places=5)
            self.assertAlmostEqual(diagnostic['effective_trigger_delay_ns'],period*1.6*1e9,delta=2)
            self.assertTrue(all(abs(y-cy)<=27. for y in diagnostic['safe_tick_impacts']))
            # A narrow target admits only one lattice pose; another sweep does
            # not guarantee a different lattice alignment.
            single_y=model.impact(launcher,angles[0],plane,'wind-none')
            scene=list(model.phase_scene);scene[3]=(target[0],single_y);model.phase_scene=tuple(scene)
            model.phase_target_half_height=8.
            self.assertIsNotNone(model.tick_forecast(stamp,angles[0]))
            self.assertEqual(model.phase_diagnostics['safe_tick_count'],1)
            fitted=model.fit_tick_clock(stamp)
            model.fit_tick_clock=lambda _:dict(fitted,uncertainty=.004)
            self.assertIsNone(model.tick_forecast(stamp,angles[0]))
            observation.target_half_height=2.;model.observe_motion(observation)
            self.assertIsNone(model.tick_forecast(stamp,aim))
