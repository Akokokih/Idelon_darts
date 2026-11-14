"""Explicitly armed continuous experimental play; outcomes are read from pixels."""
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict,replace
import io,json,time,math


class StopSignal:
    def __init__(self,event,file):self.event=event;self.file=Path(file)
    def is_set(self):return self.event.is_set() or self.file.exists()
    def wait(self,seconds):
        deadline=time.monotonic()+seconds
        while not self.is_set() and time.monotonic()<deadline:
            self.event.wait(min(.05,max(0.,deadline-time.monotonic())))
        return self.is_set()


def classify_scores(before,after):
    if before is None or after is None or after<before:return 'unknown'
    difference=after-before
    if difference==0:return 'miss'
    if difference in (1,2,3):return 'other'
    if difference in (5,10,30):return 'centre'
    return 'unknown'


def impact_tip(before,after,observation,plane_offset):
    import cv2,numpy as np
    cx,cy=observation['target_center'];plane=cx+plane_offset
    left=max(0,int(plane-110));right=min(after.shape[1],int(plane+8))
    top=max(0,int(cy-240));bottom=min(after.shape[0],int(cy+240))
    a=after[top:bottom,left:right];b=before[top:bottom,left:right]
    mask=(np.ptp(a,axis=2)<35)&(a.min(axis=2)>150)&(cv2.absdiff(a,b).max(axis=2)>25)
    y,x=np.where(mask)
    if len(x)<20 or x.max()+left<plane-6:return None
    selected=x>=x.max()-3
    if np.ptp(y[selected])>12:return None
    return float(np.median(y[selected])+top)


