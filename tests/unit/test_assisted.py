from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile
import unittest

from idleon_darts.assisted import AssistedService, assess, selection_rect, region_plan
from idleon_darts.models import Rect
from idleon_darts.prediction import ImpactModel
from tests.unit.helpers import observation, profile


class AssistedTests(unittest.TestCase):
    def model(self):
        case=dict(gain=1.,curvature=.0002,dx_min=600.,dx_max=600.,angle_min=0.,angle_max=.6,
                  sample_count=4,loo_max_error_px=0.,uncertainty_px=5.)
        return ImpactModel('synthetic',{'wind-none':case},'empirical-launch-v2',20_000_000,-31.5)

    def obs(self):
        return observation(launcher_position=(100.,200.),target_center=(731.5,200.),target_half_height=20.,
                           arm_direction=-1,context_key='wind-none')

    def test_canvas_drag_preserves_scale_letterbox_and_reverse_direction(self):
        self.assertEqual(selection_rect((120,70),(220,120),(1000,600),(20,20,.5)),Rect(200,100,200,100))
        self.assertEqual(selection_rect((220,120),(120,70),(1000,600),(20,20,.5)),Rect(200,100,200,100))
        for a,b in [((0,0),(220,120)),((120,70),(121,71))]:
            with self.assertRaises(ValueError):selection_rect(a,b,(1000,600),(20,20,.5))

    def test_guided_regions_are_inside_scene_and_mapped_to_screen(self):
        regions=dict(scene=Rect(20,30,800,500),arm=Rect(40,60,100,100),board=Rect(700,60,80,400),
                     anchor=Rect(40,200,100,20),wind_none=Rect(300,50,80,30))
        absolute,relative=region_plan(regions,Rect(100,200,1000,700))
        self.assertEqual(absolute,Rect(120,230,800,500));self.assertEqual(relative['arm'],Rect(20,30,100,100))
        with self.assertRaises(ValueError):region_plan(regions | dict(board=Rect(810,60,80,400)),Rect(0,0,1000,700))
        with self.assertRaises(ValueError):region_plan({'scene':regions['scene']},Rect(0,0,1000,700))

    def test_assessment_covers_ready_pending_unknown_wind_margin_and_position(self):
        cal=SimpleNamespace(profile=profile());model=self.model();obs=self.obs()
        self.assertTrue(assess(cal,model,obs)['ready'])
        self.assertFalse(assess(cal,model,obs,pending=True)['ready'])
        self.assertEqual(assess(cal,None,obs)['title'],'Modèle de tir nécessaire')
        self.assertEqual(assess(cal,model,replace(obs,context_key='wind-new'))['title'],'Vent non calibré')
        self.assertFalse(assess(cal,model,replace(obs,invalid_reasons=('wind-unknown',)))['ready'])
        high=replace(model,contexts={'wind-none':model.contexts['wind-none'] |
                                    dict(phase_correction_ns=15_000_000,end_to_end_uncertainty_px=65.)})
        uncertain=assess(cal,high,obs)
        self.assertTrue(uncertain['ready']);self.assertTrue(uncertain['supervised_only'])
        self.assertIn('aim_degrees',uncertain)
        self.assertEqual(assess(cal,model,replace(obs,launcher_position=(-1000.,200.)))['title'],'Position non calibrée')
        with self.assertRaises(ValueError):assess(cal,replace(model,profile_id='other'),obs)

    def test_cancelled_operation_never_focuses_or_captures(self):
        with tempfile.TemporaryDirectory() as tmp,patch('idleon_darts.assisted.focus_game') as focus:
            service=AssistedService(tmp);cancel=Event();cancel.set()
            with self.assertRaises(RuntimeError):service.capture(12,cancel)
            focus.assert_not_called()

    def test_settings_are_local_and_invalid_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=AssistedService(tmp);self.assertEqual(service.load_settings(),{})
            service.save_settings('profile-path','model-path')
            self.assertEqual(service.load_settings(),dict(calibration='profile-path',model='model-path'))
            (Path(tmp)/'settings.json').write_text('{"schema_version":99}')
            with self.assertRaises(ValueError):service.load_settings()

    def test_calibration_requires_zero_wind_annotation_before_desktop(self):
        with tempfile.TemporaryDirectory() as tmp,patch('idleon_darts.assisted.focus_game') as focus:
            with self.assertRaises(ValueError):AssistedService(tmp).calibrate(12,{},Rect(0,0,100,100),False,Event())
            focus.assert_not_called()

    def test_supervised_shot_pending_and_foreign_model_never_focus_game(self):
        with tempfile.TemporaryDirectory() as tmp,patch('idleon_darts.assisted.focus_game') as focus, \
                patch('idleon_darts.assisted.load_visual_calibration') as cal, \
                patch('idleon_darts.assisted.load_impact_model') as model:
            service=AssistedService(tmp);cal.return_value=SimpleNamespace(directory=Path(tmp),profile=profile())
            model.return_value=self.model();(Path(tmp)/'pending-shot.json').write_text('{}')
            with self.assertRaises(ValueError):service.shoot(12,'profile','model',Event())
            model.return_value=replace(self.model(),profile_id='different')
            with self.assertRaises(ValueError):service.shoot(12,'profile','model',Event())
            focus.assert_not_called()

    def test_supervised_backend_calls_one_shot_only_and_uses_roi_relative_click(self):
        with tempfile.TemporaryDirectory() as tmp,patch('idleon_darts.assisted.focus_game'), \
                patch('idleon_darts.assisted.load_visual_calibration') as cal, \
                patch('idleon_darts.assisted.load_impact_model',return_value=self.model()), \
                patch('idleon_darts.auto_test.run') as run:
            service=AssistedService(tmp);cal.return_value=SimpleNamespace(directory=Path(tmp),profile=profile())
            def output(args):
                self.assertTrue(args.arm);self.assertEqual((args.click_x,args.click_y),(400,300))
                path=Path(args.output);path.mkdir(parents=True)
                (path/'test.json').write_text(json.dumps(dict(inputs_sent=True,pending_result=True)))
            run.side_effect=output
            result=service.shoot(12,'profile','model',Event())
            self.assertTrue(result['pending']);self.assertTrue(result['inputs_sent']);run.assert_called_once()

    def test_gui_command_is_dispatched_without_arming(self):
        from idleon_darts.cli import main
        with patch('idleon_darts.gui.main',return_value=0) as launch:
            self.assertEqual(main(['gui','--data-dir','external']),0)
            self.assertFalse(hasattr(launch.call_args.args[0],'arm'))
