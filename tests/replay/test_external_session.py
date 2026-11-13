"""All images and archives below are synthetic and created outside the project."""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from idleon_darts.models import Result
from idleon_darts.cli import main
from idleon_darts.replay import decode_png, replay_frames
from idleon_darts.session import SessionValidationError, open_session


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind+payload))


def png(scanlines=b'\0\xff\0\0\0\xff\0', *, width=2, height=1, colour=2):
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, colour, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


def fixture(root):
    (root/'frames').mkdir(parents=True)
    (root/'frames/00000000.png').write_bytes(png())
    (root/'frames/00000002.png').write_bytes(png())
    meta = dict(schema_version=1, purpose='private-calibration-only',
                created_utc='2026-11-13T12:00:00Z', region=dict(left=10, top=20, width=2, height=1),
                target_fps=60, clock='perf_counter_ns', timestamps='relative nanoseconds',
                target_window=dict(window_rect=[0, 0, 100, 100], dpi=144),
                status='complete', error=None, frames_written=2, capture_attempts=3,
                dropped_frames=1, missed_schedule_slots=0, event_queue_overflow=False,
                segments=2, recorded_seconds=0.2, effective_fps=10.)
    (root/'session.json').write_text(json.dumps(meta), encoding='utf-8')
    (root/'frames.csv').write_text('frame_index,segment_index,capture_start_ns,capture_end_ns,file\n'
                                   '0,1,10,20,frames/00000000.png\n'
                                   '2,2,200000010,200000020,frames/00000002.png\n', encoding='utf-8')
    write_events(root, [dict(kind='resume', t_ns=0, segment=1),
                        dict(kind='mouse', t_ns=30, segment=1, action='down', x=0, y=0),
                        dict(kind='pause', t_ns=100000000, segment=1, reason='test'),
                        dict(kind='resume', t_ns=200000000, segment=2),
                        dict(kind='mouse', t_ns=200000030, segment=2, action='up', x=1, y=0),
                        dict(kind='pause', t_ns=300000000, segment=2, reason='end')])
    return root


def write_events(root, events):
    (root/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events), encoding='utf-8')


