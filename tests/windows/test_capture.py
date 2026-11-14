"""Synthetic capture tests: no desktop access or private images."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import patch

from idleon_darts.capture import CaptureError, WindowsFrameSource
from idleon_darts.models import Rect, WindowContext


class Desktop:
    def __init__(self):
        self.context = WindowContext(123, Rect(10, 20, 4, 3), 144, True, True)

    def snapshot(self):
        return self.context

    def physical_pixels(self):
        return nullcontext()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        self.closed = 0
        self.calls = []
        self.after_grab = lambda: None
        self.image = SimpleNamespace(width=2, height=1, bgra=bytes([1, 2, 3, 0, 4, 5, 6, 255]))
        self.backend = SimpleNamespace(grab=self.grab, close=self.close)

    def grab(self, region):
        self.calls.append(region)
        self.after_grab()
        return self.image

    def close(self):
        self.closed += 1

    def source(self):
        return WindowsFrameSource(self.desktop, Rect(11, 21, 2, 1),
                                  backend='mss', backend_factory=lambda: self.backend)

    def test_bgr_region_timing_unique_ids_and_close(self):
        with self.source() as source, patch('idleon_darts.capture.perf_counter_ns',
                                           side_effect=[100, 200, 300, 400]):
            frame = source.grab()
            second = source.grab()
            self.assertEqual((frame.start_ns, frame.end_ns), (100, 200))
            self.assertEqual(frame.bgr, bytes([1, 2, 3, 4, 5, 6]))
            self.assertNotEqual(frame.frame_id, second.frame_id)
            self.assertEqual(self.calls[0], dict(left=11, top=21, width=2, height=1))
        source.close()
        self.assertEqual(self.closed, 1)
        with self.assertRaises(CaptureError):
            source.grab()

    def test_invalid_before_capture_never_reads_pixels(self):
        for changes in [dict(foreground=False), dict(game_visible=False), dict(dpi=192),
                        dict(window_id=456), dict(rect=Rect(12, 20, 4, 3))]:
            self.setUp()
            with self.subTest(changes=changes), self.source() as source:
                self.desktop.context = replace(self.desktop.context, **changes)
                with self.assertRaises(CaptureError):
                    source.grab()
                self.assertEqual(self.calls, [])

    def test_changes_during_capture_discard_frame(self):
        for changes in [dict(foreground=False), dict(game_visible=False), dict(dpi=192),
                        dict(window_id=456), dict(rect=Rect(12, 20, 4, 3))]:
            self.setUp()
            with self.subTest(changes=changes), self.source() as source:
                self.after_grab = lambda: setattr(self.desktop, 'context',
                                                  replace(self.desktop.context, **changes))
                with self.assertRaises(CaptureError):
                    source.grab()
                self.assertEqual(len(self.calls), 1)

    def test_geometry_change_requires_new_source_even_if_roi_still_inside(self):
        with self.source() as source:
            original = self.desktop.context
            self.desktop.context = replace(self.desktop.context, rect=Rect(10, 20, 5, 3))
            with self.assertRaises(CaptureError):
                source.grab()
            self.desktop.context = original
            with self.assertRaises(CaptureError):
                source.grab()

    def test_bad_roi_and_hidden_window_refuse_backend_initialization(self):
        factory = unittest.mock.Mock()
        with self.assertRaises(CaptureError):
            WindowsFrameSource(self.desktop, Rect(0, 0, 2, 1), backend_factory=factory)
        self.desktop.context = replace(self.desktop.context, foreground=False)
        with self.assertRaises(CaptureError):
            WindowsFrameSource(self.desktop, Rect(11, 21, 2, 1), backend_factory=factory)
        factory.assert_not_called()

    def test_backend_exception_and_malformed_pixels_rejected(self):
        with self.source() as source:
            self.image.width = 9
            with self.assertRaises(CaptureError):
                source.grab()
            self.image.width = 2
            self.image.bgra = b'short'
            with self.assertRaises(CaptureError):
                source.grab()
            self.after_grab = unittest.mock.Mock(side_effect=OSError('capture failed'))
            with self.assertRaises(CaptureError):
                source.grab()

    def test_other_thread_is_rejected(self):
        with self.source() as source, patch('idleon_darts.capture.get_ident', return_value=-1):
            with self.assertRaises(CaptureError):
                source.grab()

    def test_native_adapter_refuses_non_windows_without_importing_mss(self):
        from idleon_darts.windows_io import WindowsDesktop
        with patch('sys.platform', 'linux'), self.assertRaises(CaptureError):
            WindowsDesktop(123)

    def test_dxgi_waits_for_new_frame_without_returning_cached_pixels(self):
        from idleon_darts.capture import _BGRImage
        self.backend.grab = unittest.mock.Mock(side_effect=[None, _BGRImage(2, 1, b'123456')])
        with WindowsFrameSource(self.desktop, Rect(11, 21, 2, 1),
                                backend_factory=lambda: self.backend) as source, \
                patch('idleon_darts.capture.sleep'):
            frame = source.grab()
            self.assertEqual(frame.bgr, b'123456')
            self.assertEqual(self.backend.grab.call_count, 2)

    def test_no_new_frame_times_out_and_focus_is_checked_while_waiting(self):
        self.backend.grab = unittest.mock.Mock(return_value=None)
        with WindowsFrameSource(self.desktop, Rect(11, 21, 2, 1),
                                backend_factory=lambda: self.backend) as source, \
                patch('idleon_darts.capture.perf_counter_ns', side_effect=[0, 100_000_001]):
            with self.assertRaisesRegex(CaptureError, 'nouvelle image'):
                source.grab()
        self.setUp()
        def lose_focus(_):
            self.desktop.context = replace(self.desktop.context, foreground=False)
            return None
        self.backend.grab = lose_focus
        with WindowsFrameSource(self.desktop, Rect(11, 21, 2, 1),
                                backend_factory=lambda: self.backend) as source:
            with self.assertRaisesRegex(CaptureError, 'focus'):
                source.grab()

    def test_dxgi_camera_fresh_acquisition_and_immutable_copy(self):
        from idleon_darts.capture import _DXGIBackend
        raw = bytearray(b'123456')
        array = SimpleNamespace(shape=(1, 2, 3), dtype=SimpleNamespace(name='uint8'),
                                tobytes=lambda order: bytes(raw))
        camera = SimpleNamespace(grab=unittest.mock.Mock(return_value=array),
                                 release=unittest.mock.Mock(), is_capturing=False)
        factory = unittest.mock.Mock(return_value=camera)
        backend = _DXGIBackend(camera_factory=factory)
        frame = backend.grab(dict(left=11, top=21, width=2, height=1))
        camera.grab.assert_called_once_with(region=(11, 21, 13, 22), copy=False, new_frame_only=True)
        raw[:] = b'abcdef'
        self.assertEqual(frame.bgr, b'123456')
        camera.grab.return_value = None
        self.assertIsNone(backend.grab(dict(left=11, top=21, width=2, height=1)))
        backend.close()
        camera.release.assert_called_once()

    def test_dxgi_rejects_malformed_arrays_and_background_capture(self):
        from idleon_darts.capture import _DXGIBackend
        camera = SimpleNamespace(grab=unittest.mock.Mock(), is_capturing=True)
        with self.assertRaises(CaptureError):
            _DXGIBackend(camera_factory=lambda **kwargs: camera)
        camera.is_capturing = False
        backend = _DXGIBackend(camera_factory=lambda **kwargs: camera)
        for shape, dtype in [((1, 2, 4), 'uint8'), ((1, 2, 3), 'float32')]:
            camera.grab.return_value = SimpleNamespace(shape=shape, dtype=SimpleNamespace(name=dtype))
            with self.assertRaises(CaptureError):
                backend.grab(dict(left=11, top=21, width=2, height=1))


@unittest.skipUnless(sys.platform == 'win32', 'API Windows requise')
class NativeContextTests(unittest.TestCase):
    """Own hidden synthetic window only; never reads desktop pixels."""

    def test_native_geometry_dpi_restore_hidden_and_destroyed_window(self):
        import ctypes as c
        from ctypes import wintypes as w
        from idleon_darts.windows_io import WindowsDesktop
        user = c.WinDLL('user32', use_last_error=True)
        user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                       c.c_int, c.c_int, c.c_int, c.c_int,
                                       w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
        user.CreateWindowExW.restype = w.HWND
        user.DestroyWindow.argtypes, user.DestroyWindow.restype = [w.HWND], w.BOOL
        user.GetThreadDpiAwarenessContext.restype = c.c_void_p
        user.GetDesktopWindow.restype = w.HWND
        bootstrap = WindowsDesktop(user.GetDesktopWindow())
        with bootstrap.physical_pixels():
            hwnd = user.CreateWindowExW(0, 'STATIC', 'Synthetic capture test', 0x80000000,
                                        30, 40, 100, 80, None, None, None, None)
        self.assertTrue(hwnd, c.get_last_error())
        try:
            desktop = WindowsDesktop(hwnd)
            before = user.GetThreadDpiAwarenessContext()
            context = desktop.snapshot()
            self.assertEqual(context.rect, Rect(30, 40, 100, 80))
            self.assertGreater(context.dpi, 0)
            self.assertFalse(context.game_visible)
            self.assertEqual(user.GetThreadDpiAwarenessContext(), before)
            with self.assertRaises(CaptureError):
                WindowsFrameSource(desktop)
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                with desktop.physical_pixels():
                    raise RuntimeError('synthetic')
            self.assertEqual(user.GetThreadDpiAwarenessContext(), before)
        finally:
            user.DestroyWindow(hwnd)
        with self.assertRaises(CaptureError):
            desktop.snapshot()

    def test_native_mss_resources_initialize_and_close_without_grabbing(self):
        try:
            import mss
        except ImportError:
            self.skipTest('Dependance optionnelle MSS absente')
        # physical_pixels does not depend on any specific target window.
        from idleon_darts.windows_io import WindowsDesktop
        import ctypes as c
        from ctypes import wintypes as w
        user = c.WinDLL('user32', use_last_error=True)
        user.GetDesktopWindow.restype = w.HWND
        desktop = WindowsDesktop(user.GetDesktopWindow())
        with desktop.physical_pixels():
            backend = mss.mss()
            backend.close()
