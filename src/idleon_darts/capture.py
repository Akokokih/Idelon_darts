"""Guarded screen capture. No images are persisted and no inputs are sent."""
from dataclasses import dataclass
from threading import get_ident
from time import perf_counter_ns, sleep
from typing import Protocol
from uuid import uuid4
from .models import Rect, integer


@dataclass(frozen=True)
class Frame:
    frame_id: str
    start_ns: int
    end_ns: int
    region: Rect
    bgr: bytes
    sample_ns: int | None = None

    def __post_init__(self):
        integer('start_ns', self.start_ns, 0)
        integer('end_ns', self.end_ns, self.start_ns)
        if self.sample_ns is not None:
            integer('sample_ns',self.sample_ns,0)
            if self.sample_ns>self.end_ns:raise ValueError('Horodatage image futur')
        if not isinstance(self.region, Rect) or not isinstance(self.bgr, bytes):
            raise ValueError('Frame: region et pixels BGR requis')
        if len(self.bgr) != self.region.width * self.region.height * 3:
            raise ValueError('Dimensions des pixels BGR incoherentes')


class FrameSource(Protocol):
    def grab(self) -> Frame: ...
    def close(self) -> None: ...


class CaptureError(RuntimeError):
    """Capture unavailable or invalidated; no frame may be used."""


def _mss_backend():
    try:
        import mss
    except ImportError as exc:
        raise CaptureError('Installer la dependance optionnelle : pip install -e ".[capture]"') from exc
    return mss.mss()


@dataclass(frozen=True)
class _BGRImage:
    width: int
    height: int
    bgr: bytes
    sample_ns: int | None = None


class _DXGIBackend:
    """Synchronous fresh-frame acquisition; never use DXcam's cached frames.

    Copy the temporary BGR view once to immutable bytes before another grab can
    overwrite it. DXcam's compiled numpy processor avoids Python channel slicing.
    No background ring buffer or video_mode duplicates are used.
    """

    def __init__(self, *, camera_factory=None, backend='dxgi'):
        if camera_factory is None:
            try:
                import dxcam
            except ImportError as exc:
                raise CaptureError('Installer la dependance optionnelle : pip install -e ".[capture]"') from exc
            camera_factory = dxcam.create
        self._camera = camera_factory(output_color='BGR', processor_backend='numpy',
                                      backend=backend, max_buffer_len=2)
        if self._camera.is_capturing:
            raise CaptureError('Camera DXGI deja utilisee en arriere-plan')

    def grab(self, region):
        left, top = region['left'], region['top']
        width, height = region['width'], region['height']
        image = self._camera.grab(region=(left, top, left + width, top + height),
                                  copy=False, new_frame_only=True)
        if image is None:
            return None
        if image.shape != (height, width, 3) or image.dtype.name != 'uint8':
            raise CaptureError('Format DXGI BGR incoherent')
        duplicator=getattr(self._camera,'_duplicator',None)
        seconds=getattr(duplicator,'latest_frame_time',None)
        sample_ns=round(seconds*1e9) if seconds and seconds>0 else None
        if sample_ns is not None and perf_counter_ns()-sample_ns>100_000_000:return None
        return _BGRImage(width, height, image.tobytes(order='C'),sample_ns)

    def close(self):
        self._camera.release()