def update_meta(root, **changes):
    path = root/'session.json'
    data = json.loads(path.read_text()) | changes
    path.write_text(json.dumps(data), encoding='utf-8')


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def make_zip(root, output):
    with zipfile.ZipFile(output, 'w') as z:
        for p in root.rglob('*'):
            if p.is_file():
                z.write(p, Path('recording')/p.relative_to(root))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = fixture(self.base/'external')

    def reject(self):
        with self.assertRaises(SessionValidationError):
            with open_session(self.root):
                pass

    def test_folder_is_read_only_and_replays_actual_times_and_bgr(self):
        before = snapshot(self.base)
        with open_session(self.root) as session:
            self.assertEqual(session.summary.frames_written, 2)
            self.assertEqual([r.frame_index for r in session.frames], [0, 2])
            first, second = list(replay_frames(session))
            self.assertEqual(first.frame.bgr, b'\0\0\xff\0\xff\0')
            self.assertEqual(second.frame.start_ns, 200000010)
            self.assertEqual((first.segment_index, second.segment_index), (1, 2))
        self.assertEqual(snapshot(self.base), before)

    def test_zip_is_read_without_extraction_or_file_creation(self):
        archive = self.base/'session.zip'
        make_zip(self.root, archive)
        before = snapshot(self.base)
        with patch.object(zipfile.ZipFile, 'extractall', side_effect=AssertionError('extraction')):
            with open_session(archive) as session:
                self.assertEqual(len(list(replay_frames(session))), 2)
        self.assertEqual(snapshot(self.base), before)

    def test_clicks_never_pair_across_pauses_or_create_confirmed_results(self):
        with open_session(self.root) as session:
            self.assertEqual(len(session.clicks), 2)
            self.assertIsNone(session.clicks[0].up_ns)
            self.assertIsNone(session.clicks[1].down_ns)
            self.assertTrue(all(c.result == Result.UNKNOWN for c in session.clicks))

    def test_late_callbacks_sorted_by_time_not_log_line(self):
        events = [dict(kind='resume', t_ns=0, segment=1),
                  dict(kind='dropped_frame', t_ns=60, frame_index=1, segment=1, reason='writer_queue_full'),
                  dict(kind='mouse', t_ns=30, segment=1, action='down', x=0, y=0),
                  dict(kind='mouse', t_ns=40, segment=1, action='up', x=1, y=0),
                  dict(kind='annotation', t_ns=50, segment=1, action='centre'),
                  dict(kind='pause', t_ns=100000000, segment=1, reason='test'),
                  dict(kind='resume', t_ns=200000000, segment=2),
                  dict(kind='pause', t_ns=300000000, segment=2, reason='end')]
        write_events(self.root, events)
        with open_session(self.root) as session:
            self.assertEqual([(c.down_ns, c.up_ns) for c in session.clicks], [(30, 40)])
            self.assertEqual(session.clicks[0].result, Result.UNKNOWN)
            self.assertEqual(session.annotations[0].action, 'centre')

    def test_completed_counter_inconsistencies_rejected(self):
        for change in [dict(frames_written=3), dict(capture_attempts=2), dict(dropped_frames=0),
                       dict(segments=3), dict(recorded_seconds=1.), dict(effective_fps=60.),
                       dict(event_queue_overflow=True), dict(error='failure')]:
            with self.subTest(change=change):
                original = (self.root/'session.json').read_text()
                update_meta(self.root, **change)
                self.reject()
                (self.root/'session.json').write_text(original)

    def test_live_rejected_partial_requires_explicit_option(self):
        update_meta(self.root, status='in_progress')
        with self.assertRaises(SessionValidationError):
            open_session(self.root, allow_partial=True)
        update_meta(self.root, status='error', error='encoder failed', capture_attempts=4)
        self.reject()
        with open_session(self.root, allow_partial=True) as session:
            self.assertFalse(session.summary.complete)
            self.assertTrue(session.warnings)

    def test_partial_open_segment_is_reported_and_extra_images_ignored(self):
        events = (self.root/'events.jsonl').read_text().splitlines()
        (self.root/'events.jsonl').write_text('\n'.join(events[:-1])+'\n')
        update_meta(self.root, status='error', error='interrupted')
        (self.root/'frames/00000003.png').write_bytes(b'incomplete encoder output')
        with open_session(self.root, allow_partial=True) as session:
            self.assertFalse(session.summary.complete)
            self.assertGreaterEqual(len(session.warnings), 3)
            self.assertEqual(len(list(replay_frames(session))), 2)

    def test_extra_source_and_html_are_not_executed(self):
        (self.root/'evil.py').write_text('raise RuntimeError("must not execute")')
        (self.root/'voir.html').write_text('<script>throw new Error("must not execute")</script>')
        with open_session(self.root) as session:
            self.assertEqual(session.summary.frames_written, 2)

    def test_validation_command_reports_partial_and_invalid_sessions(self):
        before = snapshot(self.base)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(['validate-session', str(self.root)]), 0)
        self.assertEqual(json.loads(out.getvalue())['validation'], 'complete')
        self.assertEqual(snapshot(self.base), before)
        update_meta(self.root, status='error', error='interrupted')
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(['validate-session', str(self.root)]), 1)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(['validate-session', str(self.root), '--allow-partial']), 0)
        self.assertFalse(json.loads(out.getvalue())['summary']['complete'])
        self.assertEqual(json.loads(out.getvalue())['validation'], 'partial')

    def test_invalid_metadata_schema_types_geometry_and_missing_files(self):
        original = (self.root/'session.json').read_text()
        for change in [dict(schema_version=2), dict(frames_written=True), dict(target_fps=0),
                       dict(region=dict(left=10, top=20, width=-1, height=1)),
                       dict(target_window=dict(window_rect=[0,0,1,1], dpi=144)),
                       dict(recorded_seconds=float('nan')), dict(clock='time.time')]:
            with self.subTest(change=change):
                update_meta(self.root, **change)
                self.reject()
                (self.root/'session.json').write_text(original)
        (self.root/'events.jsonl').unlink()
        self.reject()

    def test_duplicate_json_keys_rejected(self):
        (self.root/'session.json').write_text('{"schema_version":1,"schema_version":1}')
        self.reject()

    def test_frame_traversal_absolute_windows_paths_and_missing_png_rejected(self):
        original = (self.root/'frames.csv').read_text()
        for path in ['../outside.png', '/tmp/outside.png', 'C:/outside.png',
                     'frames\\00000000.png', 'frames/../outside.png', 'frames/00000099.png']:
            with self.subTest(path=path):
                (self.root/'frames.csv').write_text(original.replace('frames/00000000.png', path))
                self.reject()
        (self.root/'frames.csv').write_text(original)
        (self.root/'frames/00000000.png').unlink()
        self.reject()

    def test_symlink_frame_and_symlink_parent_rejected(self):
        frame = self.root/'frames/00000000.png'
        outside = self.base/'outside.png'
        outside.write_bytes(frame.read_bytes())
        frame.unlink()
        frame.symlink_to(outside)
        self.reject()
        frame.unlink()
        (self.root/'frames/00000002.png').unlink()
        (self.root/'frames').rmdir()
        (self.base/'outside-frames').mkdir()
        (self.root/'frames').symlink_to(self.base/'outside-frames', target_is_directory=True)
        self.reject()

    def test_bad_frame_order_overlap_segment_and_duplicate_references(self):
        path = self.root/'frames.csv'
        original = path.read_text()
        for replacement in ['0,2,200000010,200000020,frames/00000002.png',
                            '2,2,200000010,200000009,frames/00000002.png',
                            '2,1,15,25,frames/00000002.png',
                            '2,2,400000000,400000010,frames/00000002.png']:
            with self.subTest(replacement=replacement):
                path.write_text(original.replace('2,2,200000010,200000020,frames/00000002.png', replacement))
                self.reject()
        path.write_text(original.replace('file\n', 'file,extra\n', 1))
        self.reject()

    def test_bad_events_and_unbalanced_segment_boundaries_rejected(self):
        path = self.root/'events.jsonl'
        original = path.read_text()
        events = [json.loads(line) for line in original.splitlines()]
        cases = [events[:-1], events+[dict(kind='resume', t_ns=400000000, segment=2)],
                 events+[dict(kind='mouse', t_ns=500000000, segment=2, action='up', x=0, y=0)],
                 events+[dict(kind='mouse', t_ns=50, segment=1, action='down', x=2, y=0)],
                 events+[dict(kind='dropped_frame', t_ns=50, segment=1, frame_index=0, reason='full')]]
        for data in cases:
            with self.subTest(data=data):
                write_events(self.root, data)
                self.reject()
        path.write_text(original+'{broken json}\n')
        self.reject()

    def test_png_corruption_bad_zlib_wrong_dimensions_and_filter_rejected(self):
        frame = self.root/'frames/00000000.png'
        samples = [b'not png', png()[:-5], png()+b'trailing', png(width=3),
                   png(b'\5\xff\0\0\0\xff\0'),
                   png(b'\0\xff'), png(b'\0'+b'a'*10000)]
        corrupted = bytearray(png()); corrupted[-1] ^= 1; samples.append(bytes(corrupted))
        header = chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 2, 0, 0, 0))
        samples.append(b'\x89PNG\r\n\x1a\n'+header+chunk(b'IDAT', b'invalid-zlib')+chunk(b'IEND', b''))
        for data in samples:
            with self.subTest(size=len(data)):
                frame.write_bytes(data)
                self.reject()

    def test_change_after_validation_is_rejected_during_replay(self):
        with open_session(self.root) as session:
            (self.root/'frames/00000000.png').write_bytes(png(b'\0\0\0\0\0\0\0'))
            with self.assertRaises(SessionValidationError):
                list(replay_frames(session))

    def test_closed_session_cannot_be_read(self):
        with open_session(self.root) as session:
            pass
        with self.assertRaises(SessionValidationError):
            list(replay_frames(session))

    def test_malformed_zip_and_unsafe_names_symlinks_duplicates_rejected(self):
        archive = self.base/'bad.zip'
        archive.write_bytes(b'not a zip')
        with self.assertRaises(SessionValidationError):
            open_session(archive)
        for name in ['../escape', '/absolute', 'C:/escape', 'folder\\escape']:
            make_zip(self.root, archive)
            with zipfile.ZipFile(archive, 'a') as z:
                z.writestr(name, 'bad')
            with self.subTest(name=name), self.assertRaises(SessionValidationError):
                open_session(archive)
        make_zip(self.root, archive)
        with zipfile.ZipFile(archive, 'a') as z:
            entry = zipfile.ZipInfo('link')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(entry, '/outside')
        with self.assertRaises(SessionValidationError):
            open_session(archive)
        make_zip(self.root, archive)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(archive, 'a') as z:
                z.writestr('recording/session.json', '{}')
        with self.assertRaises(SessionValidationError):
            open_session(archive)

    def test_multiple_sessions_and_wrong_crc_in_zip_rejected(self):
        archive = self.base/'multiple.zip'
        make_zip(self.root, archive)
        with zipfile.ZipFile(archive, 'a') as z:
            z.writestr('another/session.json', '{}')
        with self.assertRaises(SessionValidationError):
            open_session(archive)
        make_zip(self.root, archive)
        data = archive.read_bytes().replace(b'private-calibration-only', b'private-calibration-BAD!', 1)
        archive.write_bytes(data)
        with self.assertRaises(SessionValidationError):
            open_session(archive)

    def test_project_local_session_is_refused(self):
        # Tell the reader this temp directory is a protected project root.
        with self.assertRaises(SessionValidationError):
            open_session(self.root, forbidden_roots=(self.base,))


