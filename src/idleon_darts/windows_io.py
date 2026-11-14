"""Read-only Win32 context and future input contracts. Imports have no side effects.

The future Windows implementation must serialize the controller and emergency stop,
refresh context immediately before reservation and release held buttons on suspend.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import sys
from typing import Protocol
from .models import WindowContext


@dataclass(frozen=True)
class InputReceipt:
    shot_id: str
    down_ns: int | None
    up_ns: int | None
    error: str | None
    down_start_ns: int | None = None
    up_start_ns: int | None = None
    planned_up_ns: int | None = None


class DesktopContext(Protocol):
    def snapshot(self) -> WindowContext: ...


class InputAdapter(Protocol):
    def release_shot(self, shot_id: str) -> InputReceipt: ...
    def release_all(self) -> None: ...


class WindowsDesktop:
    """Explicit HWND, physical client rectangle, and target-window DPI.

    Visible means not minimized/cloaked and wholly inside the primary screen;
    it does not prove absence of overlapping windows or detect game content.
    DPI is GetDpiForWindow's value (96 for DPI-unaware target applications).
    """

    def __init__(self, window_id: int):
        from .capture import CaptureError
        from .models import integer
        integer('window_id', window_id, 1)
        if sys.platform != 'win32':
            raise CaptureError('Capture disponible uniquement sous Windows 10/11')
        import ctypes
        from ctypes import wintypes as w
        self._ctypes = ctypes
        self._w = w
        self._user = ctypes.WinDLL('user32', use_last_error=True)
        self._dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        signatures = {
            'IsWindow': ([w.HWND], w.BOOL),
            'IsWindowVisible': ([w.HWND], w.BOOL),
            'IsIconic': ([w.HWND], w.BOOL),
            'GetForegroundWindow': ([], w.HWND),
            'GetClientRect': ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            'ClientToScreen': ([w.HWND, ctypes.POINTER(w.POINT)], w.BOOL),
            'GetWindowThreadProcessId': ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            'GetDpiForWindow': ([w.HWND], w.UINT),
            'GetSystemMetrics': ([ctypes.c_int], ctypes.c_int),
            'SetThreadDpiAwarenessContext': ([ctypes.c_void_p], ctypes.c_void_p),
            'GetThreadDpiAwarenessContext': ([], ctypes.c_void_p),
            'GetAwarenessFromDpiAwarenessContext': ([ctypes.c_void_p], ctypes.c_int),
        }
        try:
            for name, (arguments, result) in signatures.items():
                function = getattr(self._user, name)
                function.argtypes, function.restype = arguments, result
            self._dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
            self._dwm.DwmGetWindowAttribute.restype = ctypes.c_long
        except AttributeError as exc:
            raise CaptureError('API Windows 10/11 requise') from exc
        self.window_id = window_id
        self._identity = self._window_identity()

    def _window_identity(self):
        from .capture import CaptureError
        pid = self._w.DWORD()
        tid = self._user.GetWindowThreadProcessId(self.window_id, self._ctypes.byref(pid))
        if not tid or not pid.value or not self._user.IsWindow(self.window_id):
            raise CaptureError('Fenetre introuvable ou fermee')
        return tid, pid.value

    @contextmanager
    def physical_pixels(self):
        from .capture import CaptureError
        # Per-monitor V2 on this thread only; restore the caller's context.
        previous = self._user.SetThreadDpiAwarenessContext(self._ctypes.c_void_p(-4))
        if not previous:
            raise CaptureError('Activation DPI physique impossible')
        try:
            awareness = self._user.GetAwarenessFromDpiAwarenessContext(
                self._user.GetThreadDpiAwarenessContext())
            if awareness != 2:
                raise CaptureError('Contexte DPI par moniteur requis')
            yield
        finally:
            if not self._user.SetThreadDpiAwarenessContext(previous):
                raise CaptureError('Restauration du contexte DPI impossible')

    def snapshot(self) -> WindowContext:
        from .capture import CaptureError
        from .models import Rect
        c, u = self._ctypes, self._user
        with self.physical_pixels():
            if self._window_identity() != self._identity:
                raise CaptureError('Identite de fenetre modifiee')
            rect = self._w.RECT()
            origin = self._w.POINT(0, 0)
            if (not u.GetClientRect(self.window_id, c.byref(rect))
                    or not u.ClientToScreen(self.window_id, c.byref(origin))):
                raise CaptureError('Lecture du rectangle impossible')
            if rect.right <= rect.left or rect.bottom <= rect.top:
                raise CaptureError('Rectangle de fenetre vide')
            bounds = Rect(origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top)
            dpi = u.GetDpiForWindow(self.window_id)
            if not dpi:
                raise CaptureError('DPI de la fenetre inconnu')
            cloaked = self._w.DWORD()
            if self._dwm.DwmGetWindowAttribute(self.window_id, 14, c.byref(cloaked), c.sizeof(cloaked)):
                raise CaptureError('Visibilite DWM inconnue')
            width, height = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
            if width <= 0 or height <= 0:
                raise CaptureError('Ecran principal indisponible')
            visible = (bool(u.IsWindowVisible(self.window_id)) and not u.IsIconic(self.window_id)
                       and not cloaked.value and Rect(0, 0, width, height).contains(bounds))
            foreground = u.GetForegroundWindow() == self.window_id
            if self._window_identity() != self._identity:
                raise CaptureError('Fenetre fermee pendant la lecture')
            return WindowContext(self.window_id, bounds, dpi, foreground, bool(visible))
