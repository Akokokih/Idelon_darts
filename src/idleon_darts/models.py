"""Validated immutable values. Image coordinates are physical pixels relative to ROI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math


def integer(name: str, value: int, minimum: int | None = None) -> None:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f'{name}: entier requis, minimum={minimum}')


def finite(name: str, value: float, minimum: float | None = None) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name}: nombre fini requis')
    if minimum is not None and value < minimum:
        raise ValueError(f'{name}: minimum={minimum}')


def text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name}: texte non vide requis')


def point(name: str, value: tuple[float, float]) -> None:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f'{name}: paire de coordonnees requise')
    for coordinate in value:
        finite(name, coordinate)


class State(str, Enum):
    PAUSED = 'paused'
    OBSERVING = 'observing'
    READY = 'ready'
    SHOT_PENDING = 'shot_pending'
    STOPPED = 'stopped'


class Result(str, Enum):
    CENTRE = 'centre'
    OTHER = 'other'
    MISS = 'miss'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self):
        integer('left', self.left)
        integer('top', self.top)
        integer('width', self.width, 1)
        integer('height', self.height, 1)

    def contains(self, other: Rect) -> bool:
        return (self.left <= other.left and self.top <= other.top
                and other.left + other.width <= self.left + self.width
                and other.top + other.height <= self.top + self.height)


@dataclass(frozen=True)
class Profile:
    schema_version: int
    profile_id: str
    created_utc: str
    window_rect: Rect
    roi: Rect
    dpi: int
    detector_version: str
    model_version: str | None
    calibration_coverage: tuple[str, ...]

    def __post_init__(self):
        integer('schema_version', self.schema_version, 1)
        if self.schema_version != 1:
            raise ValueError('schema_version incompatible')
        for name in ('profile_id', 'created_utc', 'detector_version'):
            text(name, getattr(self, name))
        try:
            timestamp = datetime.fromisoformat(self.created_utc.replace('Z', '+00:00'))
            if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
                raise ValueError('created_utc doit etre en UTC')
        except (ValueError, TypeError) as exc:
            raise ValueError('created_utc invalide') from exc
        if not isinstance(self.window_rect, Rect) or not isinstance(self.roi, Rect):
            raise ValueError('Rect requis')
        if not self.window_rect.contains(self.roi):
            raise ValueError('ROI hors fenetre')
        integer('dpi', self.dpi, 1)
        if self.model_version is not None:
            text('model_version', self.model_version)
        if not isinstance(self.calibration_coverage, tuple):
            raise ValueError('calibration_coverage: tuple requis')
        for key in self.calibration_coverage:
            text('calibration_coverage', key)
        if len(set(self.calibration_coverage)) != len(self.calibration_coverage):
            raise ValueError('contextes de calibration dupliques')

    @property
    def calibrated(self) -> bool:
        # Metadata check only: this does not prove a model's empirical accuracy.
        return self.model_version is not None and bool(self.calibration_coverage)


@dataclass(frozen=True)
class WindowContext:
    window_id: int
    rect: Rect
    dpi: int
    foreground: bool
    game_visible: bool

    def __post_init__(self):
        integer('window_id', self.window_id, 1)
        integer('dpi', self.dpi, 1)
        if not isinstance(self.rect, Rect):
            raise ValueError('rect requis')
        if type(self.foreground) is not bool or type(self.game_visible) is not bool:
            raise ValueError('etat de fenetre booleen requis')


@dataclass(frozen=True)
class Observation:
    observation_id: str
    session_id: str
    segment_index: int
    capture_start_ns: int
    capture_end_ns: int
    launcher_position: tuple[float, float] | None
    arm_angle: float | None
    arm_direction: int | None
    target_center: tuple[float, float] | None
    target_radius: float | None
    wind_features: tuple[float, ...] | None
    context_key: str | None
    confidence: float
    invalid_reasons: tuple[str, ...] = ()
    image_path: str | None = None

    def __post_init__(self):
        text('observation_id', self.observation_id)
        text('session_id', self.session_id)
        integer('segment_index', self.segment_index, 1)
        integer('capture_start_ns', self.capture_start_ns, 0)
        integer('capture_end_ns', self.capture_end_ns, self.capture_start_ns)
        for name in ('launcher_position', 'target_center'):
            value = getattr(self, name)
            if value is not None:
                point(name, value)
        if self.arm_angle is not None:
            finite('arm_angle (radians)', self.arm_angle)
        if self.arm_direction is not None and (type(self.arm_direction) is not int
                                               or self.arm_direction not in (-1, 1)):
            raise ValueError('arm_direction: -1, 1 ou None requis')
        if self.target_radius is not None:
            finite('target_radius', self.target_radius, 0)
            if self.target_radius == 0:
                raise ValueError('target_radius doit etre positif')
        if self.wind_features is not None:
            if not isinstance(self.wind_features, tuple) or not self.wind_features:
                raise ValueError('wind_features: tuple non vide ou None requis')
            for value in self.wind_features:
                finite('wind_features', value)
        if self.context_key is not None:
            text('context_key', self.context_key)
        finite('confidence', self.confidence, 0)
        if self.confidence > 1:
            raise ValueError('confidence hors [0,1]')
        if not isinstance(self.invalid_reasons, tuple):
            raise ValueError('invalid_reasons: tuple requis')
        for reason in self.invalid_reasons:
            text('invalid_reason', reason)
        if self.image_path is not None:
            text('image_path', self.image_path)

    @property
    def complete(self) -> bool:
        return all(value is not None for value in (
            self.launcher_position, self.arm_angle, self.arm_direction,
            self.target_center, self.target_radius, self.wind_features, self.context_key))


@dataclass(frozen=True)
class Prediction:
    observation_id: str
    profile_id: str
    model_version: str
    context_key: str
    release_ns: int
    valid_until_ns: int
    predicted_impact: tuple[float, float]
    uncertainty_radius: float

    def __post_init__(self):
        for name in ('observation_id', 'profile_id', 'model_version', 'context_key'):
            text(name, getattr(self, name))
        integer('release_ns', self.release_ns, 0)
        integer('valid_until_ns', self.valid_until_ns, self.release_ns)
        point('predicted_impact', self.predicted_impact)
        finite('uncertainty_radius', self.uncertainty_radius, 0)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    state: State