class WindowsFrameSource:
    """One explicit window and physical ROI, fixed for this source's lifetime.

    DXGI is the default; MSS remains an explicit compatibility backend.
    Construct, grab and close on the same thread. Geometry/DPI changes require
    a new source. Focus can return, but this adapter never arms the controller.
    The two snapshots cannot detect a focus change that returns between them.
    """

    def __init__(self, desktop, region: Rect | None = None, *, backend='auto', backend_factory=None):
        if backend not in ('auto', 'dxgi', 'winrt', 'mss'):
            raise ValueError('Backend de capture inconnu')
        self.backend = 'dxgi' if backend=='auto' else backend
        self._fallback = backend=='auto' and backend_factory is None
        self.desktop = desktop
        self._thread = get_ident()
        self._backend = None
        self._closed = False
        self._invalidated = False
        self._prefix = uuid4().hex
        self._index = 0
        self._expected = desktop.snapshot()
        self.region = self._expected.rect if region is None else region
        if not isinstance(self.region, Rect) or not self._expected.rect.contains(self.region):
            raise CaptureError('Region hors de la fenetre')
        self._validate(self._expected)
        try:
            with desktop.physical_pixels():
                factory=backend_factory or (_mss_backend if self.backend=='mss' else lambda:_DXGIBackend(backend=self.backend))
                self._backend = factory()
        except CaptureError:
            raise
        except Exception as exc:
            raise CaptureError(f'Initialisation {self.backend} impossible : {exc}') from exc

    def _validate(self, context):
        if self._invalidated or (context.window_id, context.rect, context.dpi) != (
                self._expected.window_id, self._expected.rect, self._expected.dpi):
            self._invalidated = True
            raise CaptureError('Fenetre/geometrie/DPI modifies : nouvelle capture requise')
        if not context.foreground or not context.game_visible:
            raise CaptureError('Fenetre non visible, hors ecran principal ou sans focus')

    def _check_thread(self):
        if get_ident() != self._thread:
            raise CaptureError('Capture utilisee depuis un autre thread')

    def grab(self) -> Frame:
        self._check_thread()
        if self._closed:
            raise CaptureError('Capture fermee')
        try:
            start = perf_counter_ns()
            while True:
                self._validate(self.desktop.snapshot())
                with self.desktop.physical_pixels():
                    image = self._backend.grab(dict(left=self.region.left, top=self.region.top,
                                                   width=self.region.width, height=self.region.height))
                if image is not None:
                    break
                self._validate(self.desktop.snapshot())
                if perf_counter_ns() - start >= 100_000_000:
                    if self._fallback and self._index==0:
                        self._fallback=False
                        with self.desktop.physical_pixels():
                            self._backend.close()
                            try:
                                self._backend=_DXGIBackend(backend='winrt');self.backend='winrt'
                            except Exception:
                                self._backend=_mss_backend();self.backend='mss'
                        start=perf_counter_ns()
                        continue
                    raise CaptureError('Aucune nouvelle image pendant 100 ms')
                sleep(.001)
            if (image.width, image.height) != (self.region.width, self.region.height):
                raise CaptureError('Dimensions de capture incoherentes')
            if isinstance(image, _BGRImage):
                pixels = image.bgr
            else:
                raw = bytes(image.bgra)
                if len(raw) != self.region.width * self.region.height * 4:
                    raise CaptureError('Pixels MSS incomplets')
                converted = bytearray(self.region.width * self.region.height * 3)
                converted[0::3], converted[1::3], converted[2::3] = raw[0::4], raw[1::4], raw[2::4]
                pixels = bytes(converted)
            self._validate(self.desktop.snapshot())
            end = perf_counter_ns()
            sample=getattr(image,'sample_ns',None)
            # WGC may label a frame with its next presentation timestamp.
            # Bound that small future offset by the local acquisition end.
            if sample is not None and 0<sample-end<=20_000_000:sample=end
            if sample is not None and not 0<=end-sample<=100_000_000:
                raise CaptureError(f'Horodatage de capture périmé ou incompatible ({(end-sample)/1e6:.1f} ms)')
            frame = Frame(f'{self._prefix}-{self._index}', start, end, self.region, pixels,sample)
            self._index += 1
            return frame
        except CaptureError:
            raise
        except Exception as exc:
            raise CaptureError(f'Capture refusee : {exc}') from exc

    def close(self):
        self._check_thread()
        if not self._closed:
            self._closed = True
            if self._backend is not None:
                try:
                    with self.desktop.physical_pixels():
                        self._backend.close()
                except CaptureError:
                    raise
                except Exception as exc:
                    raise CaptureError(f'Fermeture {self.backend} impossible : {exc}') from exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
