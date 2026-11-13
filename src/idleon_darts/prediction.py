"""Prediction interface; models and wind constants await empirical calibration."""
from typing import Protocol
from .models import Observation, Prediction, Profile


class Predictor(Protocol):
    def predict(self, observation: Observation, profile: Profile,
                *, now_ns: int) -> Prediction | None: ...
