"""Empirical, profile-bound trajectory models and guarded release forecasts."""
from typing import Protocol
from .models import Observation, Prediction, Profile
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import math
from .models import finite, text
from collections import deque


class Predictor(Protocol):
    def predict(self, observation: Observation, profile: Profile,
                *, now_ns: int) -> Prediction | None: ...


@dataclass(frozen=True)
class ImpactModel:
    profile_id: str
    contexts: dict
    version: str = 'empirical-release-v1'
    trigger_delay_ns: int = 0
    target_x_offset: float = 0.

    def __post_init__(self):
        text('profile_id', self.profile_id)
        if self.version not in ('empirical-release-v1', 'empirical-launch-v2') or not isinstance(self.contexts, dict) or not self.contexts:
            raise ValueError('Modele incompatible ou sans contexte')
        from .models import integer
        integer('trigger_delay_ns', self.trigger_delay_ns, 0)
        finite('target_x_offset', self.target_x_offset)
        if self.trigger_delay_ns > 200_000_000 or abs(self.target_x_offset) > 200:
            raise ValueError('Timing ou projection hors limites')
        if self.version == 'empirical-release-v1' and (self.trigger_delay_ns or self.target_x_offset):
            raise ValueError('Ancien modele incompatible avec correction de timing')
        fields = {'gain', 'curvature', 'dx_min', 'dx_max', 'angle_min', 'angle_max',
                  'sample_count', 'loo_max_error_px', 'uncertainty_px'}
        for key, case in self.contexts.items():
            text('context', key)
            timing_fields = {'phase_correction_ns', 'end_to_end_uncertainty_px'}
            if not isinstance(case, dict) or set(case) not in (fields, fields | timing_fields):
                raise ValueError('Champs du modele invalides')
            for name, value in case.items():finite(name, value)
            if timing_fields <= set(case):
                if (self.version != 'empirical-launch-v2'
                        or type(case['phase_correction_ns']) is not int
                        or abs(case['phase_correction_ns']) > 100_000_000
                        or case['end_to_end_uncertainty_px'] < 5):
                    raise ValueError('Correction de phase ou incertitude invalide')
            if (not .1 < case['gain'] < 5 or not 0 < case['curvature'] < .01
                    or not 0 < case['dx_min'] <= case['dx_max']
                    or not -1.3 < case['angle_min'] < case['angle_max'] < 1.3
                    or type(case['sample_count']) is not int or case['sample_count'] < 4
                    or case['uncertainty_px'] < 5 or case['loo_max_error_px'] < 0):
                raise ValueError('Parametres ou couverture de modele invalides')

    def impact(self, launcher, angle, target_x, context):
        case = self.contexts.get(context)
        if case is None:return None
        for name, value in [('angle', angle), ('target_x', target_x), ('x', launcher[0]), ('y', launcher[1])]:
            finite(name, value)
        dx = target_x - launcher[0]
        # Limited experimental projection, never an unbounded extrapolation.
        if not .9 * case['dx_min'] <= dx <= 1.1 * case['dx_max']:
            return None
        if not case['angle_min'] <= angle <= case['angle_max']:
            return None
        return launcher[1] - case['gain'] * dx * math.tan(angle) + case['curvature'] * (dx / math.cos(angle)) ** 2

    def aim_angle(self, launcher, target, context):
        case = self.contexts.get(context)
        if case is None:return None
        for name, value in [('target_x', target[0]), ('target_y', target[1]),
                            ('launcher_x', launcher[0]), ('launcher_y', launcher[1])]:
            finite(name, value)
        dx = target[0] - launcher[0]
        if not .9 * case['dx_min'] <= dx <= 1.1 * case['dx_max']:return None
        # u = tan(theta): a*u² + b*u + c = 0. Endpoint bracketing is
        # insufficient when a calibrated angular interval spans both arcs.
        a = case['curvature'] * dx * dx
        b = -case['gain'] * dx
        c = launcher[1] + a - target[1]
        discriminant = b*b - 4*a*c
        if discriminant < 0:return None
        q = -.5 * (b + math.copysign(math.sqrt(discriminant), b))
        roots = (q/a, c/q) if q else (-b/(2*a),)
        candidates = sorted(math.atan(root) for root in roots)
        for angle in candidates:
            if self.impact(launcher, angle, target[0], context) is not None:
                return angle
        return None

    def effective_uncertainty(self, context):
        case = self.contexts[context]
        return max(case['uncertainty_px'], case.get('end_to_end_uncertainty_px', 0.))

    def save(self, path):
        with Path(path).open('x', encoding='utf-8') as stream:
            json.dump(asdict(self), stream, indent=2)


