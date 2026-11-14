"""One explicitly armed experimental shot; always stops for result confirmation."""
from dataclasses import replace, asdict
from pathlib import Path
from time import perf_counter_ns, sleep
import json
import math
from contextlib import nullcontext
from uuid import uuid4
from .calibration import load_visual_calibration, external_directory
from .prediction import load_impact_model, ReleasePredictor
from .capture import WindowsFrameSource, CaptureError
from .windows_io import WindowsDesktop
from .native_input import WindowsInputAdapter
from .perception import CalibratedPerception, annotate_observation
from .controller import Controller
from .models import Rect


def run(args):
    cancel = getattr(args, 'cancel_event', None)
    def cancelled():return cancel is not None and cancel.is_set()
    if not args.arm:
        print(json.dumps(dict(state='paused', inputs_sent=False, reason='explicit_arm_required')))
        return 0
    output = external_directory(args.output)
    if output.exists():raise ValueError('Choisir un nouveau dossier de test')
    calibration = load_visual_calibration(args.calibration)
    pending = calibration.directory / 'pending-shot.json'
    if pending.exists():raise ValueError('Confirmer le resultat du tir precedent avant un autre test')
    model = getattr(args,'model_instance',None) or load_impact_model(args.model)
    if model.profile_id != calibration.profile.profile_id:raise ValueError('Modele lie a un autre profil')
    profile = replace(calibration.profile, model_version=model.version,
                      calibration_coverage=tuple(model.contexts))
    calibration = replace(calibration, profile=profile)
    detector = getattr(args,'detector_instance',None) or CalibratedPerception(calibration)
    absolute_up=getattr(model,'absolute_mouse_up',False)
    hold_ms=model.press_lead_ms if absolute_up else args.hold_ms
    predictor = ReleasePredictor(model, hold_ns=int(hold_ms * 1e6))
    desktop = WindowsDesktop(args.window_id)
    context = desktop.snapshot()
    supervised = bool(getattr(args, 'supervised_calibration', False))
    controller = Controller(profile, min_confidence=.6 if model.version=='discrete-ballistics-v1' else .8,
        max_age_ns=250_000_000 if model.version=='discrete-ballistics-v1' else 100_000_000,
        require_centre_precision=not supervised)
    controller.arm(context, now_ns=perf_counter_ns())
    point = (args.click_x, args.click_y)
    if not profile.roi.contains(Rect(*point, 1, 1)):
        raise ValueError('Point de clic hors scene')
    adapter = WindowsInputAdapter(desktop, context, point, hold_ms=hold_ms)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(mode='experimental-one-shot', profile_id=profile.profile_id,
                  inputs_sent=False, receipt=None, observations=[], model_version=model.version,
                  result='unknown', pending_result=False)
    report['forecast_policy'] = (getattr(model,'forecast_policy','harmonic-physics-v1') if hasattr(model,'forecast') else
                                ('acceleration-aware-v1' if model.version == 'empirical-launch-v2' else 'historical-linear'))
    report['supervised_calibration'] = supervised
    report['precision_requirement'] = 'nominal-centre-only' if supervised else 'uncertainty-contained-in-centre'
    shot_id = uuid4().hex
    # Acquire the per-profile inter-process reservation before the timing loop.
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(dict(shot_id=shot_id, output=str(output), result='unknown', stage='preparing'), stream)
    frame = observation = None
    before_frame=before_observation=None
    from .shot_recording import FlightRecorder
    recording=FlightRecorder(getattr(args,'record_flight',True))
    motion_session=getattr(args,'motion_session_id',output.name)
    try:
        deadline = perf_counter_ns() + int(args.max_wait * 1e9)
        shared_source=getattr(args,'frame_source',None)
        with (nullcontext(shared_source) if shared_source is not None else WindowsFrameSource(desktop, profile.roi)) as source:
            while perf_counter_ns() < deadline:
                if cancelled():raise RuntimeError('Arrêt demandé depuis l’application')
                if adapter.stopped():raise RuntimeError('F8 demande')
                frame = source.grab()
                observation = detector.detect(frame, profile, session_id=motion_session, segment_index=1)
                report['observations'].append(asdict(observation))
                if hasattr(model,'bind_observation') and observation.context_key is not None:model.bind_observation(observation)
                if observation.invalid_reasons:
                    if set(observation.invalid_reasons) <= {'arm-unknown','arm-direction-unknown'}:
                        if 'arm-unknown' in observation.invalid_reasons:predictor.history.clear()
                        continue
                    raise RuntimeError('Observation inconnue : ' + ','.join(observation.invalid_reasons))
                case = model.contexts.get(observation.context_key)
                if case is None:
                    raise RuntimeError('Vent reconnu mais hors couverture du modele')
                tolerance = (observation.target_half_height if model.version != 'empirical-release-v1'
                             else observation.target_radius)
                if tolerance is None or (not supervised and model.effective_uncertainty(observation.context_key) > tolerance):
                    raise RuntimeError('Incertitude du modele superieure au rayon de la cible')
                prediction = predictor.predict(observation, profile, now_ns=perf_counter_ns())
                if prediction is None:continue
                # Short, guarded wait. Reservation rechecks context and observation age.
                while perf_counter_ns() < prediction.release_ns:
                    if cancelled() or adapter.stopped() or desktop.snapshot() != context:raise RuntimeError('Test suspendu')
                    sleep(.0005)
                decision = controller.reserve_shot(shot_id, observation, prediction,
                                                   desktop.snapshot(), now_ns=perf_counter_ns())
                if not decision.allowed:
                    if controller.state.value == 'paused':raise RuntimeError(decision.reason)
                    continue
                before_frame, before_observation = frame, observation
                aim_target=(observation.target_center[0]+model.target_x_offset,observation.target_center[1])
                report['aim_angle_rad']=model.aim_angle(observation.launcher_position,aim_target,observation.context_key)
                report['model_at_shot']=dict(trigger_delay_ns=(predictor.last_motion or {}).get('effective_trigger_delay_ns',model.trigger_delay_ns),
                    base_trigger_delay_ns=model.trigger_delay_ns,target_x_offset=model.target_x_offset,
                    input_overhead_ns=getattr(model,'input_overhead_ns',0),
                    absolute_mouse_up=absolute_up,press_lead_ms=hold_ms,
                    amplitude_rad=getattr(model,'amplitude',None),wind=getattr(model,'wind',None))
                if cancelled():raise RuntimeError('Arrêt demandé avant le clic')
                input_options=dict(not_after_ns=prediction.valid_until_ns)
                if absolute_up:
                    input_options['up_at_ns']=prediction.release_ns+int(hold_ms*1e6)+model.input_overhead_ns
                receipt = adapter.release_shot(shot_id,**input_options)
                report.update(shot_id=shot_id, receipt=asdict(receipt), pending_result=True,
                              inputs_sent=receipt.down_ns is not None, prediction=asdict(prediction),
                              before_observation=asdict(observation))
                report['angular_motion'] = predictor.last_motion
                if receipt.error:raise RuntimeError(receipt.error)
                from .vision import cv2
                duration=2.5
                if getattr(model,'tick_mode',False):
                    steps=model.flight_steps(before_observation.launcher_position,report['aim_angle_rad'],aim_target[0])
                    duration=max(2.5,min(15.,steps/40+.75))
                    recording.interval_ns=max(50_000_000,int(duration/45*1e9))
                    report['expected_flight_steps']=steps;report['post_shot_window_s']=duration
                after = perf_counter_ns() + int(duration*1e9)
                reader=getattr(args,'result_reader',None);previous_result=None;result_stable=0;next_read=0
                report['result_settled']=False
                while perf_counter_ns() < after:
                    if cancelled() or adapter.stopped():break
                    frame = source.grab()
                    recording.add(frame,before_observation.launcher_position)
                    if reader is not None and frame.end_ns>=next_read:
                        from .vision import np
                        pixels=np.frombuffer(frame.bgr,dtype='uint8').reshape(frame.region.height,frame.region.width,3)
                        score,lives=reader.score(pixels),reader.lives(pixels)
                        changed=(score is not None and getattr(args,'before_score',None) is not None and
                            (score!=args.before_score or (lives is not None and args.before_lives is not None and lives<args.before_lives)))
                        key=(score,lives);result_stable=result_stable+1 if changed and key==previous_result else int(changed)
                        previous_result=key;next_read=frame.end_ns+50_000_000
                        if result_stable>=2:
                            report.update(result_settled=True,settled_score=score,settled_lives=lives)
                            break
                observation=detector.detect(frame,profile,session_id=motion_session,segment_index=1)
                report['observations'].append(asdict(observation))
                break
            if report['receipt'] is None:
                report['error'] = 'Aucune fenetre de tir dans la couverture avant expiration'
    except (CaptureError, RuntimeError, OSError, ValueError) as exc:
        report['error'] = str(exc)
    finally:
        adapter.release_all()
        controller.stop()
        report['state'] = 'stopped'
        if before_frame is not None and report['inputs_sent']:
            from .vision import cv2,np
            for name,captured,measured in [('before',before_frame,before_observation),('after',frame,observation)]:
                pixels=np.frombuffer(captured.bgr,dtype='uint8').reshape(captured.region.height,captured.region.width,3)
                cv2.imwrite(str(output/f'{name}-raw.png'),pixels)
                cv2.imwrite(str(output/f'{name}.png'),annotate_observation(captured,measured,calibration))
            report['flight_frames']=recording.save(output)
        (output / 'test.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if report['receipt'] is None:
            target = calibration.directory / 'resolved-shots'
            target.mkdir(exist_ok=True)
            pending.rename(target / f'{shot_id}-not-sent.json')
    print(json.dumps({key: value for key, value in report.items() if key != 'observations'}, indent=2))
    return 1 if report.get('error') else 0


def confirm(directory, result, source):
    import re
    calibration = load_visual_calibration(directory)
    pending = calibration.directory / 'pending-shot.json'
    data = json.loads(pending.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not re.fullmatch('[a-f0-9]{32}', data.get('shot_id', '')):
        raise ValueError('Reservation de tir invalide')
    data.update(result=result, result_source=source, confirmed_ns=perf_counter_ns())
    target = calibration.directory / 'resolved-shots'
    target.mkdir(exist_ok=True)
    destination = target / f'{data["shot_id"]}.json'
    # Keep evidence and remove the unresolved marker only after writing confirmation.
    with destination.open('x', encoding='utf-8') as stream:json.dump(data, stream, indent=2)
    pending.rename(target / f'{data["shot_id"]}-reservation.json')
    print(json.dumps(data, indent=2))
    return 0
