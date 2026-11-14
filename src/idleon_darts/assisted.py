"""Services for the assisted desktop app. No window/input access at import."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import math
import sys
import time

from .calibration import external_directory, load_visual_calibration
from .models import Rect
from .prediction import load_impact_model


def list_game_windows():
    if sys.platform != 'win32':return []
    import ctypes as c
    from ctypes import wintypes as w
    user=c.WinDLL('user32',use_last_error=True)
    kernel=c.WinDLL('kernel32',use_last_error=True)
    callback_type=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[callback_type,w.LPARAM];user.EnumWindows.restype=w.BOOL
    user.GetWindowTextLengthW.argtypes=[w.HWND];user.GetWindowTextLengthW.restype=c.c_int
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,c.c_int];user.GetWindowTextW.restype=c.c_int
    user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
    user.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    found=[]
    @callback_type
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd):return True
        length=user.GetWindowTextLengthW(hwnd)
        title=c.create_unicode_buffer(length+1);user.GetWindowTextW(hwnd,title,length+1)
        if 'idleon' not in title.value.casefold():return True
        pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,c.byref(pid))
        handle=kernel.OpenProcess(0x1000,False,pid.value)
        if not handle:return True
        try:
            size=w.DWORD(32768);path=c.create_unicode_buffer(size.value)
            if (kernel.QueryFullProcessImageNameW(handle,0,path,c.byref(size))
                    and Path(path.value).name.casefold()=='legendsofidleon.exe'):
                found.append(dict(id=int(hwnd),title=title.value,executable=path.value))
        finally:kernel.CloseHandle(handle)
        return True
    if not user.EnumWindows(visit,0):raise OSError('Impossible de rechercher la fenêtre Idleon.')
    return found


def focus_game(window_id):
    """Product action: maximize the selected game, without generating a click."""
    from .windows_io import WindowsDesktop
    if window_id not in [w['id'] for w in list_game_windows()]:
        raise ValueError('La fenêtre Idleon sélectionnée a été fermée. Actualisez la liste.')
    import ctypes as c
    from ctypes import wintypes as w
    user=c.WinDLL('user32',use_last_error=True)
    user.ShowWindow.argtypes=[w.HWND,c.c_int];user.ShowWindow.restype=w.BOOL
    user.SetForegroundWindow.argtypes=[w.HWND];user.SetForegroundWindow.restype=w.BOOL
    user.ShowWindow(window_id,3)
    user.SetForegroundWindow(window_id)
    time.sleep(.25)
    desktop=WindowsDesktop(window_id)
    if not desktop.snapshot().foreground:
        raise ValueError('Windows refuse le premier plan. Affichez Idleon puis réessayez.')
    return desktop


def selection_rect(start, end, image_size, viewport):
    """Map a drag on a letterboxed preview to image pixels, without silent clipping."""
    width,height=image_size;left,top,scale=viewport
    if scale<=0:raise ValueError('Aperçu indisponible.')
    points=[((x-left)/scale,(y-top)/scale) for x,y in (start,end)]
    if any(not(0<=x<=width and 0<=y<=height) for x,y in points):
        raise ValueError('Dessinez le rectangle à l’intérieur de l’image.')
    x0,y0=[math.floor(min(p[i] for p in points)) for i in (0,1)]
    x1,y1=[math.ceil(max(p[i] for p in points)) for i in (0,1)]
    if x1-x0<8 or y1-y0<8:raise ValueError('Le rectangle est trop petit.')
    return Rect(x0,y0,x1-x0,y1-y0)


def region_plan(rectangles, capture_region):
    required={'scene','arm','board','anchor','wind_none'}
    if set(rectangles)!=required:raise ValueError('Sélectionnez les cinq repères du guide.')
    scene=rectangles['scene']
    bounds=Rect(0,0,capture_region.width,capture_region.height)
    if not bounds.contains(scene) or any(not scene.contains(rectangles[k]) for k in required-{'scene'}):
        raise ValueError('Tous les repères doivent être à l’intérieur du mini-jeu.')
    absolute=Rect(scene.left+capture_region.left,scene.top+capture_region.top,scene.width,scene.height)
    relative={k:Rect(v.left-scene.left,v.top-scene.top,v.width,v.height)
              for k,v in rectangles.items() if k!='scene'}
    return absolute,relative


def assess(calibration, model, observation, pending=False):
    calculated={}
    if model is not None:
        if hasattr(model,'bind_observation') and observation.context_key is not None:model.bind_observation(observation)
        if model.profile_id!=calibration.profile.profile_id:raise ValueError('Ce modèle appartient à un autre profil visuel.')
        if observation.launcher_position and observation.target_center and observation.context_key in model.contexts:
            target=(observation.target_center[0]+model.target_x_offset,observation.target_center[1])
            angle=model.aim_angle(observation.launcher_position,target,observation.context_key)
            if angle is not None:calculated['aim_degrees']=math.degrees(angle)
    if pending:return dict(ready=False,title='Résultat à confirmer',detail='Confirmez le dernier tir avant un nouvel essai.')
    minimum=.6 if model is not None and model.version=='discrete-ballistics-v1' else .8
    if not observation.invalid_reasons and observation.confidence<minimum:
        return dict(ready=False,title='Repères à vérifier',detail='La lecture des repères manque de confiance. Vérifiez le cadrage et la calibration.')
    if observation.invalid_reasons:
        reason=set(observation.invalid_reasons)
        if 'wind-unknown' in reason:detail='Le vent est inconnu ou ambigu. Une référence visuelle est nécessaire.'
        elif 'target-unknown' in reason:detail='Le rouge est masqué ou non reconnu. Relancez la vérification.'
        elif 'launcher-anchor-unknown' in reason:detail='Le repère du personnage n’est pas reconnu. Vérifiez la calibration.'
        else:detail='La fléchette n’est pas encore lisible. Relancez la vérification sans toucher au jeu.'
        return dict(ready=False,title='Repères à vérifier',detail=detail,**calculated)
    if model is None:return dict(ready=False,title='Modèle de tir nécessaire',detail='La calibration visuelle est valide. Chargez ensuite un modèle de trajectoire lié à ce profil.')
    if model.profile_id!=calibration.profile.profile_id:raise ValueError('Ce modèle appartient à un autre profil visuel.')
    if observation.context_key not in model.contexts:
        return dict(ready=False,title='Vent non calibré',detail='Le vent est reconnu, mais sa trajectoire n’est pas calibrée. Aucun tir automatique ne sera envoyé.')
    tolerance=observation.target_half_height if model.version!='empirical-release-v1' else observation.target_radius
    if not calculated:return dict(ready=False,title='Position non calibrée',detail='Cette position demande un angle hors de la plage mesurée.')
    if tolerance is None:return dict(ready=False,title='Cible à vérifier',detail='La taille de la zone rouge n’est pas mesurée.',**calculated)
    if model.effective_uncertainty(observation.context_key)>tolerance:
        return dict(ready=True,supervised_only=True,title='Essai supervisé disponible',
                    detail='Visée calculée, précision non certifiée. L’essai peut manquer le rouge ou perdre une vie. Un seul tir, puis confirmation.',**calculated)
    return dict(ready=True,supervised_only=False,title='Prêt pour un essai supervisé',detail='Le jeu sera revérifié juste avant le clic. Un seul tir, puis confirmation obligatoire.',**calculated)


class AssistedService:
    def __init__(self,directory):
        self.directory=external_directory(directory)
        self.directory.mkdir(parents=True,exist_ok=True)

    def load_settings(self):
        file=self.directory/'settings.json'
        if not file.exists():return {}
        from .calibration import _visual_json
        d=_visual_json(file)
        if not isinstance(d,dict) or d.get('schema_version')!=1:raise ValueError('Préférences locales invalides.')
        return {k:v for k,v in d.items() if k in ('calibration','model','last_session') and isinstance(v,str)}

    def save_settings(self,calibration,model,last_session=None):
        data=dict(schema_version=1,calibration=calibration or '',model=model or '')
        if last_session:data['last_session']=str(last_session)
        temporary=self.directory/'settings.tmp'
        temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
        temporary.replace(self.directory/'settings.json')

    def destination(self,kind):
        return self.directory/'reports'/f'{kind}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid4().hex[:8]}'

    @staticmethod
    def check_cancel(cancel):
        if cancel.is_set():raise RuntimeError('Opération arrêtée. Aucun nouvel essai n’est armé.')

    def capture(self,window_id,cancel):
        from .capture import WindowsFrameSource
        from .vision import cv2,np
        self.check_cancel(cancel);desktop=focus_game(window_id);self.check_cancel(cancel)
        with WindowsFrameSource(desktop) as source:frame=source.grab()
        self.check_cancel(cancel)
        directory=self.destination('reference');directory.mkdir(parents=True)
        image=np.frombuffer(frame.bgr,dtype='uint8').reshape(frame.region.height,frame.region.width,3)
        preview=directory/'preview.png'
        if not cv2.imwrite(str(preview),image):raise OSError('Impossible d’enregistrer l’aperçu.')
        result=dict(kind='capture',preview=str(preview),region=asdict(frame.region),inputs_sent=False)
        (directory/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result

    def auto_calibrate(self,window_id,cancel):
        from .game_assets import auto_calibrate
        self.check_cancel(cancel)
        return auto_calibrate(window_id,self.directory/'profiles'/f'auto-{uuid4().hex[:12]}',cancel)

    def calibrate(self,window_id,rectangles,capture_region,wind_none,cancel,known_profile=None):
        from .calibration import calibrate_visual
        from .capture import WindowsFrameSource
        if not wind_none:raise ValueError('Le vent doit afficher None pour créer ce profil visuel.')
        scene,regions=region_plan(rectangles,capture_region)
        self.check_cancel(cancel);desktop=focus_game(window_id);context=desktop.snapshot()
        if context.rect!=capture_region:raise ValueError('Le cadrage a changé. Reprenez la capture du guide.')
        if known_profile:
            from .perception import CalibratedPerception
            known=load_visual_calibration(known_profile)
            if context.rect==known.profile.window_rect and context.dpi==known.profile.dpi:
                with WindowsFrameSource(desktop,known.profile.roi) as source:
                    observation=CalibratedPerception(known).detect(source.grab(),known.profile,session_id='wind-check',segment_index=1)
                if observation.context_key!='wind-none':
                    raise ValueError('Le profil existant ne confirme pas le vent None. Attendez une partie sans vent pour créer ce repère.')
        destination=self.directory/'profiles'/f'visual-{uuid4().hex[:12]}'
        def frames(source):
            for _ in range(160):
                self.check_cancel(cancel);yield source.grab()
        with WindowsFrameSource(desktop,scene) as source:
            calibration=calibrate_visual(frames(source),context,regions,destination)
        return dict(kind='calibration',calibration=str(destination),preview=str(destination/'reference.png'),
                    metrics=calibration.metrics,inputs_sent=False)

    def verify(self,window_id,calibration_path,model_path,cancel):
        from .capture import WindowsFrameSource
        from .perception import CalibratedPerception,annotate_observation
        from .vision import cv2
        calibration=load_visual_calibration(calibration_path)
        model=load_impact_model(model_path) if model_path else None
        if model and model.profile_id!=calibration.profile.profile_id:raise ValueError('Ce modèle appartient à un autre profil visuel.')
        self.check_cancel(cancel);desktop=focus_game(window_id);context=desktop.snapshot()
        if context.rect!=calibration.profile.window_rect or context.dpi!=calibration.profile.dpi:
            raise ValueError('Le cadrage ou le zoom Windows a changé. Reprenez la calibration visuelle.')
        detector=CalibratedPerception(calibration);observations=[];started=time.perf_counter()
        with WindowsFrameSource(desktop,calibration.profile.roi) as source:
            for _ in range(45):
                self.check_cancel(cancel);frame=source.grab()
                observations.append(detector.detect(frame,calibration.profile,session_id='assisted-check',segment_index=1))
        elapsed=time.perf_counter()-started;last=observations[-1]
        assessment=assess(calibration,model,last,(calibration.directory/'pending-shot.json').exists())
        directory=self.destination('verification');directory.mkdir(parents=True)
        preview=directory/'preview.png'
        if not cv2.imwrite(str(preview),annotate_observation(frame,last,calibration)):
            raise OSError('Impossible d’enregistrer l’aperçu.')
        result=dict(kind='verification',preview=str(preview),assessment=assessment,observation=asdict(last),
                    frames=len(observations),effective_fps=len(observations)/max(elapsed,1e-9),
                    complete_observations=sum(not o.invalid_reasons for o in observations),inputs_sent=False)
        (directory/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        return result

    def shoot(self,window_id,calibration_path,model_path,cancel):
        from .auto_test import run
        from contextlib import redirect_stdout
        import io
        calibration=load_visual_calibration(calibration_path);model=load_impact_model(model_path)
        if model.profile_id!=calibration.profile.profile_id:raise ValueError('Ce modèle appartient à un autre profil visuel.')
        if (calibration.directory/'pending-shot.json').exists():raise ValueError('Confirmez le résultat du dernier tir.')
        self.check_cancel(cancel);focus_game(window_id);self.check_cancel(cancel)
        directory=self.destination('tir')
        # Use an empty part of the selected scene, never a fixed monitor coordinate.
        roi=calibration.profile.roi;point=(roi.left+roi.width//2,roi.top+roi.height//2)
        args=SimpleNamespace(arm=True,calibration=str(calibration.directory),model=str(model_path),
            output=str(directory),window_id=window_id,max_wait=15.,hold_ms=1.,
            click_x=point[0],click_y=point[1],cancel_event=cancel,supervised_calibration=True)
        with redirect_stdout(io.StringIO()):run(args)
        d=json.loads((directory/'test.json').read_text(encoding='utf-8'))
        return dict(kind='shot',inputs_sent=d['inputs_sent'],pending=d.get('pending_result',False),
                    error=d.get('error'),preview=str(directory/'after.png') if (directory/'after.png').exists() else None,
                    output=str(directory))

    def confirm(self,calibration_path,result):
        from .auto_test import confirm
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):confirm(calibration_path,result,'Résultat observé et confirmé dans l’application assistée.')
        return dict(kind='confirmation',result=result,inputs_sent=False)

    def continuous(self,window_id,calibration_path,model_path,cancel,on_progress,max_shots=20,record_flight=True):
        from .continuous import run
        if type(max_shots) is not int or not 0<=max_shots<=10000:raise ValueError('Choisissez entre 1 et 10 000 tirs, ou 0 pour une boucle continue.')
        self.check_cancel(cancel);focus_game(window_id)
        args=SimpleNamespace(arm=True,window_id=window_id,calibration=calibration_path,model=model_path,
            output=str(self.destination('serie')),cancel_event=cancel,max_shots=max_shots,on_progress=on_progress,record_flight=record_flight)
        result=run(args)
        learned=Path(result['output'])/'learned-model.json'
        if learned.exists():
            models=self.directory/'models';models.mkdir(exist_ok=True)
            active=models/'application-current.json';temporary=models/'application-current.tmp'
            temporary.write_bytes(learned.read_bytes());temporary.replace(active)
            return dict(kind='continuous',model=str(active),**result)
        return dict(kind='continuous',**result)

    def export_session(self,session):
        from .session_export import export_session
        destination=self.directory/'exports'/f'analyse-{time.strftime("%Y%m%d-%H%M%S")}-{uuid4().hex[:8]}.zip'
        return export_session(session,destination)