def load_impact_model(path):
    from .calibration import _visual_json
    data = _visual_json(path)
    if isinstance(data,dict) and data.get('model_type')=='discrete-ballistics-v1':
        from .ballistics import DiscreteBallisticsModel
        return DiscreteBallisticsModel(data)
    if not isinstance(data, dict) or set(data) not in ({'profile_id', 'contexts', 'version'},
            {'profile_id', 'contexts', 'version', 'trigger_delay_ns', 'target_x_offset'}):
        raise ValueError('Schema de modele invalide')
    return ImpactModel(**data)


def fit_impact_model(samples, *, profile_id, trigger_delay_ns=0, target_x_offset=0.):
    import numpy as np
    grouped = {}
    for sample in samples:
        required = {'context', 'launcher_x', 'launcher_y', 'impact_x', 'impact_y'}
        if not isinstance(sample, dict) or not required <= set(sample):
            raise ValueError('Mesure d impact incomplete')
        text('context', sample['context'])
        for key in required - {'context'}:finite(key, sample[key])
        if 'flight_points' in sample:
            launch = fit_launch_track(sample['flight_points'], (sample['launcher_x'], sample['launcher_y']))
            angle = launch['launch_angle']
        else:
            angle = sample.get('release_angle')
            finite('release_angle', angle)
        dx = sample['impact_x'] - sample['launcher_x']
        if not dx > 0 or not -1.3 < angle < 1.3:
            raise ValueError('Mesure hors domaine du modele')
        grouped.setdefault(sample['context'], []).append((dx, angle, sample['impact_y'] - sample['launcher_y']))
    contexts = {}
    for key, rows in grouped.items():
        if len(rows) < 4:
            raise ValueError('Au moins quatre impacts distincts par contexte requis')
        if len(set((round(dx, 4), round(angle, 5)) for dx, angle, _ in rows)) < 4:
            raise ValueError('Mesures de calibration degenerees')
        x = np.array([[-dx * math.tan(angle), (dx / math.cos(angle)) ** 2] for dx, angle, _ in rows])
        y = np.array([vertical for _, _, vertical in rows])
        coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
        if rank != 2:raise ValueError('Mesures de calibration degenerees')
        errors = []
        for index in range(len(rows)):
            mask = np.arange(len(rows)) != index
            fitted, _, rank, _ = np.linalg.lstsq(x[mask], y[mask], rcond=None)
            if rank != 2:raise ValueError('Validation du modele degeneree')
            errors.append(abs(float(x[index] @ fitted - y[index])))
        worst = max(errors)
        contexts[key] = dict(gain=float(coefficients[0]), curvature=float(coefficients[1]),
            dx_min=min(dx for dx, _, _ in rows), dx_max=max(dx for dx, _, _ in rows),
            angle_min=min(angle for _, angle, _ in rows), angle_max=max(angle for _, angle, _ in rows),
            sample_count=len(rows), loo_max_error_px=worst, uncertainty_px=max(5., 1.5 * worst + 5.))
    version = 'empirical-launch-v2' if trigger_delay_ns or target_x_offset else 'empirical-release-v1'
    return ImpactModel(profile_id, contexts, version, trigger_delay_ns, target_x_offset)


