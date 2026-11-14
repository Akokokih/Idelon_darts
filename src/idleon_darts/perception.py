"""Perception contract. No visual detections are fabricated without recordings."""
from typing import Protocol
from collections import deque
import math
from .capture import Frame
from .models import Observation, Profile


class Perception(Protocol):
    def detect(self, frame: Frame, profile: Profile, *, session_id: str,
               segment_index: int) -> Observation: ...


class CalibratedPerception:
    """Geometry-specific visual observer; no result classifier or shot predictor.

    Only annotated wind references are recognized. All other winds remain
    unknown. launcher_position is the fitted visual rotation pivot, not a proven
    projectile origin. Direction is inferred from recent measured orientations.
    The historical arm_angle field measures the white dart shaft held in hand,
    not an anatomical arm segment or a proven initial flight velocity direction.
    """

    def __init__(self, calibration):
        from .vision import cv2, np
        import struct
        self.calibration = calibration
        self.profile = calibration.profile
        self._history = deque(maxlen=8)
        self._segment = None
        self._offset = (0, 0)
        self.templates = {}
        for key, filename in [('anchor', 'anchor.png'), ('wind_none', 'wind-none.png')]:
            with (calibration.directory / filename).open('rb') as stream:
                data = stream.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024 or len(data) < 24 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Modele visuel PNG invalide')
            width, height = struct.unpack('>II', data[16:24])
            region = calibration.regions[key]
            if (width, height) != (region.width, region.height) or width * height > 16_000_000:
                raise ValueError('Dimensions du modele visuel invalides')
            image = cv2.imdecode(np.frombuffer(data, dtype='uint8'), cv2.IMREAD_COLOR)
            if image is None or image.shape != (height, width, 3):
                raise ValueError('Modele visuel illisible')
            self.templates[key] = image
        self.wind_references = []
        self.hud = None
        if (calibration.directory/'hud.json').exists():
            from .hud import HudReader
            self.hud=HudReader(calibration.directory)
        library = calibration.directory / 'wind-library.json'
        if library.exists():
            from .calibration import _visual_json
            from .models import Rect, finite
            import re
            entries = _visual_json(library)
            if not isinstance(entries, list) or len(entries) > 32:raise ValueError('Bibliotheque de vent invalide')
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {'key','region','features','threshold'}:
                    raise ValueError('Reference de vent invalide')
                key = entry['key']
                if not isinstance(key, str) or not re.fullmatch('[a-z][a-z0-9-]{1,50}', key) or key == 'wind-none':
                    raise ValueError('Nom de vent invalide')
                region = Rect(**entry['region'])
                if not Rect(0,0,calibration.profile.roi.width,calibration.profile.roi.height).contains(region):
                    raise ValueError('Reference de vent hors image')
                features = entry['features']
                if not isinstance(features, list) or len(features) != 2:raise ValueError('Vecteur de vent requis')
                for feature in features:finite('wind feature', feature)
                finite('wind threshold', entry['threshold'], .95)
                if entry['threshold'] > 1:raise ValueError('Seuil de vent invalide')
                file = calibration.directory / f'{key}.png'
                if file.stat().st_size > 2_000_000:raise ValueError('Reference de vent trop grande')
                data = file.read_bytes()
                if len(data)<24 or not data.startswith(b'\x89PNG\r\n\x1a\n') or struct.unpack('>II',data[16:24]) != (region.width,region.height):
                    raise ValueError('Reference de vent PNG invalide')
                template = cv2.imdecode(np.frombuffer(data,dtype='uint8'),cv2.IMREAD_COLOR)
                if template is None:raise ValueError('Reference de vent illisible')
                self.wind_references.append((key,region,tuple(features),entry['threshold'],template))

    def detect(self, frame: Frame, profile: Profile, *, session_id: str, segment_index: int) -> Observation:
        from .vision import np, find_blade, find_red_target, template_score, locate_template
        from .models import Rect
        if profile != self.profile or frame.region != profile.roi:
            raise ValueError('Image/profil incompatible avec la calibration visuelle')
        image = np.frombuffer(frame.bgr, dtype='uint8').reshape(frame.region.height, frame.region.width, 3)
        calibration = self.calibration
        sampled=frame.sample_ns if frame.sample_ns is not None else frame.end_ns
        reasons = []
        anchor = calibration.regions['anchor']
        current_anchor = Rect(anchor.left + self._offset[0], anchor.top + self._offset[1], anchor.width, anchor.height)
        anchor_score = template_score(image, current_anchor, self.templates['anchor'])
        previous_offset = self._offset
        if anchor_score < calibration.template_threshold:
            located = locate_template(image, self.templates['anchor'], threshold=calibration.template_threshold)
            if located is not None:
                position, anchor_score = located
                self._offset = (position[0] - anchor.left, position[1] - anchor.top)
        anchor_valid = anchor_score >= calibration.template_threshold
        if not anchor_valid:
            reasons.append('launcher-anchor-unknown')
        target = find_red_target(image, calibration.regions['board'], expected_size=calibration.target_size)
        if target is None:
            reasons.append('target-unknown')
        wind_score = template_score(image, calibration.regions['wind_none'], self.templates['wind_none'])
        wind_valid = wind_score >= calibration.template_threshold
        wind_key, wind_features = ('wind-none', (0.,)) if wind_valid else (None, None)
        matches = []
        for key, region, features, threshold, template in self.wind_references:
            score = template_score(image, region, template)
            if score >= threshold:matches.append((key, features, score))
        if matches:
            if len(matches) == 1 and not wind_valid:
                wind_key, wind_features, wind_score = matches[0]
                wind_valid = True
            else:
                wind_valid, wind_key, wind_features = False, None, None
        if self.hud is not None and (wind_key!='wind-none' or self.hud.none_mask is not None):
            if self.hud.none_mask is not None:wind_valid=False;wind_key=None;wind_features=None
            reading=self.hud.wind(image)
            if reading is not None:
                wind_valid=True;wind_key='wind-none' if reading['mph']==0 else 'wind-vector';wind_features=reading['features'];wind_score=reading['quality']
        if not wind_valid:
            reasons.append('wind-unknown')
        arm = calibration.regions['arm']
        shifted_arm = Rect(arm.left + self._offset[0], arm.top + self._offset[1], arm.width, arm.height)
        bounds = Rect(0, 0, frame.region.width, frame.region.height)
        scale=calibration.metrics.get('vision_scale',1.)
        line = find_blade(image, shifted_arm,area_min=400*scale*scale,area_max=1400*scale*scale,
                          length_min=50*scale,length_max=180*scale) if anchor_valid and bounds.contains(shifted_arm) else None
        pivot = (calibration.pivot[0] + self._offset[0], calibration.pivot[1] + self._offset[1])
        if line is not None:
            delta = (line.center[0] - pivot[0], line.center[1] - pivot[1])
            distance = abs(-line.vector[1] * delta[0] + line.vector[0] * delta[1])
            if distance > 8*scale or not 60*scale <= math.hypot(*delta) <= 200*scale:
                line = None
        if line is None:
            reasons.append('arm-unknown')
        direction = None
        max_gap=250_000_000 if calibration.metrics.get('scale') else 100_000_000
        segment = session_id, segment_index
        if (segment != self._segment or previous_offset != self._offset or not anchor_valid or line is None or
                (self._history and not 0 < sampled - self._history[-1][0] <= max_gap)):
            self._history.clear()
        self._segment = segment
        if line is not None:
            if not self._history or line.angle!=self._history[-1][1]:self._history.append((sampled, line.angle))
            if len(self._history) >= 2:
                history=list(self._history)[-2:]
                times = np.array([(time - history[0][0]) / 1e9 for time, _ in history])
                angles = np.array([angle for _, angle in history])
                centered = times - times.mean()
                denominator = float(centered @ centered)
                slope = float(centered @ (angles - angles.mean()) / denominator) if denominator > 0 else 0.
                if abs(slope) > .03 and float(np.ptp(angles)) > math.radians(.1):
                    direction = 1 if slope > 0 else -1
        if direction is None:
            reasons.append('arm-direction-unknown')
        target_center = None if target is None else (target[0].left + target[0].width / 2,
                                                     target[0].top + target[0].height / 2)
        quality = min(anchor_score, wind_score, target[1] if target else 0.,
                      line.ratio / (line.ratio + 1) if line else 0.) if not reasons else 0.
        return Observation(frame.frame_id, session_id, segment_index, frame.start_ns, frame.end_ns,
            pivot if anchor_valid else None, line.angle if line else None, direction,
            target_center, min(target[0].width, target[0].height) / 2 if target else None,
            wind_features, wind_key, float(quality), tuple(reasons),
            target_half_height=target[0].height / 2 if target else None,sample_ns=frame.sample_ns)


