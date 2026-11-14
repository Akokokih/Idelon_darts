"""Explicit calibration and bounded visual checks. No input adapter is used."""
from collections import Counter
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import time


def run(args):
    from .calibration import calibrate_visual, load_visual_calibration, external_directory, _visual_json
    from .capture import WindowsFrameSource, CaptureError
    from .windows_io import WindowsDesktop
    from .models import Rect
    try:
        # Validate all paths before touching the desktop.
        if args.command == 'calibrate-visual':
            destination = external_directory(args.output)
            if destination.exists():
                raise ValueError('Le dossier de calibration existe deja')
            regions = _visual_json(args.regions)
            if not isinstance(regions, dict) or set(regions) != {'scene', 'arm', 'board', 'anchor', 'wind_none'}:
                raise ValueError('Regions scene, arm, board, anchor et wind_none requises')
            regions = {key: Rect(**value) for key, value in regions.items()}
            scene = regions.pop('scene')
            if any(not scene.contains(region) for region in regions.values()):
                raise ValueError('Repere en dehors de la scene choisie')
            regions = {key: Rect(region.left - scene.left, region.top - scene.top, region.width, region.height)
                       for key, region in regions.items()}
        else:
            from .perception import CalibratedPerception
            calibration = load_visual_calibration(args.calibration)
            detector = CalibratedPerception(calibration)
            scene = calibration.profile.roi
            for path in (args.report, args.preview):
                if path and external_directory(path).exists():
                    raise ValueError('Choisir un nouveau fichier de resultat')
        if args.delay:
            print(f'Dans {args.delay:g} s : afficher le mini-jeu au premier plan.', file=sys.stderr)
            time.sleep(args.delay)
        desktop = WindowsDesktop(args.window_id)
        context = desktop.snapshot()
        if args.command == 'check-calibration' and (context.rect != calibration.profile.window_rect or
                                                   context.dpi != calibration.profile.dpi):
            raise ValueError('Geometrie/DPI modifies : refaire la calibration visuelle')
        with WindowsFrameSource(desktop, scene) as source:
            stable_context = desktop.snapshot()
            if stable_context.rect != context.rect or stable_context.dpi != context.dpi:
                raise ValueError('Geometrie/DPI modifies pendant l ouverture de la capture')
            if args.command == 'calibrate-visual':
                calibration = calibrate_visual((source.grab() for _ in range(args.frames)), context,
                                                regions, destination)
                print(json.dumps(dict(directory=str(destination), profile_id=calibration.profile.profile_id,
                    pivot=calibration.pivot, target_size=calibration.target_size, metrics=calibration.metrics,
                    model_calibrated=False, inputs_sent=False), indent=2))
                return 0
            observations = []
            error = None
            started = time.perf_counter_ns()
            try:
                for _ in range(args.frames):
                    frame = source.grab()
                    observations.append(detector.detect(frame, calibration.profile,
                                        session_id='visual-check', segment_index=1))
            except CaptureError as exc:
                error = str(exc)
            elapsed = (time.perf_counter_ns() - started) / 1e9
        reasons = Counter(reason for observation in observations for reason in observation.invalid_reasons)
        report = dict(complete=error is None, error=error, frames=len(observations),
            profile_id=calibration.profile.profile_id, elapsed_seconds=elapsed,
            effective_fps=len(observations) / max(elapsed, 1e-9), inputs_sent=False, model_calibrated=False,
            counts={name: sum(getattr(observation, name) is not None for observation in observations)
                    for name in ('launcher_position', 'arm_angle', 'arm_direction', 'target_center', 'wind_features')},
            complete_observations=sum(not observation.invalid_reasons for observation in observations),
            invalid_reasons=dict(reasons))
        if args.report:
            path = external_directory(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as stream:
                json.dump(report | dict(observations=[asdict(o) for o in observations]), stream, indent=2)
        if args.preview and observations:
            from .perception import annotate_observation
            from .vision import cv2
            path = external_directory(args.preview)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(path), annotate_observation(frame, observations[-1], calibration)):
                raise OSError('Ecriture de l apercu impossible')
        print(json.dumps(report, indent=2))
        return 0 if error is None else 1
    except (ValueError, TypeError, OSError, CaptureError, ImportError) as exc:
        print(f'Calibration refusee : {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Calibration interrompue.', file=sys.stderr)
        return 130