def fit_launch_track(points, launcher):
    """Infer the launch angle from one consistently tracked projectile landmark.

    Points are measured ROI-relative (x,y) positions in flight order. Discard the
    first 200 horizontal pixels: the landmark can still belong to the throwing
    hand/animation inside the calibrated launcher area. A stationary arm pose
    after the click is not used as a launch-angle measurement.
    """
    import numpy as np
    from .models import point
    point('launcher', launcher)
    if not isinstance(points, (list, tuple)) or not 8 <= len(points) <= 1000:
        raise ValueError('Au moins huit positions de vol requises')
    for value in points:
        if not isinstance(value, (list, tuple)):
            raise ValueError('Paire de coordonnees de vol requise')
        point('flight point', tuple(value))
    measured = np.asarray(points, dtype=float)
    x, y = measured[:, 0] - launcher[0], measured[:, 1]
    free_flight = x > 200
    excluded = int(len(x) - np.count_nonzero(free_flight))
    x, y = x[free_flight], y[free_flight]
    if len(x) < 8:
        raise ValueError('Au moins huit positions hors de la zone de lancer requises')
    if x.min() <= 0 or np.any(np.diff(x) <= 0) or np.ptp(x) < 300:
        raise ValueError('Trajectoire trop courte, stationnaire ou non ordonnee')
    coefficients = np.polyfit(x, y, 2)
    curvature, slope, origin = (float(v) for v in coefficients)
    error = float(np.quantile(np.abs(y - np.polyval(coefficients, x)), .95))
    angle = math.atan(-slope)
    if (not 0 < curvature < .01 or not -1.3 < angle < 1.3
            or abs(origin - launcher[1]) > 60 or error > 3):
        raise ValueError('Ajustement de trajectoire instable ou incompatible')
    return dict(launch_angle=angle, curvature=curvature,
                origin_offset_y=origin-launcher[1], residual_p95_px=error, sample_count=len(x),
                excluded_near_launcher_points=excluded)


def fit_angular_motion(history):
    """Estimate local speed and supported acceleration from ten distinct poses.

    Times are relative to the newest pose. Never replace its measured angle by
    the fit intercept: timestamp/pose ownership stays explicit. If acceleration
    fails validation, return the stable six-pose local speed with alpha=0.
    """
    import numpy as np
    if len(history) < 4:return None
    last = history[-1][0]
    times = np.array([(stamp-last)/1e9 for stamp, _ in history], dtype=float)
    angles = np.array([angle for _, angle in history], dtype=float)
    if (not np.all(np.isfinite(times)) or not np.all(np.isfinite(angles))
            or np.any(np.diff(times) <= 0)):return None
    # Use the full window to distinguish acceleration from fit noise. Never
    # discard isolated poses or relax the residual threshold to obtain a fit.
    quadratic_times=times if len(history)>=10 and .05<=-times[0]<=.3 else None
    if quadratic_times is None:
        times=times[-6:];angles=angles[-6:]
        coefficients=np.polyfit(times,angles,1)
        residual=float(np.max(np.abs(angles-np.polyval(coefficients,times))))
        omega=float(coefficients[0])
        if not .03<=-times[0]<=.3 or residual>math.radians(.3) or not -4.<omega<-.1:return None
        return omega,0.,residual
    coefficients, covariance = np.polyfit(times, angles, 2, cov=True)
    alpha, omega = float(2*coefficients[0]), float(coefficients[1])
    residual = float(np.max(np.abs(angles-np.polyval(coefficients,times))))
    alpha_sigma = 2*math.sqrt(max(0.,float(covariance[0,0])))
    if (residual <= math.radians(.3) and abs(alpha) <= 20.
            and -.1 > omega > -4. and -.1 > omega+alpha*times[0] > -4.
            and abs(alpha) > max(.1, 2*alpha_sigma)):
        # Verify the acceleration against the last two poses withheld from a
        # separate fit. Correlated render jitter can otherwise look significant.
        train_t, train_a = times[:-2], angles[:-2]
        prior_q = np.polyfit(train_t, train_a, 2)
        prior_l = np.polyfit(train_t[-6:], train_a[-6:], 1)
        dt = times[-2:]-train_t[-1]
        prior_omega = 2*prior_q[0]*train_t[-1]+prior_q[1]
        error_q = np.abs(train_a[-1]+prior_omega*dt+prior_q[0]*dt*dt-angles[-2:])
        error_l = np.abs(train_a[-1]+prior_l[0]*dt-angles[-2:])
        if max(error_q) <= math.radians(.3) and np.mean(error_q) < np.mean(error_l):
            return omega, alpha, residual
    # An acceleration estimate dominated by noise must not move the command.
    t, a = times[-6:], angles[-6:]
    coefficients = np.polyfit(t, a, 1)
    omega = float(coefficients[0])
    residual = float(np.max(np.abs(a-np.polyval(coefficients,t))))
    if residual > math.radians(.3) or not -.1 > omega > -4.:return None
    return omega, 0., residual