def annotate_observation(frame, observation, calibration):
    from .vision import np, cv2
    image = np.frombuffer(frame.bgr, dtype='uint8').reshape(frame.region.height, frame.region.width, 3).copy()
    for name, region in calibration.regions.items():
        if name in ('arm', 'anchor') and observation.launcher_position is not None:
            from .models import Rect
            dx = round(observation.launcher_position[0] - calibration.pivot[0])
            dy = round(observation.launcher_position[1] - calibration.pivot[1])
            region = Rect(region.left + dx, region.top + dy, region.width, region.height)
        cv2.rectangle(image, (region.left, region.top),
                      (region.left + region.width, region.top + region.height), (0, 200, 255), 2)
        label={'arm':'flechette','board':'cible','anchor':'plateforme','wind_none':'vent'}.get(name,name)
        cv2.putText(image, label, (region.left, max(20, region.top - 8)), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 200, 255), 2)
    if observation.target_center is not None:
        center = tuple(round(v) for v in observation.target_center)
        cv2.circle(image, center, round(observation.target_radius), (0, 255, 0), 2)
        cv2.drawMarker(image, center, (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
    if observation.launcher_position is not None:
        pivot = tuple(round(v) for v in observation.launcher_position)
        cv2.circle(image, pivot, 6, (0, 255, 255), 2)
        if observation.arm_angle is not None:
            tip = (round(pivot[0] + 180 * math.cos(observation.arm_angle)),
                   round(pivot[1] - 180 * math.sin(observation.arm_angle)))
            cv2.line(image, pivot, tip, (0, 255, 0), 2)
    text = ', '.join(observation.invalid_reasons) or 'Apercu des reperes visuels'
    cv2.putText(image, text, (15, image.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
    return image
