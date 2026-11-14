from pathlib import Path
from tempfile import TemporaryDirectory
import csv,hashlib,io,json,unittest,zipfile
from idleon_darts.session_export import export_session
from idleon_darts.shot_recording import FlightRecorder
from idleon_darts.capture import Frame
from idleon_darts.models import Rect


class SeriesDataTests(unittest.TestCase):
    def test_export_preserves_evidence_and_excludes_unrelated_files(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)/'series';shot=root/'attempt-0001';shot.mkdir(parents=True)
            report=dict(before_observation=dict(launcher_position=[100.,200.],target_center=[800.,200.],
                wind_features=[2.,3.],arm_angle=.2,capture_start_ns=10,capture_end_ns=20),
                receipt=dict(down_ns=40,up_ns=50),prediction=dict(release_ns=35),angular_motion=dict(omega_rad_s=-1.))
            (shot/'test.json').write_text(json.dumps(report));(shot/'before-raw.png').write_bytes(b'frame')
            (root/'private-unrelated.txt').write_text('not part of the session')
            state=dict(state='complete',shots=1,bullseyes=1,lives_lost=0,rate=1.,results=[dict(number=1,
                result='centre',before_score=0,after_score=5,lives_lost=0,output=str(shot))])
            (root/'state.json').write_text(json.dumps(state));destination=Path(temp)/'analysis.zip'
            result=export_session(root,destination);self.assertEqual(result['shots'],1)
            with zipfile.ZipFile(destination) as archive:
                self.assertIsNone(archive.testzip());self.assertNotIn('private-unrelated.txt',archive.namelist())
                rows=list(csv.DictReader(io.StringIO(archive.read('shots.csv').decode('utf-8-sig'))))
                self.assertEqual(rows[0]['actual_up_ns'],'50');self.assertEqual(rows[0]['wind_y'],'3.0')
                self.assertIn('sans garantie de 90',archive.read('ANALYSIS.md').decode())
                manifest=json.loads(archive.read('manifest.json'))
                for item in manifest['files']:
                    self.assertEqual(hashlib.sha256(archive.read(item['path'])).hexdigest(),item['sha256'])
            with self.assertRaises(FileExistsError):export_session(root,destination)
            with self.assertRaises(ValueError):export_session(root,root/'recursive.zip')

    def test_flight_recording_is_bounded_and_keeps_original_times(self):
        recorder=FlightRecorder();region=Rect(10,20,160,90)
        for index in range(80):
            stamp=index*50_000_000
            recorder.add(Frame(str(index),stamp,stamp+1,region,b'\x20\x30\x40'*(160*90),stamp),(100.,50.))
        self.assertEqual(len(recorder.frames),48)
        with TemporaryDirectory() as directory:
            self.assertEqual(recorder.save(directory),48)
            data=json.loads((Path(directory)/'flight.json').read_text())
            self.assertEqual(data['frames'][1]['sample_ns'],50_000_000)
            self.assertEqual(data['frames'][0]['crop']['left'],20)
            self.assertTrue((Path(directory)/data['frames'][0]['image']).exists())
        disabled=FlightRecorder(False)
        disabled.add(Frame('x',0,1,region,b'\0'*(160*90*3)),(100.,50.))
        self.assertEqual(disabled.frames,[])
