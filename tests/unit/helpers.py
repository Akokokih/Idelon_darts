from idleon_darts.models import Observation, Prediction, Profile, Rect, WindowContext


def profile():
    return Profile(schema_version=1, profile_id='synthetic', created_utc='2026-11-13T12:00:00Z',
                   window_rect=Rect(0, 0, 1000, 800), roi=Rect(100, 100, 600, 400),
                   dpi=144, detector_version='synthetic-detector', model_version='synthetic-model',
                   calibration_coverage=('wind-zero',))


def context(**changes):
    fields = dict(window_id=12, rect=Rect(0, 0, 1000, 800), dpi=144,
                  foreground=True, game_visible=True)
    return WindowContext(**(fields | changes))


def observation(**changes):
    fields = dict(observation_id='obs1', session_id='test', segment_index=1,
                  capture_start_ns=1_000_000, capture_end_ns=2_000_000,
                  launcher_position=(10., 30.), arm_angle=0.1, arm_direction=1,
                  target_center=(300., 200.), target_radius=10., wind_features=(0.,),
                  context_key='wind-zero', confidence=0.99, invalid_reasons=())
    return Observation(**(fields | changes))


def prediction(**changes):
    fields = dict(observation_id='obs1', profile_id='synthetic', model_version='synthetic-model',
                  context_key='wind-zero', release_ns=3_000_000, valid_until_ns=4_000_000,
                  predicted_impact=(300., 200.), uncertainty_radius=1.)
    return Prediction(**(fields | changes))
