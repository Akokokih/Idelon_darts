from pathlib import Path
from threading import Event
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from idleon_darts.continuous import classify_scores,StopSignal,run


class ContinuousTests(unittest.TestCase):
    def test_score_deltas_distinguish_red_bonus_other_miss_and_reset(self):
        for delta in (5,10,30):self.assertEqual(classify_scores(40,40+delta),'centre')
        for delta in (1,2,3):self.assertEqual(classify_scores(40,40+delta),'other')
        self.assertEqual(classify_scores(40,40),'miss')
        for value in (None,0,44,46):self.assertEqual(classify_scores(40,value),'unknown')

    def test_unarmed_never_reads_desktop(self):
        with patch('idleon_darts.windows_io.WindowsDesktop') as desktop:
            self.assertEqual(run(SimpleNamespace(arm=False))['shots'],0)
            desktop.assert_not_called()

    def test_stop_file_and_gui_event_both_cancel(self):
        with TemporaryDirectory() as directory:
            event=Event();file=Path(directory)/'stop-requested';signal=StopSignal(event,file)
            self.assertFalse(signal.is_set());file.touch();self.assertTrue(signal.wait(.1))
            file.unlink();event.set();self.assertTrue(signal.is_set())
