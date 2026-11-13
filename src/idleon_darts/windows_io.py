"""Native adapter contracts only. Importing this module has no desktop side effects.

The future Windows implementation must serialize the controller and emergency stop,
refresh context immediately before reservation and release held buttons on suspend.
"""
from dataclasses import dataclass
from typing import Protocol
from .models import WindowContext


@dataclass(frozen=True)
class InputReceipt:
    shot_id: str
    down_ns: int | None
    up_ns: int | None
    error: str | None


class DesktopContext(Protocol):
    def snapshot(self) -> WindowContext: ...


class InputAdapter(Protocol):
    def release_shot(self, shot_id: str) -> InputReceipt: ...
    def release_all(self) -> None: ...
