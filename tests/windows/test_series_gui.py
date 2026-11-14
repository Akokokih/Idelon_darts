from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import time,unittest
from idleon_darts.assisted import AssistedService


class SeriesGuiTests(unittest.TestCase):
    def test_minimal_view_hides_advanced_and_prepares_on_first_launch(self):
        import tkinter as tk
        from idleon_darts.gui import AssistedApp
        try:root=tk.Tk();root.withdraw()
        except tk.TclError as exc:self.skipTest(str(exc))
        try:
            with TemporaryDirectory() as directory,patch('idleon_darts.gui.list_game_windows',return_value=[dict(id=123,title='Synthetic Idleon')]):
                class Service(AssistedService):
                    def auto_calibrate(self,window,cancel):
                        self.prepared=True
                        return dict(kind='auto-calibration',calibration='new-profile',model='new-model')
                    def continuous(self,window,profile,model,cancel,on_progress,max_shots,record_flight):
                        self.called=(profile,model,max_shots)
                        return dict(kind='continuous',state='complete',shots=1,bullseyes=1,rate=1.,lives_lost=0,output=str(Path(directory)/'series'))
                service=Service(directory);app=AssistedApp(root,service)
                self.assertEqual(app.advanced_window.state(),'withdrawn')
                self.assertEqual(app.loop_button.cget('text'),'Préparer et lancer')
                app.load_profile=lambda path,persist=True:setattr(app,'calibration_path',path)
                app.load_model=lambda path,persist=True:setattr(app,'model_path',path)
                app.series_count.set('1');app.continuous()
                deadline=time.monotonic()+2
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
                self.assertFalse(app.busy);self.assertTrue(service.prepared)
                self.assertEqual(service.called,('new-profile','new-model',1))
                self.assertEqual(app.advanced_window.state(),'withdrawn')
                self.assertEqual(app.calibration_path,'new-profile')
                app.open_advanced();root.update_idletasks()
                self.assertEqual(app.advanced_window.state(),'normal')
                app.advanced_window.withdraw()
                self.assertFalse(app.closing)
        finally:root.destroy()

    def test_start_series_collects_automatically_and_remembers_export_session(self):
        import tkinter as tk
        from idleon_darts.gui import AssistedApp
        try:root=tk.Tk();root.withdraw()
        except tk.TclError as exc:self.skipTest(str(exc))
        try:
            with TemporaryDirectory() as directory,patch('idleon_darts.gui.list_game_windows',return_value=[dict(id=123,title='Synthetic Idleon')]):
                class Service(AssistedService):
                    def continuous(self,window,profile,model,cancel,on_progress,max_shots,record_flight):
                        self.called=(window,max_shots,record_flight)
                        output=str(Path(directory)/'series')
                        on_progress(dict(message='Deux tirs enregistrés',shots=2,rate=.5,lives_lost=0,output=output))
                        return dict(kind='continuous',state='complete',shots=2,bullseyes=1,rate=.5,lives_lost=0,output=output)
                service=Service(directory);app=AssistedApp(root,service)
                self.assertEqual(app.series_count.get(),'20');self.assertTrue(app.record_flight.get())
                app.calibration_path=str(Path(directory)/'profile');app.model_path=str(Path(directory)/'model.json')
                self.assertFalse(app.loop_arm.get());app._refresh_buttons();self.assertFalse(app.loop_button.instate(['disabled']))
                app.continuous()
                deadline=time.monotonic()+2
                while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
                self.assertFalse(app.busy);self.assertEqual(service.called,(123,20,True))
                self.assertEqual(app.status.get(),'Série terminée');self.assertIn('Exporter pour Codex',app.detail.get())
                self.assertEqual(service.load_settings()['last_session'],str(Path(directory)/'series'))
        finally:root.destroy()
