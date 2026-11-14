from contextlib import redirect_stdout, redirect_stderr
import io
import json
import unittest
from unittest.mock import patch
from idleon_darts.cli import main


class CliTests(unittest.TestCase):
    def test_status_describes_actual_capabilities(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(['status']), 0)
        status = json.loads(out.getvalue())
        self.assertTrue(status['automatic_play_available'])
        self.assertEqual(status['stage'], 'experimental-desktop')
        self.assertFalse(status['private_capture_included'])

    def test_reserved_commands_do_not_read_profile_or_touch_desktop(self):
        for args in [['run', '--profile', 'missing.json'],
                     ['observe', '--profile', 'missing.json'],
                     ['replay', 'missing-session', '--profile', 'missing.json']]:
            with self.subTest(args=args), patch('builtins.open', side_effect=AssertionError('unexpected IO')):
                err = io.StringIO()
                with redirect_stderr(err):
                    self.assertEqual(main(args), 2)
                self.assertIn('indisponible', err.getvalue())

    def test_capture_check_uses_explicit_window_and_never_saves_pixels(self):
        from idleon_darts.capture import Frame
        from idleon_darts.models import Rect
        frame = Frame('synthetic', 100, 200, Rect(0, 0, 1, 1), b'\0\0\0')
        out = io.StringIO()
        with patch('idleon_darts.windows_io.WindowsDesktop') as desktop, \
                patch('idleon_darts.capture.WindowsFrameSource') as source, \
                patch('idleon_darts.cli.time.perf_counter_ns', side_effect=[100, 1_000_000_100]), \
                redirect_stdout(out):
            source.return_value.__enter__.return_value.grab.return_value = frame
            self.assertEqual(main(['capture-check', '--window-id', '0x7b',
                                   '--frames', '2', '--delay', '0']), 0)
            desktop.assert_called_once_with(123)
            source.assert_called_once_with(desktop.return_value, backend='dxgi')
            self.assertEqual(source.return_value.__enter__.return_value.grab.call_count, 2)
        report = json.loads(out.getvalue())
        self.assertEqual(report['frames'], 2)
        self.assertEqual(report['elapsed_seconds'], 1)
        self.assertEqual(report['effective_fps'], 2)
        self.assertEqual(report['capture_ms_p95'], .0001)
        self.assertEqual(report['frames_over_100ms'], 0)
        self.assertEqual(report['frames_over_16_67ms'], 0)
        self.assertEqual(report['backend'], 'dxgi')
        self.assertFalse(report['images_saved'])

    def test_capture_check_reports_refusal(self):
        from idleon_darts.capture import CaptureError
        err = io.StringIO()
        with patch('idleon_darts.windows_io.WindowsDesktop', side_effect=CaptureError('sans focus')), \
                redirect_stderr(err):
            self.assertEqual(main(['capture-check', '--window-id', '123', '--delay', '0']), 1)
        self.assertIn('sans focus', err.getvalue())

    def test_capture_check_rejects_invalid_arguments_before_desktop_access(self):
        for extra in [['--frames', '0'], ['--frames', '301'], ['--delay', 'nan'],
                      ['--delay', '-1'], ['--delay', '31'], ['--window-id', '0']]:
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), \
                    patch('idleon_darts.windows_io.WindowsDesktop') as desktop:
                with self.assertRaises(SystemExit) as error:
                    main(['capture-check', '--window-id', '123'] + extra)
                self.assertEqual(error.exception.code, 2)
                desktop.assert_not_called()