class PngTests(unittest.TestCase):
    def test_rgb_filters_decode_to_expected_pixels(self):
        # Two rows, one pixel each. Expected RGB rows (10,20,30), (11,22,33).
        for filter_id, row in [(0, bytes([11,22,33])), (1, bytes([11,22,33])),
                               (2, bytes([1,2,3])), (3, bytes([6,12,18])), (4, bytes([1,2,3]))]:
            data = png(b'\0\x0a\x14\x1e'+bytes([filter_id])+row, width=1, height=2)
            self.assertEqual(decode_png(data, width=1, height=2), bytes([30,20,10,33,22,11]))

    def test_multicolumn_filters_include_left_and_upper_left_pixels(self):
        rows = {
            0: ([10,20,30,40,50,60], [11,22,33,44,55,66]),
            1: ([10,20,30,30,30,30], [11,22,33,33,33,33]),
            2: ([10,20,30,40,50,60], [1,2,3,4,5,6]),
            3: ([10,20,30,35,40,45], [6,12,18,19,19,20]),
            4: ([10,20,30,30,30,30], [1,2,3,4,5,6]),
        }
        for filter_id, (first, second) in rows.items():
            with self.subTest(filter_id=filter_id):
                raw = bytes([filter_id]+first+[filter_id]+second)
                self.assertEqual(decode_png(png(raw, width=2, height=2), width=2, height=2),
                                 bytes([30,20,10,60,50,40,33,22,11,66,55,44]))

    def test_palette_rgba_and_interlaced_variants_are_explicitly_unsupported(self):
        interlaced = (b'\x89PNG\r\n\x1a\n'
                      + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 1, 8, 2, 0, 0, 1))
                      + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0\0\xff\0'))
                      + chunk(b'IEND', b''))
        for data in (png(colour=3), png(colour=6), interlaced):
            with self.subTest(data=data), self.assertRaises(SessionValidationError):
                decode_png(data, width=2, height=1)


if __name__ == '__main__':
    unittest.main()
