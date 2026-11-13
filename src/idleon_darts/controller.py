"""Pure single-thread state machine. No clock, file, screenshot or mouse side effects.

The future Windows event loop must serialize calls, re-read the desktop immediately
before reservation and submit at most one native input after a successful reservation.
SHOT_PENDING denotes a reserved attempt; actual input timestamps belong to the future
session layer. An interrupted attempt requires explicit result resolution.
"""
import math
from .models import Decision, Observation, Prediction, Profile, Result, State, WindowContext
from .models import finite, integer, text


class Controller:
    def __init__(self, profile: Profile, *, min_confidence: float,
                 max_age_ns: int = 100_000_000, result_timeout_ns: int = 3_000_000_000):
        finite('min_confidence', min_confidence, 0)
        if min_confidence > 1:
            raise ValueError('min_confidence hors [0,1]')
        integer('max_age_ns', max_age_ns, 1)
        integer('result_timeout_ns', result_timeout_ns, 1)
        self.profile = profile
        self.min_confidence = min_confidence
        self.max_age_ns = max_age_ns
        self.result_timeout_ns = result_timeout_ns
        self.state = State.PAUSED
        self.reason = 'not_armed'
        self.pending_shot_id: str | None = None
        self._pending_since_ns: int | None = None
        self._window_id: int | None = None
        self._last_time_ns = 0
        self._minimum_capture_start_ns = 0
        self._used_shot_ids: set[str] = set()

    def _time(self, now_ns: int):
        integer('now_ns', now_ns, 0)
        if now_ns < self._last_time_ns:
            self.pause('clock_reversed')
            raise ValueError('Le temps ne peut pas reculer')
        self._last_time_ns = now_ns

    def _context_reason(self, context: WindowContext) -> str | None:
        if not context.foreground or not context.game_visible:
            return 'window_inactive'
        if context.rect != self.profile.window_rect or context.dpi != self.profile.dpi:
            return 'profile_geometry_mismatch'
        if self._window_id is not None and context.window_id != self._window_id:
            return 'window_identity_changed'
        return None

    def arm(self, context: WindowContext, *, now_ns: int):
        self._time(now_ns)
        if self.state == State.STOPPED:
            raise ValueError('Session terminee')
        if self.pending_shot_id is not None:
            raise ValueError('Tir non resolu : confirmer un resultat, meme inconnu, avant reprise')
        if not self.profile.calibrated:
            self.pause('profile_uncalibrated')
            raise ValueError('Profil sans modele ou couverture de calibration')
        reason = self._context_reason(context)
        if reason:
            self.pause(reason)
            raise ValueError(reason)
        self._window_id = context.window_id
        self.state, self.reason = State.OBSERVING, 'armed'

    def pause(self, reason: str):
        text('reason', reason)
        if self.state != State.STOPPED:
            self.state, self.reason = State.PAUSED, reason

    def stop(self):
        self.state, self.reason = State.STOPPED, 'stopped'

    def _deny(self, reason: str, *, suspend: bool = True) -> Decision:
        if suspend:
            self.pause(reason)
        else:
            self.state, self.reason = State.OBSERVING, reason
        return Decision(False, reason, self.state)

    def evaluate(self, observation: Observation, prediction: Prediction | None,
                 context: WindowContext, *, now_ns: int) -> Decision:
        self._time(now_ns)
        if self.state in (State.PAUSED, State.STOPPED):
            return Decision(False, self.reason, self.state)
        reason = self._context_reason(context)
        if reason:
            return self._deny(reason)
        if self.pending_shot_id is not None:
            if now_ns - self._pending_since_ns > self.result_timeout_ns:
                return self._deny('result_timeout')
            return Decision(False, 'shot_pending', self.state)
        if observation.capture_end_ns > now_ns:
            return self._deny('future_observation')
        if (now_ns-observation.capture_end_ns > self.max_age_ns
                or observation.capture_end_ns-observation.capture_start_ns > self.max_age_ns):
            return self._deny('stale_or_slow_capture')
        if observation.capture_start_ns < self._minimum_capture_start_ns:
            return self._deny('new_observation_required', suspend=False)
        if (not observation.complete or observation.invalid_reasons
                or observation.confidence < self.min_confidence):
            return self._deny('observation_unreliable')
        if observation.context_key not in self.profile.calibration_coverage:
            return self._deny('context_out_of_coverage')
        if prediction is None:
            return self._deny('no_prediction', suspend=False)
        if (prediction.observation_id != observation.observation_id
                or prediction.profile_id != self.profile.profile_id
                or prediction.model_version != self.profile.model_version
                or prediction.context_key != observation.context_key):
            return self._deny('prediction_mismatch')
        distance = math.dist(prediction.predicted_impact, observation.target_center)
        if distance + prediction.uncertainty_radius > observation.target_radius:
            return self._deny('impact_outside_centre', suspend=False)
        if now_ns < prediction.release_ns:
            return self._deny('waiting_for_release_window', suspend=False)
        if now_ns > prediction.valid_until_ns:
            return self._deny('release_window_missed', suspend=False)
        self.state, self.reason = State.READY, 'release_window_ready'
        return Decision(True, self.reason, self.state)

    def reserve_shot(self, shot_id: str, observation: Observation, prediction: Prediction,
                     context: WindowContext, *, now_ns: int) -> Decision:
        text('shot_id', shot_id)
        decision = self.evaluate(observation, prediction, context, now_ns=now_ns)
        if not decision.allowed:
            return decision
        if shot_id in self._used_shot_ids:
            return self._deny('shot_id_already_used')
        self._used_shot_ids.add(shot_id)
        self.pending_shot_id = shot_id
        self._pending_since_ns = now_ns
        self.state, self.reason = State.SHOT_PENDING, 'attempt_reserved'
        return Decision(True, self.reason, self.state)

    def confirm_result(self, shot_id: str, result: Result, *, now_ns: int):
        self._time(now_ns)
        if not isinstance(result, Result):
            raise ValueError('Result enum requis')
        if self.pending_shot_id is None or self.pending_shot_id != shot_id:
            raise ValueError('Resultat sans tir correspondant')
        self.pending_shot_id = None
        self._pending_since_ns = None
        self._minimum_capture_start_ns = now_ns
        if self.state == State.STOPPED:
            return
        if result == Result.UNKNOWN:
            self.pause('result_unknown')
        elif self.state != State.PAUSED:
            self.state, self.reason = State.OBSERVING, 'result_confirmed'
