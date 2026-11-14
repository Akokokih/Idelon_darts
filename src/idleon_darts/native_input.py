"""Bounded Win32 mouse inputs for explicitly armed product tests.

No native library is loaded at import, and constructors send no inputs.
"""
import ctypes as c
from ctypes import wintypes as w
from threading import Lock
from time import perf_counter_ns, sleep
import sys
from contextlib import nullcontext
from .windows_io import InputReceipt
from .models import Rect, integer, text, finite


class _Win32Mouse:
    def __init__(self):
        if sys.platform != 'win32':raise RuntimeError('Windows requis pour les entrees')
        class Mouse(c.Structure):
            _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', c.c_size_t)]
        class Keyboard(c.Structure):
            _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', c.c_size_t)]
        class Hardware(c.Structure):
            _fields_ = [('message', w.DWORD), ('low', w.WORD), ('high', w.WORD)]
        class Payload(c.Union):
            _fields_ = [('mouse', Mouse), ('keyboard', Keyboard), ('hardware', Hardware)]
        class Input(c.Structure):
            _anonymous_ = ('payload',)
            _fields_ = [('type', w.DWORD), ('payload', Payload)]
        self.Input, self.Mouse = Input, Mouse
        self.user = c.WinDLL('user32', use_last_error=True)
        self.user.SendInput.argtypes, self.user.SendInput.restype = [w.UINT, c.POINTER(Input), c.c_int], w.UINT
        self.user.SetCursorPos.argtypes, self.user.SetCursorPos.restype = [c.c_int, c.c_int], w.BOOL
        self.user.GetAsyncKeyState.argtypes, self.user.GetAsyncKeyState.restype = [c.c_int], w.SHORT

    def is_down(self, key):return bool(self.user.GetAsyncKeyState(key) & (0x8001 if key==0x77 else 0x8000))

    def move(self, x, y):
        if not self.user.SetCursorPos(x, y):raise OSError('Positionnement du curseur refuse')

    def _send(self, flag):
        event = self.Input()
        event.type = 0
        event.mouse = self.Mouse(0, 0, 0, flag, 0, 0)
        if self.user.SendInput(1, c.byref(event), c.sizeof(event)) != 1:
            raise OSError('SendInput refuse ou partiel')

    def down(self):self._send(0x0002)
    def up(self):self._send(0x0004)


class WindowsInputAdapter:
    def __init__(self, desktop, expected_context, point, *, hold_ms=20, transport=None):
        for value in point:integer('click coordinate', value)
        finite('hold_ms', hold_ms, 1)
        if hold_ms > 500 or not expected_context.rect.contains(Rect(point[0], point[1], 1, 1)):
            raise ValueError('Clic ou maintien hors limites')
        self.desktop, self.expected, self.point = desktop, expected_context, point
        self.hold_ms = hold_ms
        self.transport = transport if transport is not None else _Win32Mouse()
        self._lock = Lock()
        self._held = False
        self._used = set()

    def stopped(self):return self.transport.is_down(0x77)  # F8

    def _guard(self):
        if self.stopped():raise RuntimeError('F8 demande')
        if self.desktop.snapshot() != self.expected:
            raise RuntimeError('Contexte de fenetre modifie')

    def release_all(self):
        if self._held:
            self.transport.up()
            self._held = False

    def release_shot(self, shot_id, *, not_after_ns=None, up_at_ns=None):
        text('shot_id', shot_id)
        if up_at_ns is not None:integer('up_at_ns',up_at_ns,0)
        with self._lock:
            down = up = None
            down_start = up_start = None
            error = None
            try:
                if shot_id in self._used:raise RuntimeError('Identifiant de tir deja utilise')
                self._used.add(shot_id)
                self._guard()
                if self.transport.is_down(1):raise RuntimeError('Bouton deja maintenu par utilisateur')
                with getattr(self.desktop, 'physical_pixels', nullcontext)():
                    self.transport.move(*self.point)
                self._guard()
                if not_after_ns is not None and perf_counter_ns() > not_after_ns:
                    raise RuntimeError('Fenetre de tir expiree avant entree native')
                if up_at_ns is not None and not 0<up_at_ns-perf_counter_ns()<=500_000_000:
                    raise RuntimeError('Echeance de relachement expiree ou trop eloignee')
                # Mark ownership before sending: a partially failed down may need up.
                self._held = True
                down_start = perf_counter_ns()
                self.transport.down()
                down = perf_counter_ns()
                deadline = up_at_ns if up_at_ns is not None else down + int(self.hold_ms * 1e6)
                if up_at_ns is not None and down>=deadline:
                    raise RuntimeError('Entree native terminee apres le relachement prevu')
                while (remaining:=deadline-perf_counter_ns()) > 0:
                    self._guard()
                    if up_at_ns is None:sleep(.001)
                    else:
                        remaining=deadline-perf_counter_ns()
                        if remaining>0:sleep(min(.001,remaining/1e9))
                self._guard()
            except Exception as exc:
                error = str(exc)
            finally:
                if self._held:
                    try:
                        up_start = perf_counter_ns()
                        self.release_all()
                        up = perf_counter_ns()
                    except Exception as exc:
                        error = f'{error or ""}; release failed: {exc}'
            return InputReceipt(shot_id, down, up, error, down_start, up_start,up_at_ns)
