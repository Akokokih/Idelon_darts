"""Strict profile loading; no trained model or fitted constants are supplied yet."""
from dataclasses import dataclass, fields, asdict
import json
from pathlib import Path
from .models import Profile, Rect, point, integer, finite


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Cle JSON dupliquee : {key}')
        result[key] = value
    return result


def load_profile(path: str | Path) -> Profile:
    file = Path(path)
    with file.open('r', encoding='utf-8') as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise ValueError('Profil trop volumineux')
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        expected = {f.name for f in fields(Profile)}
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError('Champs du profil absents ou inconnus')
        for key in ('window_rect', 'roi'):
            if not isinstance(data[key], dict) or set(data[key]) != {'left', 'top', 'width', 'height'}:
                raise ValueError(f'{key}: rectangle invalide')
            data[key] = Rect(**data[key])
        if not isinstance(data['calibration_coverage'], list):
            raise ValueError('calibration_coverage: liste requise')
        data['calibration_coverage'] = tuple(data['calibration_coverage'])
        return Profile(**data)
    except (TypeError, KeyError) as exc:
        raise ValueError('Profil invalide') from exc


VISUAL_VERSION = 'colour-pca-v1'
VISUAL_REGIONS = {'arm', 'board', 'anchor', 'wind_none'}


@dataclass(frozen=True)
class VisualCalibration:
    directory: Path
    profile: Profile
    regions: dict[str, Rect]
    pivot: tuple[float, float]
    target_size: tuple[int, int]
    template_threshold: float
    metrics: dict

    def __post_init__(self):
        if self.profile.detector_version != VISUAL_VERSION or set(self.regions) != VISUAL_REGIONS:
            raise ValueError('Version ou regions de calibration visuelle invalides')
        bounds = Rect(0, 0, self.profile.roi.width, self.profile.roi.height)
        if any(not isinstance(r, Rect) or not bounds.contains(r) for r in self.regions.values()):
            raise ValueError('Repere hors ROI')
        point('pivot', self.pivot)
        if not (0 <= self.pivot[0] < bounds.width and 0 <= self.pivot[1] < bounds.height):
            raise ValueError('Pivot hors ROI')
        if not isinstance(self.target_size, tuple) or len(self.target_size) != 2:
            raise ValueError('Dimensions de cible invalides')
        for value in self.target_size:
            integer('target_size', value, 1)
        if any(v > maximum for v, maximum in zip(self.target_size,
                (self.regions['board'].width, self.regions['board'].height))):
            raise ValueError('Cible hors panneau')
        finite('template_threshold', self.template_threshold, .9)
        if self.template_threshold > 1 or not isinstance(self.metrics, dict):
            raise ValueError('Qualite de calibration invalide')


def external_directory(path):
    destination = Path(path).resolve()
    project = Path(__file__).resolve().parents[2]
    if destination.is_relative_to(project):
        raise ValueError('Conserver les captures et profils a l exterieur du depot')
    return destination


def _visual_json(path):
    with Path(path).open('r', encoding='utf-8') as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise ValueError('Calibration visuelle trop volumineuse')
    return json.loads(raw, object_pairs_hook=_unique_object)


def load_visual_calibration(directory) -> VisualCalibration:
    directory = Path(directory).resolve()
    profile = load_profile(directory / 'profile.json')
    data = _visual_json(directory / 'visual.json')
    expected = {'schema_version', 'profile_id', 'regions', 'pivot', 'target_size',
                'template_threshold', 'metrics'}
    if (not isinstance(data, dict) or set(data) != expected or type(data['schema_version']) is not int
            or data['schema_version'] != 1 or data['profile_id'] != profile.profile_id):
        raise ValueError('Schema de calibration visuelle invalide')
    try:
        if not isinstance(data['regions'], dict) or set(data['regions']) != VISUAL_REGIONS:
            raise ValueError('Regions visuelles invalides')
        regions = {key: Rect(**value) for key, value in data['regions'].items()}
        return VisualCalibration(directory, profile, regions, tuple(data['pivot']),
                                 tuple(data['target_size']), data['template_threshold'], data['metrics'])
    except (TypeError, KeyError) as exc:
        raise ValueError('Calibration visuelle invalide') from exc


def calibrate_visual(frames, context, regions: dict[str, Rect], destination) -> VisualCalibration:
    """Fit visual geometry from a sweep, never a trajectory or automatic-play model.

    Regions are relative to frame.region. wind_none is a human-annotated reference
    which must visibly say None. The resulting profile has no model or coverage.
    """
    from datetime import datetime, timezone
    from itertools import chain
    from uuid import uuid4
    from .vision import np, cv2, crop, find_blade, fit_pivot, find_red_target
    destination = external_directory(destination)
    if destination.exists():
        raise ValueError('Choisir un nouveau dossier de calibration, sans ecraser un profil')
    if set(regions) != VISUAL_REGIONS:
        raise ValueError('Regions arm, board, anchor et wind_none requises')
    iterator = iter(frames)
    first = next(iterator, None)
    if first is None or not context.rect.contains(first.region):
        raise ValueError('Image de calibration absente ou hors fenetre')
    bounds = Rect(0, 0, first.region.width, first.region.height)
    if any(not isinstance(r, Rect) or not bounds.contains(r) for r in regions.values()):
        raise ValueError('Region de calibration hors image')
    reference = np.frombuffer(first.bgr, dtype='uint8').reshape(bounds.height, bounds.width, 3)
    target = find_red_target(reference, regions['board'])
    if target is None:
        raise ValueError('Zone rouge absente ou ambigue dans la reference')
    lines, total, previous = [], 0, -1
    for frame in chain((first,), iterator):
        if frame.region != first.region or frame.end_ns <= previous:
            raise ValueError('Geometrie ou chronologie du balayage incoherente')
        previous = frame.end_ns
        image = np.frombuffer(frame.bgr, dtype='uint8').reshape(bounds.height, bounds.width, 3)
        line = find_blade(image, regions['arm'])
        if line is not None:
            lines.append(line)
        total += 1
    if len(lines) < .9 * total:
        raise ValueError('Trop de lames inconnues dans le balayage de calibration')
    pivot, metrics = fit_pivot(lines)
    metrics['frames'] = total
    metrics['reference_end_ns'] = first.end_ns
    profile = Profile(1, uuid4().hex, datetime.now(timezone.utc).isoformat(), context.rect,
                      first.region, context.dpi, VISUAL_VERSION, None, ())
    calibration = VisualCalibration(destination, profile, dict(regions), pivot,
        (target[0].width, target[0].height), .995, metrics)
    destination.mkdir(parents=True, exist_ok=False)
    for filename, image in [('reference.png', reference),
                            ('anchor.png', crop(reference, regions['anchor'])),
                            ('wind-none.png', crop(reference, regions['wind_none']))]:
        if not cv2.imwrite(str(destination / filename), image):
            raise OSError(f'Ecriture impossible : {filename}')
    (destination / 'profile.json').write_text(json.dumps(asdict(profile), indent=2), encoding='utf-8')
    # Write completion metadata last; an interrupted folder cannot be loaded.
    (destination / 'visual.json').write_text(json.dumps(dict(schema_version=1,
        profile_id=profile.profile_id, regions={key: asdict(value) for key, value in regions.items()},
        pivot=pivot, target_size=calibration.target_size, template_threshold=.995, metrics=metrics), indent=2), encoding='utf-8')
    return calibration
