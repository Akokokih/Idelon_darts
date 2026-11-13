"""Offline image replay. No Windows imports, clocks, writes or synthetic inputs.

The decoder accepts static non-interlaced RGB8 PNGs, the recorder's format. It
checks CRC, zlib completion, scanline lengths and all five standard RGB filters.
Other PNG variants fail explicitly instead of silently changing pixel semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable, Iterator, Protocol, TYPE_CHECKING
import zlib

from .capture import Frame
from .models import Decision, Observation
from .session import MAX_IMAGE_BYTES, MAX_PIXELS, SessionValidationError

if TYPE_CHECKING:
    from .session import ValidatedSession


PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _paeth(a, b, c):
    estimate = a+b-c
    da, db, dc = abs(estimate-a), abs(estimate-b), abs(estimate-c)
    if da <= db and da <= dc:
        return a
    return b if db <= dc else c


def decode_png(data: bytes, *, width: int, height: int) -> bytes:
    """Decode recorder-compatible PNG to BGR bytes with bounded decompression."""
    if (type(width) is not int or type(height) is not int or width < 1 or height < 1
            or width*height > MAX_PIXELS or len(data) > MAX_IMAGE_BYTES
            or not data.startswith(PNG_SIGNATURE)):
        raise SessionValidationError('Signature PNG ou dimensions invalides')
    offset = len(PNG_SIGNATURE)
    header = False
    ended = False
    idat_started = False
    idat_closed = False
    compressed = bytearray()
    while offset < len(data):
        if len(data)-offset < 12:
            raise SessionValidationError('Chunk PNG tronque')
        length = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset+4:offset+8]
        finish = offset+12+length
        if finish > len(data) or any(not (65 <= c <= 90 or 97 <= c <= 122) for c in kind):
            raise SessionValidationError('Chunk PNG invalide')
        payload = data[offset+8:offset+8+length]
        expected_crc = struct.unpack_from('>I', data, offset+8+length)[0]
        if zlib.crc32(kind+payload) != expected_crc:
            raise SessionValidationError('CRC PNG incorrect')
        if not header and kind != b'IHDR':
            raise SessionValidationError('IHDR doit etre le premier chunk')
        if kind == b'IHDR':
            if header or length != 13:
                raise SessionValidationError('IHDR invalide ou duplique')
            actual_w, actual_h, depth, colour, method, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (actual_w, actual_h) != (width, height):
                raise SessionValidationError('Dimensions PNG differentes de la zone de capture')
            if (depth, colour, method, filtering, interlace) != (8, 2, 0, 0, 0):
                raise SessionValidationError('PNG incompatible : RGB8 statique non entrelace requis')
            header = True
        elif kind == b'IDAT':
            if idat_closed:
                raise SessionValidationError('Chunks IDAT non consecutifs')
            idat_started = True
            compressed.extend(payload)
        elif kind == b'IEND':
            if length or not idat_started or finish != len(data):
                raise SessionValidationError('Fin PNG invalide ou donnees ajoutees')
            ended = True
        else:
            if kind in (b'acTL', b'fcTL', b'fdAT', b'tRNS') or not kind[0] & 32:
                raise SessionValidationError('Extension PNG incompatible avec les captures RGB8')
            if idat_started:
                idat_closed = True
        offset = finish
    if not ended:
        raise SessionValidationError('PNG sans IEND')
    stride = width*3
    expected = (stride+1)*height
    try:
        stream = zlib.decompressobj()
        raw = stream.decompress(compressed, expected+1)
        if (len(raw) != expected or not stream.eof or stream.unused_data or stream.unconsumed_tail):
            raise SessionValidationError('Donnees PNG decompressees incoherentes')
    except zlib.error as exc:
        raise SessionValidationError('Flux PNG zlib illisible') from exc
    rgb = bytearray(stride*height)
    previous = bytes(stride)
    for y in range(height):
        start = y*(stride+1)
        filter_id = raw[start]
        if filter_id > 4:
            raise SessionValidationError('Filtre PNG inconnu')
        row = bytearray(raw[start+1:start+1+stride])
        if filter_id:
            for x in range(stride):
                left = row[x-3] if x >= 3 else 0
                above = previous[x]
                upper_left = previous[x-3] if x >= 3 else 0
                if filter_id == 1:
                    predictor = left
                elif filter_id == 2:
                    predictor = above
                elif filter_id == 3:
                    predictor = (left+above)//2
                else:
                    predictor = _paeth(left, above, upper_left)
                row[x] = (row[x]+predictor) & 255
        rgb[y*stride:(y+1)*stride] = row
        previous = row
    bgr = bytearray(len(rgb))
    bgr[0::3], bgr[1::3], bgr[2::3] = rgb[2::3], rgb[1::3], rgb[0::3]
    return bytes(bgr)


@dataclass(frozen=True)
class RecordedFrame:
    frame_index: int
    segment_index: int
    frame: Frame


def replay_frames(session: ValidatedSession) -> Iterator[RecordedFrame]:
    """Decode one frame at a time, preserving real timestamps and pause segments."""
    for record in session.frames:
        region = session.summary.region
        bgr = decode_png(session.image_bytes(record), width=region.width, height=region.height)
        frame = Frame(str(record.frame_index), record.capture_start_ns, record.capture_end_ns, region, bgr)
        yield RecordedFrame(record.frame_index, record.segment_index, frame)


@dataclass(frozen=True)
class ReplayRecord:
    observation_id: str
    decision: Decision


class ReplayEngine(Protocol):
    def review(self, observations: Iterable[Observation]) -> Iterable[ReplayRecord]: ...