def run(args):
    from .calibration import load_visual_calibration,external_directory
    from .prediction import load_impact_model
    from .capture import WindowsFrameSource
    from .windows_io import WindowsDesktop
    from .native_input import _Win32Mouse
    from .hud import HudReader
    from .auto_test import run as one_shot,confirm
    from threading import Event
    import cv2,numpy as np
    if not args.arm:return dict(state='paused',reason='explicit_arm_required',shots=0)
    cancel=getattr(args,'cancel_event',None) or Event()
    publish=getattr(args,'on_progress',None) or (lambda value:None)
    output=external_directory(args.output);resume=bool(getattr(args,'resume',False))
    model_path=output/'learned-model.json' if resume else Path(args.model)
    calibration=load_visual_calibration(args.calibration);model=load_impact_model(model_path)
    if model.profile_id!=calibration.profile.profile_id:raise ValueError('Modèle lié à un autre profil.')
    if (calibration.directory/'pending-shot.json').exists():raise ValueError('Un résultat antérieur reste à confirmer.')
    reader=HudReader(calibration.directory);desktop=WindowsDesktop(args.window_id);transport=_Win32Mouse()
    from .perception import CalibratedPerception
    runtime_profile=replace(calibration.profile,model_version=model.version,calibration_coverage=tuple(model.contexts))
    detector=CalibratedPerception(replace(calibration,profile=runtime_profile))
    if resume:
        state=json.loads((output/'state.json').read_text(encoding='utf-8'))
        if state['state'] not in ('stopped','paused'):raise ValueError('La série doit être arrêtée avant reprise.')
        original=json.loads((output/'configuration'/'profile.json').read_text(encoding='utf-8'))
        if original['profile_id']!=model.profile_id:raise ValueError('Le profil de reprise diffère de la série.')
        state['state']='running'
    else:output.mkdir(parents=True,exist_ok=False)
    cancel=StopSignal(cancel,output/'stop-requested')
    from datetime import datetime,timezone
    from . import __version__
    configuration=output/'configuration'
    if not resume:configuration.mkdir()
    for name,source in [('profile',calibration.directory/'profile.json'),('visual',calibration.directory/'visual.json'),('model',Path(args.model))]:
        if not resume:(configuration/f'{name}.json').write_bytes(source.read_bytes())
    session=dict(schema_version=1,app_version=__version__,
        started_utc=datetime.now(timezone.utc).isoformat(),max_shots=args.max_shots,
        record_flight=getattr(args,'record_flight',True),adapt_timing=getattr(args,'adapt_timing',False),
        experimental=True,target_rate=.9)
    if resume:
        session=json.loads((output/'session.json').read_text(encoding='utf-8'))
        session.setdefault('continuations',[]).append(dict(utc=datetime.now(timezone.utc).isoformat(),
            after_shots=state['shots'],timing_policy=getattr(model,'forecast_policy','existing'),model_changed=False))
    (output/'session.json').write_text(json.dumps(session,indent=2),encoding='utf-8')
    if not resume:state=dict(state='running',shots=0,bullseyes=0,other=0,misses=0,unknown=0,lives_lost=0,
               rate=None,score=None,visible_lives=None,results=[],experimental=True,target_rate=.9,output=str(output))
    stopped=lambda:cancel.is_set() or transport.is_down(0x77)
    def save():
        state['rate']=state['bullseyes']/state['shots'] if state['shots'] else None
        temporary=output/'state.tmp';temporary.write_text(json.dumps(state,indent=2),encoding='utf-8');temporary.replace(output/'state.json')
        if hasattr(model,'wind'):
            learned=json.loads(model_path.read_text(encoding='utf-8'))
            learned['trigger_delay_ns']=model.trigger_delay_ns
            learned['amplitude_deg']=math.degrees(model.amplitude)
            learned['last_score']=state['score']
            (output/'learned-model.json').write_text(json.dumps(learned,indent=2),encoding='utf-8')
    last_message=None
    def emit(message):
        nonlocal last_message
        if message==last_message:return
        last_message=message
        publish(dict(kind='continuous-progress',message=message,**{k:v for k,v in state.items() if k!='results'}))
    capture=None
    def image_snapshot():
        nonlocal capture
        if capture is None:capture=WindowsFrameSource(desktop,calibration.profile.roi)
        frame=capture.grab()
        image=np.frombuffer(frame.bgr,dtype='uint8').reshape(frame.region.height,frame.region.width,3)
        return frame,image,reader.score(image),reader.lives(image)
    def hud_snapshot():
        _,_,score,lives=image_snapshot();return score,lives
    save();emit('Lecture du jeu…')
    attempts=max((int(p.name.split('-')[1]) for p in output.glob('attempt-*') if p.is_dir() and p.name.split('-')[1].isdigit()),default=0)
    try:
        while not stopped() and (not args.max_shots or state['shots']<args.max_shots):
            if not desktop.snapshot().foreground:
                emit('En pause : remettez Idleon au premier plan.');cancel.wait(.5);continue
            try:score,lives=hud_snapshot()
            except (RuntimeError,ValueError,OSError) as exc:
                emit(str(exc));cancel.wait(.5);continue
            state['score']=score;state['visible_lives']=lives
            if score is None or (score>0 and lives==0):
                emit('En attente du mini-jeu ou d’une nouvelle partie.');cancel.wait(.5);continue
            if score==0 and lives==0 and hasattr(model,'amplitude'):
                model.amplitude=math.radians(38.)
            attempts+=1;destination=output/f'attempt-{attempts:04d}'
            roi=calibration.profile.roi
            shot_args=SimpleNamespace(arm=True,calibration=str(calibration.directory),model=str(args.model),
                output=str(destination),window_id=args.window_id,max_wait=15.,hold_ms=1.,
                click_x=roi.left+roi.width//2,click_y=roi.top+roi.height//2,
                cancel_event=cancel,supervised_calibration=True,model_instance=model)
            shot_args.record_flight=getattr(args,'record_flight',True)
            shot_args.frame_source=capture;shot_args.motion_session_id=output.name
            shot_args.detector_instance=detector
            shot_args.result_reader=reader;shot_args.before_score=score;shot_args.before_lives=lives
            with redirect_stdout(io.StringIO()):one_shot(shot_args)
            report=json.loads((destination/'test.json').read_text(encoding='utf-8'))
            if 'F8' in (report.get('error') or ''):cancel.event.set()
            if not report['inputs_sent']:
                error=report.get('error','Pas de créneau de tir.')
                emit(error)
                if 'F8' in error:break
                cancel.wait(.01 if error=='Aucune fenetre de tir dans la couverture avant expiration' else .25);continue
            before=cv2.imread(str(destination/'before-raw.png'));after=cv2.imread(str(destination/'after-raw.png'))
            before_score=reader.score(before) if before is not None else score
            after_score=reader.score(after) if after is not None else None
            after_lives=reader.lives(after) if after is not None else None
            # Slow game rendering can keep a dart in flight well beyond 2.5 s.
            # A stable, unchanged score alone does not prove a miss.
            settled=lambda: after_score is not None and before_score is not None and (
                after_score!=before_score or (after_lives is not None and after_lives<lives))
            deadline=time.monotonic()+30.;stable=2 if report.get('result_settled') else 0;previous=None;result_frame=None
            while not stopped() and time.monotonic()<deadline and (not settled() or stable<2):
                emit('Lecture du résultat avant le tir suivant…');cancel.wait(.1)
                try:
                    result_frame,after,after_score,after_lives=image_snapshot()
                    reading=(after_score,after_lives)
                    stable=stable+1 if reading==previous else 1;previous=reading
                except (RuntimeError,ValueError,OSError):continue
            result=classify_scores(before_score,after_score) if settled() and stable>=2 else 'unknown'
            if result_frame is not None:
                cv2.imwrite(str(destination/'after-raw.png'),after)
                report['result_snapshot']=dict(frame_id=result_frame.frame_id,start_ns=result_frame.start_ns,
                    end_ns=result_frame.end_ns,sample_ns=result_frame.sample_ns)
            report['read_result']=result;report['after_score']=after_score;report['after_lives']=after_lives
            (destination/'test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            state['shots']+=1;field={'centre':'bullseyes','other':'other','miss':'misses','unknown':'unknown'}[result]
            state[field]+=1
            lost=int(result=='miss' and before_score is not None and before_score>0)
            state['lives_lost']+=lost;state['score']=after_score;state['visible_lives']=after_lives
            tip=impact_tip(before,after,report['before_observation'],model.target_x_offset) if before is not None and after is not None else None
            row=dict(number=state['shots'],result=result,before_score=before_score,after_score=after_score,
                     lives_lost=lost,tip_y=tip,context=report['before_observation']['context_key'],
                     wind=report['before_observation']['wind_features'],output=str(destination))
            row['flight_frames']=report.get('flight_frames',0)
            state['results'].append(row)
            if result in ('centre','other') and hasattr(model,'amplitude'):
                # The swing amplitude grows with successful hits in this minigame.
                amplitude=math.degrees(model.amplitude)
                estimate=max(0.,30*(amplitude-38)/max(.1,53-amplitude))+1
                model.amplitude=math.radians(38+15*estimate/(estimate+30))
            if result!='unknown':
                with redirect_stdout(io.StringIO()):confirm(calibration.directory,result,f'Lecture automatique du score : {before_score} -> {after_score}.')
            if getattr(args,'adapt_timing',False) and tip is not None and hasattr(model,'wind') and result in ('centre','other'):
                obs=report['before_observation'];error=tip-obs['target_center'][1]
                omega=(report.get('angular_motion') or {}).get('omega_rad_s')
                angle=obs['arm_angle']
                if omega and omega<-.1 and abs(error)<120:
                    upper=model.impact(obs['launcher_position'],angle+.01,obs['target_center'][0]+model.target_x_offset,obs['context_key'])
                    lower=model.impact(obs['launcher_position'],angle-.01,obs['target_center'][0]+model.target_x_offset,obs['context_key'])
                    if upper is not None and lower is not None:
                        sensitivity=(upper-lower)/.02*omega
                        if sensitivity>100:
                            step=max(-3e6,min(3e6,.2*error/sensitivity*1e9))
                            model.trigger_delay_ns=int(max(0,min(80e6,model.trigger_delay_ns+step)))
                            row['adapted_delay_ns']=model.trigger_delay_ns
            save();emit(f'{state["bullseyes"]}/{state["shots"]} rouges — score {after_score}')
            if result=='unknown':
                state['state']='paused';emit('Résultat ambigu : reprise manuelle nécessaire.');break
        if state['state']=='running':state['state']='stopped' if stopped() else 'complete'
    finally:
        try:save();emit('Boucle arrêtée.');state['output']=str(output)
        finally:
            if capture is not None:capture.close()
    return state
