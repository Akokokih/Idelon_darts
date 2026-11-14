"""Read-only validation of external recorder folders and ZIPs. Never extracts files."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Protocol
import zipfile

from .models import Rect, Result, finite, integer, text

MAX_FRAMES = 100_000
MAX_EVENTS = 1_000_000
MAX_PIXELS = 16_000_000
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_INDEX_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 150_000
FRAME_COLUMNS = ['frame_index', 'segment_index', 'capture_start_ns', 'capture_end_ns', 'file']


class SessionValidationError(ValueError):
    """Invalid, incomplete or changed external data; nothing has been copied."""


def safe_name(name: str) -> str:
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or '\x00' in name or name.startswith('/')
            or any(p in ('', '.', '..') for p in name.split('/'))):
        raise SessionValidationError(f'Chemin de session interdit : {name!r}')
    return name


def _json(raw: bytes):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise SessionValidationError(f'Cle JSON dupliquee : {key}')
            obj[key] = value
        return obj
    def invalid(value):
        raise SessionValidationError(f'Nombre JSON non fini : {value}')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)


def _natural(value: str) -> int:
    if not re.fullmatch(r'[0-9]{1,20}', value):
        raise SessionValidationError('Entier CSV invalide')
    return int(value)


def _forbidden_roots(extra):
    candidates = [*Path(__file__).resolve().parents, Path.cwd(), *Path.cwd().parents]
    roots = {p.resolve() for p in extra}
    for p in candidates:
        if (p/'pyproject.toml').is_file() and (p/'.specify').is_dir():
            roots.add(p.resolve())
    return roots


class _Source:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.archive = None
        self.prefix = ''
        if path.is_symlink():
            raise SessionValidationError('Session symbolique interdite')
        if path.is_dir():
            # Enumerate names, without traversing symbolic directories.
            import os
            names = set()
            for parent, directories, files in os.walk(self.path, followlinks=False):
                for item in directories + files:
                    p = Path(parent)/item
                    if p.is_symlink():
                        raise SessionValidationError('Lien symbolique dans la session')
                    if len(names) + len(directories) > MAX_MEMBERS:
                        raise SessionValidationError('Trop de fichiers de session')
                for item in files:
                    names.add(safe_name((Path(parent)/item).relative_to(self.path).as_posix()))
            self.names = frozenset(names)
        elif path.is_file():
            self.archive = zipfile.ZipFile(self.path, 'r')
            try:
                infos = self.archive.infolist()
                if len(infos) > MAX_MEMBERS:
                    raise SessionValidationError('Archive trop volumineuse')
                names = set()
                all_names = set()
                total = 0
                for info in infos:
                    # ZipInfo normalizes Windows separators when reading; validate
                    # the original member name before that normalization hides it.
                    original = info.orig_filename
                    safe_name(original[:-1] if original.endswith('/') else original)
                    name = safe_name(info.filename[:-1] if info.is_dir() else info.filename)
                    if name.casefold() in all_names:
                        raise SessionValidationError('Nom de membre ZIP duplique ou ambigu')
                    all_names.add(name.casefold())
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                        raise SessionValidationError('Lien, fichier special ou chiffrement ZIP interdit')
                    if info.file_size > MAX_IMAGE_BYTES:
                        raise SessionValidationError('Membre ZIP trop volumineux')
                    total += info.file_size
                    if total > 32 * 1024**3:
                        raise SessionValidationError('Volume ZIP decompresse trop important')
                    if not info.is_dir():
                        names.add(name)
                manifests = [n for n in names if PurePosixPath(n).name == 'session.json']
                if len(manifests) != 1:
                    raise SessionValidationError('Une seule session est attendue dans le ZIP')
                self.prefix = manifests[0][:-len('session.json')]
                self.names = frozenset(n[len(self.prefix):] for n in names if n.startswith(self.prefix))
            except BaseException:
                self.close()
                raise
        else:
            raise SessionValidationError('Session introuvable : dossier ou ZIP attendu')

    def read(self, name, *, limit):
        safe_name(name)
        if name not in self.names:
            raise SessionValidationError(f'Fichier de session absent : {name}')
        if self.archive:
            with self.archive.open(self.prefix+name, 'r') as stream:
                raw = stream.read(limit+1)
        else:
            path = self.path
            for component in name.split('/'):
                path = path/component
                if path.is_symlink():
                    raise SessionValidationError('Lien symbolique apparu dans la session')
            if not path.resolve().is_relative_to(self.path):
                raise SessionValidationError('Fichier hors session')
            with path.open('rb') as stream:
                raw = stream.read(limit+1)
        if len(raw) > limit:
            raise SessionValidationError(f'Fichier trop volumineux : {name}')
        return raw

    def close(self):
        if self.archive is not None:
            self.archive.close()


@dataclass(frozen=True)
class SessionSummary:
    schema_version: int
    status: str
    region: Rect
    frames_written: int
    segments: int
    dropped_frames: int
    recorded_seconds: float
    effective_fps: float

    @property
    def complete(self):
        return self.status == 'complete'


@dataclass(frozen=True)
class FrameRecord:
    frame_index: int
    segment_index: int
    capture_start_ns: int
    capture_end_ns: int
    file: str
    sha256: str


@dataclass(frozen=True)
class RecordedEvent:
    kind: str
    t_ns: int
    segment: int
    action: str | None = None
    x: int | None = None
    y: int | None = None
    frame_index: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ClickSpan:
    segment_index: int
    down_ns: int | None
    up_ns: int | None
    result: Result = Result.UNKNOWN


def _clicks(events):
    pending = {}
    clicks = []
    for event in events:
        if event.kind != 'mouse':
            continue
        segment = event.segment
        if event.action == 'down':
            if segment in pending:
                clicks.append(ClickSpan(segment, pending[segment], None))
            pending[segment] = event.t_ns
        else:
            clicks.append(ClickSpan(segment, pending.pop(segment, None), event.t_ns))
    clicks.extend(ClickSpan(segment, down, None) for segment, down in pending.items())
    return tuple(sorted(clicks, key=lambda c: (c.segment_index, c.down_ns if c.down_ns is not None else c.up_ns)))


class ValidatedSession:
    def __init__(self, source, summary, frames, events, notices):
        self._source = source
        self.summary = summary
        self.frames = tuple(frames)
        self.events = tuple(events)
        self.warnings = tuple(notices)
        self.clicks = _clicks(events)
        self.annotations = tuple(e for e in events if e.kind == 'annotation')
        self._closed = False

    @property
    def root(self):
        """External source path (a ZIP path for archive-backed sessions)."""
        return self._source.path

    def image_bytes(self, record):
        if self._closed:
            raise SessionValidationError('Session fermee')
        try:
            raw = self._source.read(record.file, limit=MAX_IMAGE_BYTES)
            if hashlib.sha256(raw).hexdigest() != record.sha256:
                raise SessionValidationError('Image modifiee depuis sa validation')
            return raw
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SessionValidationError('Image devenue illisible') from exc

    def close(self):
        self._closed = True
        self._source.close()

    def __enter__(self):
        if self._closed:
            raise SessionValidationError('Session fermee')
        return self

    def __exit__(self, *_):
        self.close()


def _metadata(source, allow_partial):
    meta = _json(source.read('session.json', limit=1024*1024))
    if not isinstance(meta, dict):
        raise SessionValidationError('Metadonnees JSON objet attendues')
    integer('schema_version', meta['schema_version'], 1)
    if meta['schema_version'] != 1 or meta['clock'] != 'perf_counter_ns':
        raise SessionValidationError('Schema ou horloge incompatible')
    if meta['purpose'] != 'private-calibration-only':
        raise SessionValidationError('Format de session de calibration attendu')
    timestamp = datetime.fromisoformat(meta['created_utc'].replace('Z', '+00:00'))
    if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
        raise SessionValidationError('Date UTC attendue')
    text('timestamps', meta['timestamps'])
    if meta['status'] not in ('complete', 'error'):
        raise SessionValidationError('Session en cours ou statut inconnu')
    partial = meta['status'] == 'error'
    if partial and not allow_partial:
        raise SessionValidationError('Session partielle : accord explicite allow_partial requis')
    notices = ['Session partielle : impropre a une validation de performance complete.'] if partial else []
    region = Rect(**meta['region'])
    if region.width*region.height > MAX_PIXELS:
        raise SessionValidationError('Dimensions de capture trop importantes')
    integer('target_fps', meta['target_fps'], 1)
    if meta['target_fps'] > 120:
        raise SessionValidationError('Cadence cible incompatible')
    window = meta['target_window']
    if not isinstance(window, dict) or len(window['window_rect']) != 4:
        raise SessionValidationError('Geometrie de fenetre invalide')
    left, top, right, bottom = window['window_rect']
    for value in (left, top, right, bottom):
        integer('window_rect', value)
    integer('dpi', window['dpi'], 1)
    if not Rect(left, top, right-left, bottom-top).contains(region):
        raise SessionValidationError('Capture hors fenetre')
    for name in ('frames_written', 'capture_attempts', 'dropped_frames',
                 'missed_schedule_slots', 'segments'):
        integer(name, meta[name], 0)
    if not 1 <= meta['frames_written'] <= MAX_FRAMES or not 1 <= meta['segments'] <= MAX_EVENTS:
        raise SessionValidationError('Session vide ou trop volumineuse')
    if type(meta['event_queue_overflow']) is not bool:
        raise SessionValidationError('event_queue_overflow doit etre booleen')
    for key in ('recorded_seconds', 'effective_fps'):
        finite(key, meta[key], 0)
    if not partial and (meta['error'] is not None or meta['event_queue_overflow']):
        raise SessionValidationError('Session marquee complete avec erreur ou perte d’evenements')
    if partial and meta['event_queue_overflow']:
        notices.append('Des evenements ont ete perdus par le collecteur.')
    accounted = meta['frames_written'] + meta['dropped_frames']
    if meta['capture_attempts'] < accounted or (not partial and meta['capture_attempts'] != accounted):
        raise SessionValidationError('Compteurs de capture incoherents')
    if partial and meta['capture_attempts'] != accounted:
        notices.append('Tentatives non ecrites pendant l’erreur du collecteur.')
    return meta, region, notices


def _events(source, meta, region, notices):
    raw = source.read('events.jsonl', limit=MAX_INDEX_BYTES)
    lines = raw.splitlines()
    if len(lines) > MAX_EVENTS:
        raise SessionValidationError('Trop d’evenements')
    events = []
    bounds = {}
    active = None
    last_boundary = -1
    for line in lines:
        data = _json(line)
        if not isinstance(data, dict):
            raise SessionValidationError('Evenement objet attendu')
        kind, t, segment = data['kind'], data['t_ns'], data['segment']
        integer('event time', t, 0)
        integer('event segment', segment, 1)
        if segment > meta['segments']:
            raise SessionValidationError('Evenement dans un segment inexistant')
        if kind in ('resume', 'pause'):
            if t < last_boundary:
                raise SessionValidationError('Chronologie des pauses invalide')
            last_boundary = t
            # Lifecycle records are emitted synchronously; mouse callbacks can lag.
            if kind == 'resume':
                if active is not None or segment != len(bounds)+1:
                    raise SessionValidationError('Reprise sans pause ou segment duplique')
                active = segment
                bounds[segment] = [t, None]
                event = RecordedEvent(kind, t, segment)
            else:
                if active != segment:
                    raise SessionValidationError('Pause sans segment actif')
                bounds[segment][1] = t
                active = None
                text('pause reason', data['reason'])
                event = RecordedEvent(kind, t, segment, reason=data['reason'])
        elif kind == 'mouse':
            if data['action'] not in ('down', 'up'):
                raise SessionValidationError('Action souris inconnue')
            integer('x', data['x'], 0)
            integer('y', data['y'], 0)
            if data['x'] >= region.width or data['y'] >= region.height:
                raise SessionValidationError('Clic hors zone de capture')
            event = RecordedEvent(kind, t, segment, data['action'], data['x'], data['y'])
        elif kind == 'annotation':
            if data['action'] not in ('centre', 'autre'):
                raise SessionValidationError('Annotation inconnue')
            event = RecordedEvent(kind, t, segment, data['action'])
        elif kind == 'dropped_frame':
            integer('dropped index', data['frame_index'], 0)
            text('dropped reason', data['reason'])
            event = RecordedEvent(kind, t, segment, frame_index=data['frame_index'], reason=data['reason'])
        else:
            raise SessionValidationError('Type d’evenement inconnu')
        events.append(event)
    if len(bounds) != meta['segments']:
        raise SessionValidationError('Nombre de segments incoherent')
    if active is not None:
        if meta['status'] == 'complete':
            raise SessionValidationError('Session complete sans pause finale')
        notices.append('Dernier segment sans borne de fin apres interruption.')
    for event in events:
        if event.segment not in bounds:
            raise SessionValidationError('Segment d’evenement inexistant')
        start, end = bounds[event.segment]
        if event.t_ns < start or (end is not None and event.t_ns > end):
            raise SessionValidationError('Evenement hors des bornes de son segment')
    if meta['status'] == 'complete':
        duration = sum(end-start for start, end in bounds.values())/1e9
        if not math.isclose(duration, meta['recorded_seconds'], rel_tol=1e-9, abs_tol=1e-6):
            raise SessionValidationError('Duree enregistree incoherente')
    expected_fps = meta['frames_written']/max(meta['recorded_seconds'], .001)
    if not math.isclose(expected_fps, meta['effective_fps'], rel_tol=1e-6, abs_tol=1e-6):
        raise SessionValidationError('Debit mesure incoherent')
    return tuple(sorted(events, key=lambda event: event.t_ns)), bounds


def _frames(source, meta, region, events, bounds, notices):
    from .replay import decode_png
    raw = source.read('frames.csv', limit=MAX_INDEX_BYTES)
    reader = csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
    if next(reader, None) != FRAME_COLUMNS:
        raise SessionValidationError('Entete frames.csv incompatible')
    frames, names, ids = [], set(), set()
    previous_index, previous_end, previous_segment = -1, -1, 0
    for row in reader:
        if len(row) != 5 or len(frames) >= MAX_FRAMES:
            raise SessionValidationError('Ligne CSV invalide ou trop d’images')
        index, segment, start, end = map(_natural, row[:4])
        name = safe_name(row[4])
        if name != f'frames/{index:08d}.png' or name in names:
            raise SessionValidationError('Reference d’image incoherente ou dupliquee')
        if (index <= previous_index or index >= meta['capture_attempts'] or start < previous_end
                or end < start or segment < previous_segment or segment not in bounds):
            raise SessionValidationError('Chronologie ou indice d’image incoherent')
        lower, upper = bounds[segment]
        if start < lower or (upper is not None and end > upper):
            raise SessionValidationError('Capture hors des bornes de son segment')
        image = source.read(name, limit=MAX_IMAGE_BYTES)
        decode_png(image, width=region.width, height=region.height)
        frames.append(FrameRecord(index, segment, start, end, name, hashlib.sha256(image).hexdigest()))
        names.add(name)
        ids.add(index)
        previous_index, previous_end, previous_segment = index, end, segment
    if len(frames) != meta['frames_written']:
        raise SessionValidationError('Nombre d’images ecrites incoherent')
    extra = {n for n in source.names if n.startswith('frames/') and n.lower().endswith('.png')} - names
    if extra:
        if meta['status'] == 'complete':
            raise SessionValidationError('Images non indexees dans une session complete')
        notices.append('Images non indexees ignorees dans la session partielle.')
    dropped = set()
    for event in events:
        if event.kind != 'dropped_frame':
            continue
        if event.frame_index in ids or event.frame_index in dropped or event.frame_index >= meta['capture_attempts']:
            raise SessionValidationError('Abandon d’image incoherent')
        dropped.add(event.frame_index)
    if len(dropped) > meta['dropped_frames']:
        raise SessionValidationError('Trop d’abandons d’image dans les evenements')
    return frames


def open_session(path: str | Path, *, allow_partial=False, forbidden_roots=()) -> ValidatedSession:
    """Validate every indexed PNG; retain only indexes and hashes, not decoded pixels.

    Use as a context manager. ZIP members are read in place, never extracted. The
    reader refuses data inside discovered project roots. Additional forbidden roots
    can be supplied by an installed application without weakening default checks.
    """
    source = None
    try:
        if type(allow_partial) is not bool:
            raise SessionValidationError('allow_partial doit etre booleen')
        path = Path(path).absolute()
        if any(path.resolve().is_relative_to(root) for root in _forbidden_roots(forbidden_roots)):
            raise SessionValidationError('Les enregistrements doivent rester hors du projet')
        source = _Source(path)
        meta, region, notices = _metadata(source, allow_partial)
        events, bounds = _events(source, meta, region, notices)
        frames = _frames(source, meta, region, events, bounds, notices)
        summary = SessionSummary(1, meta['status'], region, meta['frames_written'], meta['segments'],
                                 meta['dropped_frames'], meta['recorded_seconds'], meta['effective_fps'])
        return ValidatedSession(source, summary, frames, events, notices)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, UnicodeError,
            zipfile.BadZipFile, csv.Error, RuntimeError, RecursionError) as exc:
        if source is not None:
            source.close()
        if isinstance(exc, SessionValidationError):
            raise
        raise SessionValidationError(f'Session invalide : {exc}') from exc


class SessionJournal(Protocol):
    def append(self, event: dict) -> None: ...
    def close(self) -> None: ...
