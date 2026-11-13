"""Perception contract. No visual detections are fabricated without recordings."""
from typing import Protocol
from .capture import Frame
from .models import Observation, Profile


class Perception(Protocol):
    def detect(self, frame: Frame, profile: Profile, *, session_id: str,
               segment_index: int) -> Observation: ...
