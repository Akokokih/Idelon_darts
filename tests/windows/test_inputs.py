from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from tests.unit.helpers import context


class InputTests(unittest.TestCase):
    def setUp(self):
        self.expected = context()
        self.desktop = SimpleNamespace(snapshot=Mock(return_value=self.expected))
        self.transport = SimpleNamespace(move=Mock(), down=Mock(), up=Mock(),
                                         is_down=Mock(return_value=False))

    def adapter(self):
        from idleon_darts.native_input import WindowsInputAdapter
        return WindowsInputAdapter(self.desktop, self.expected, (200, 200),
                                   hold_ms=2, transport=self.transport)

    def test_one_click_has_receipt_and_duplicate_never_resends(self):
        adapter = self.adapter()
        receipt = adapter.release_shot('one')
        self.assertIsNone(receipt.error)
        self.assertLessEqual(receipt.down_ns, receipt.up_ns)
        self.assertLessEqual(receipt.down_start_ns, receipt.down_ns)
        self.assertLessEqual(receipt.down_ns, receipt.up_start_ns)
        self.assertLessEqual(receipt.up_start_ns, receipt.up_ns)
        self.assertIsNotNone(adapter.release_shot('one').error)
        self.transport.down.assert_called_once()
        self.transport.up.assert_called_once()

    def test_no_down_when_inactive_emergency_or_user_button_held(self):
        for problem in ['focus', 'dpi', 'f8', 'held']:
            self.setUp()
            if problem == 'focus':self.desktop.snapshot.return_value = replace(self.expected, foreground=False)
            if problem == 'dpi':self.desktop.snapshot.return_value = replace(self.expected, dpi=96)
            if problem in ('f8', 'held'):
                self.transport.is_down.side_effect = lambda key: key == (0x77 if problem == 'f8' else 1)
            with self.subTest(problem=problem):
                result = self.adapter().release_shot('one')
                self.assertIsNotNone(result.error)
                self.transport.down.assert_not_called()

    def test_focus_loss_during_hold_releases_owned_button_and_reports_error(self):
        def lose_focus():
            self.desktop.snapshot.return_value = replace(self.expected, foreground=False)
        self.transport.down.side_effect = lose_focus
        result = self.adapter().release_shot('one')
        self.assertIsNotNone(result.error)
        self.transport.up.assert_called_once()

    def test_partial_transport_failure_still_attempts_release(self):
        self.transport.down.side_effect = OSError('transport error')
        result = self.adapter().release_shot('one')
        self.assertIsNotNone(result.error)
        self.transport.up.assert_called_once()

    def test_expired_release_window_never_sends_down(self):
        result = self.adapter().release_shot('expired', not_after_ns=0)
        self.assertIsNotNone(result.error)
        self.transport.down.assert_not_called()
        self.transport.up.assert_not_called()

    def test_absolute_mouse_up_absorbs_variable_down_call_duration(self):
        for latency in (2_000_000,12_000_000,25_000_000):
            self.setUp();clock=[1_000_000_000];target=clock[0]+40_000_000
            self.transport.down.side_effect=lambda:clock.__setitem__(0,clock[0]+latency)
            def sleep(seconds):clock[0]+=round(seconds*1e9)
            with patch('idleon_darts.native_input.perf_counter_ns',side_effect=lambda:clock[0]),patch('idleon_darts.native_input.sleep',side_effect=sleep):
                receipt=self.adapter().release_shot('scheduled',up_at_ns=target)
            self.assertIsNone(receipt.error)
            self.assertEqual(receipt.planned_up_ns,target)
            self.assertEqual(receipt.up_ns,target)
            self.transport.up.assert_called_once()

    def test_absolute_mouse_up_rejects_expired_deadline_and_releases_after_slow_down(self):
        for expired in (False,True):
            self.setUp();clock=[1_000_000_000];target=clock[0]+10_000_000
            self.transport.down.side_effect=lambda:clock.__setitem__(0,clock[0]+20_000_000)
            with patch('idleon_darts.native_input.perf_counter_ns',side_effect=lambda:clock[0]):
                receipt=self.adapter().release_shot('late',up_at_ns=clock[0]-1 if expired else target)
            self.assertIsNotNone(receipt.error)
            if expired:
                self.transport.down.assert_not_called();self.transport.up.assert_not_called()
            else:
                self.transport.up.assert_called_once();self.assertEqual(receipt.up_ns,clock[0])

    def test_focus_loss_during_absolute_hold_still_releases(self):
        self.transport.down.side_effect=lambda:setattr(self.desktop,'snapshot',Mock(return_value=replace(self.expected,foreground=False)))
        from time import perf_counter_ns
        result=self.adapter().release_shot('focus-lost',up_at_ns=perf_counter_ns()+40_000_000)
        self.assertIsNotNone(result.error);self.transport.up.assert_called_once()
