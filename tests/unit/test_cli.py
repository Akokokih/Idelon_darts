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
        self.assertFalse(status['automatic_play_available'])
        self.assertEqual(status['stage'], 'foundation')
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