def angular_crossing_time(angle, aim, omega, alpha):
    """Nearest crossing on the same descending branch, within 100 ms."""
    if not all(math.isfinite(v) for v in (angle, aim, omega, alpha)) or omega >= -.1:return None
    difference = angle-aim
    if abs(alpha) < 1e-8:
        candidates = [-difference/omega]
    else:
        discriminant = omega*omega-2*alpha*difference
        if discriminant < 0:return None
        q = -.5*(omega+math.copysign(math.sqrt(discriminant),omega))
        candidates = [q/(.5*alpha), difference/q] if q else [-omega/alpha]
    valid = [t for t in candidates if abs(t) <= .1 and omega+alpha*t < -.1]
    return min(valid,key=abs) if valid else None


class ReleasePredictor:
    """Bounded angular forecast: acceleration for v2, historical linear for v1."""
    def __init__(self, model, *, hold_ns=20_000_000):
        self.model = model
        self.hold_ns = hold_ns
        self.history = deque(maxlen=10 if model.version != 'empirical-release-v1' else 6)
        self.segment = None
        self.scene = None
        self.last_motion = None

    def predict(self, observation, profile, *, now_ns):
        self.last_motion = None
        sampled=observation.sample_ns if observation.sample_ns is not None else observation.capture_end_ns
        max_gap=250_000_000 if hasattr(self.model,'forecast') else 100_000_000
        maximum_age=50_000_000 if getattr(self.model,'clock_base',None) else 150_000_000
        if not 0<=now_ns-sampled<=maximum_age:
            self.history.clear();return None
        if (profile.profile_id != self.model.profile_id or not observation.complete
                or observation.invalid_reasons or observation.context_key not in self.model.contexts
                or now_ns < observation.capture_end_ns or now_ns - observation.capture_end_ns > 100_000_000):
            self.history.clear()
            return None
        if hasattr(self.model,'observe_motion'):self.model.observe_motion(observation)
        # Collect both branches for the clock, but release only while descending.
        if observation.arm_direction != -1:
            self.history.clear()
            return None
        segment = observation.session_id, observation.segment_index
        scene = observation.launcher_position, observation.target_center, observation.context_key, observation.wind_features
        if (self.segment != segment or self.scene != scene or (self.history and
                not 0 < sampled - self.history[-1][0] <= max_gap)):
            self.history.clear()
        self.segment = segment
        self.scene = scene
        if self.model.version != 'empirical-release-v1' and self.history:
            elapsed = sampled - self.history[-1][0]
            max_interval=max_gap if hasattr(self.model,'forecast') else 60_000_000
            max_delta=.4 if hasattr(self.model,'forecast') else .12
            delta = self.history[-1][1] - observation.arm_angle
            # A fresh desktop frame may repeat the same game pose. Do not
            # retimestamp it, forecast from it, or discard valid earlier poses.
            # A prolonged stall still invalidates the entire history.
            if 0 < elapsed <= max_interval and abs(delta) < 1e-9:
                return None
            if not (0 < elapsed <= max_interval and .003 < delta < max_delta
                    and .1 < delta / (elapsed / 1e9) < 4.):
                self.history.clear()
        self.history.append((sampled, observation.arm_angle))
        required = 1 if getattr(self.model,'clock_base',None) else (3 if hasattr(self.model,'forecast') else 4)
        if len(self.history) < required:return None
        t0 = self.history[0][0]
        times = [(stamp - t0) / 1e9 for stamp, _ in self.history]
        mean_t, mean_a = sum(times) / len(times), sum(a for _, a in self.history) / len(times)
        denominator = sum((t - mean_t) ** 2 for t in times)
        slope = (sum((t - mean_t) * (a - mean_a) for t, (_, a) in zip(times, self.history)) / denominator
                 if denominator>0 else (-1. if getattr(self.model,'clock_base',None) else 0.))
        if abs(slope) < .1 or slope * observation.arm_direction <= 0:return None
        motion = None
        if self.model.version != 'empirical-release-v1' and not hasattr(self.model,'forecast'):
            motion = fit_angular_motion(self.history)
            if motion is None:return None
            self.last_motion = dict(omega_rad_s=motion[0], alpha_rad_s2=motion[1],
                                    residual_rad=motion[2], used_acceleration=motion[1] != 0.)
        target = (observation.target_center[0] + self.model.target_x_offset, observation.target_center[1])
        aim = self.model.aim_angle(observation.launcher_position, target, observation.context_key)
        if aim is None:return None
        if hasattr(self.model,'forecast'):
            forecast=self.model.forecast(self.history,observation.arm_angle,aim)
            if forecast is None:return None
            crossing,omega,alpha,residual=forecast;motion=(omega,alpha,residual)
            self.last_motion=dict(omega_rad_s=omega,alpha_rad_s2=alpha,residual_rad=residual,used_acceleration=True,
                                  method=getattr(self.model,'forecast_policy','harmonic'))
            if getattr(self.model,'phase_diagnostics',None):self.last_motion.update(self.model.phase_diagnostics)
        # Forecast from the latest measured angle; no cached pixel is retimestamped.
        if hasattr(self.model,'forecast'):
            pass
        elif motion is not None:
            crossing = angular_crossing_time(observation.arm_angle, aim, motion[0], motion[1])
            if crossing is None:return None
        else:
            crossing = (aim-observation.arm_angle)/slope
        target_up_ns = sampled + int(crossing*1e9)
        case = self.model.contexts[observation.context_key]
        # Positive phase correction postpones the command. This is an empirical
        # mapping between displayed dart orientation and flight, not a measured
        # negative processing latency inside the game.
        trigger_delay_ns=(self.last_motion or {}).get('effective_trigger_delay_ns',self.model.trigger_delay_ns)
        # SendInput and the guarded hold consume time before mouse-up. Budget
        # their measured overhead separately from the flight/phase delay.
        input_overhead_ns=getattr(self.model,'input_overhead_ns',0)
        down_ns = (target_up_ns - self.hold_ns - input_overhead_ns - trigger_delay_ns
                   + case.get('phase_correction_ns', 0))
        horizon = 25_000_000 if self.model.version != 'empirical-release-v1' else 40_000_000
        if hasattr(self.model,'forecast'):horizon=getattr(self.model,'forecast_horizon_ns',200_000_000)
        if not now_ns <= down_ns <= now_ns + horizon:return None
        if motion is not None:
            command_time = (down_ns-sampled)/1e9
            if motion[0]+motion[1]*command_time >= -.1:return None
        uncertainty = self.model.effective_uncertainty(observation.context_key)
        predicted_impact=observation.target_center
        if getattr(self.model,'tick_mode',False) and self.last_motion is not None:
            predicted_impact=(observation.target_center[0],self.last_motion['predicted_impact_y'])
        # With an absolute mouse-up, a slightly late preparatory press does not
        # move the shot. Keep at least 20 ms of nominal lead for the native call.
        press_window_ns=(min(10_000_000,max(3_000_000,self.hold_ns-20_000_000))
                         if getattr(self.model,'absolute_mouse_up',False) else 3_000_000)
        return Prediction(observation.observation_id, profile.profile_id, profile.model_version,
                          observation.context_key, down_ns, down_ns + press_window_ns,
                          predicted_impact, uncertainty,
                          'vertical' if self.model.version != 'empirical-release-v1' else 'radial')
