from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from dataclasses import dataclass
from unittest.mock import Mock,patch
from contextlib import ExitStack,redirect_stdout
import io,json,unittest
from tests.unit.helpers import profile,context,observation,prediction
from idleon_darts.capture import Frame
from idleon_darts.windows_io import InputReceipt


class FastSeriesTests(unittest.TestCase):
    def test_settled_score_ends_recording_early_and_shared_capture_stays_open(self):
        from idleon_darts.auto_test import run
        @dataclass
        class Calibration:
            profile: object
            directory: Path
        with TemporaryDirectory() as directory,ExitStack() as stack:
            clock=[1_000_000_000];p=profile();pixels=bytes(p.roi.width*p.roi.height*3)
            def now():clock[0]+=1_000_000;return clock[0]
            source=SimpleNamespace(close=Mock());frames=[]
            def grab():
                clock[0]+=50_000_000
                frame=Frame(str(len(frames)),clock[0]-1_000_000,clock[0],p.roi,pixels,clock[0]);frames.append(frame);return frame
            source.grab=grab
            detector=SimpleNamespace(detect=lambda f,*a,**k:observation(observation_id=f.frame_id,
                capture_start_ns=f.start_ns,capture_end_ns=f.end_ns,sample_ns=f.sample_ns,
                arm_direction=-1,target_half_height=20.))
            model=SimpleNamespace(profile_id=p.profile_id,version='discrete-ballistics-v1',contexts={'wind-zero':{}},
                trigger_delay_ns=0,target_x_offset=0.,aim_angle=lambda *a:.1)
            predictor=SimpleNamespace(last_motion=None,predict=lambda o,prof,now_ns:prediction(
                observation_id=o.observation_id,model_version=model.version,release_ns=now_ns,valid_until_ns=now_ns+20_000_000))
            adapter=SimpleNamespace(stopped=lambda:False,release_all=Mock(),release_shot=lambda *a,**k:InputReceipt('one',now(),now(),None))
            patches={
                'load_visual_calibration':Calibration(p,Path(directory)),
                'load_impact_model':model,'ReleasePredictor':predictor,
                'WindowsDesktop':SimpleNamespace(snapshot=lambda:context()),'WindowsInputAdapter':adapter}
            for name,value in patches.items():stack.enter_context(patch('idleon_darts.auto_test.'+name,return_value=value))
            stack.enter_context(patch('idleon_darts.auto_test.perf_counter_ns',side_effect=now))
            stack.enter_context(patch('idleon_darts.auto_test.annotate_observation',return_value=None))
            stack.enter_context(patch('cv2.imwrite',return_value=True))
            args=SimpleNamespace(arm=True,output=str(Path(directory)/'attempt'),calibration='profile',model='model',
                window_id=12,hold_ms=1,click_x=400,click_y=300,max_wait=1.,supervised_calibration=True,
                record_flight=False,frame_source=source,detector_instance=detector,
                result_reader=SimpleNamespace(score=lambda _:5,lives=lambda _:3),before_score=0,before_lives=3)
            with redirect_stdout(io.StringIO()):self.assertEqual(run(args),0)
            report=json.loads((Path(args.output)/'test.json').read_text())
            self.assertTrue(report['result_settled']);self.assertEqual(report['settled_score'],5)
            self.assertEqual(len(frames),3);source.close.assert_not_called()
