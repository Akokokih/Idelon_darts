"""Interface for the future product observer, independent of the private recorder."""
from dataclasses import dataclass
from typing import Protocol
from .models import Rect, integer


@dataclass(frozen=True)
class Frame:
    frame_id: str
    start_ns: int
    end_ns: int
    region: Rect
    bgr: bytes

    def __post_init__(self):
        integer('start_ns', self.start_ns, 0)
        integer('end_ns', self.end_ns, self.start_ns)
        if not isinstance(self.region, Rect) or not isinstance(self.bgr, bytes):
            raise ValueError('Frame: region et pixels BGR requis')
        if len(self.bgr) != self.region.width * self.region.height * 3:
            raise ValueError('Dimensions des pixels BGR incoherentes')


class FrameSource(Protocol):
    def grab(self) -> Frame: ...
    def close(self) -> None: ...
