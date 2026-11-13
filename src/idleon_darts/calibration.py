"""Strict profile loading; no trained model or fitted constants are supplied yet."""
from dataclasses import fields
import json
from pathlib import Path
from .models import Profile, Rect


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
