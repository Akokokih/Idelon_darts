"""Native assisted UI. Tk stays on the main thread; game work is serialized."""
from pathlib import Path
from queue import Queue, Empty
from threading import Event, Thread
import base64
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import __version__
from .assisted import AssistedService, list_game_windows, selection_rect
from .calibration import load_visual_calibration, external_directory
from .prediction import load_impact_model
from .models import Rect

BG='#0c1422'; PANEL='#152236'; TEXT='#edf3fa'; MUTED='#a7bbcf'; ACCENT='#35d5bc'
REGIONS=[('scene','Le mini-jeu','Encadrez tout le mini-jeu, avec le personnage et la cible.'),
         ('arm','La fléchette','Encadrez toute la zone balayée par la lame blanche, avec une marge. Évitez le visage.'),
         ('board','La cible','Encadrez la colonne complète de la cible à droite, avec le rouge.'),
         ('anchor','La plateforme','Sélectionnez une petite bande immobile de la plateforme, sans les pieds.'),
         ('wind_none','Le vent « None »','Encadrez uniquement le mot None. Ce repère nécessite une partie sans vent.')]


class AssistedApp:
    def __init__(self,root,service,calibration=None,model=None):
        self.root=root;self.service=service;self.queue=Queue();self.cancel=Event()
        self.busy=False;self.closing=False;self.worker=None;self.windows=[]
        self.calibration_path='';self.model_path='';self.assessment=None
        self.session_path=''
        self.image=None;self.photo=None;self.viewport=(0,0,0);self.drag_start=None
        self.rectangles={};self.wizard=None;self.capture_region=None
        self.controls=[];self.result_controls=[]
        self.status=tk.StringVar(value='Bienvenue — connectez le jeu pour commencer.')
        self.detail=tk.StringVar(value='Choisissez le nombre de tirs puis lancez la série. Les résultats sont collectés automatiquement.')
        self.profile_label=tk.StringVar(value='Aucun profil visuel chargé')
        self.model_label=tk.StringVar(value='Aucun modèle de trajectoire chargé')
        self.telemetry=tk.StringVar(value='Vent —    Position —    Visée —')
        self.guide=tk.StringVar(value='Chargez un profil existant, ou capturez le mini-jeu pour créer ses repères.')
        self.arm=tk.BooleanVar(value=False);self.none=tk.BooleanVar(value=False)
        self.loop_arm=tk.BooleanVar(value=False)
        self.series_count=tk.StringVar(value='20');self.record_flight=tk.BooleanVar(value=True)
        self._build();self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind('<F8>',lambda _:self.stop())
        self.root.bind('<FocusIn>',lambda _:self._refresh_buttons() if not self.busy else None)
        try:
            settings=service.load_settings()
            self.session_path=settings.get('last_session','')
            chosen=calibration or settings.get('calibration')
            if chosen:self.load_profile(chosen,persist=False)
            chosen_model=model or settings.get('model')
            if chosen_model:self.load_model(chosen_model,persist=False)
            self.persist()
        except (ValueError,OSError,ImportError) as exc:self.show_error(str(exc))
        self.refresh_windows();self._refresh_buttons();self._drain_job=self.root.after(100,self._drain)
        self._watch_job=self.root.after(2000,self._watch_windows)
        self.root.bind('<Destroy>',self._cancel_jobs,add='+')
        if self.calibration_path and self.model_path:
            self.tabs.select(1);self.status.set('Prêt à lancer une série')
            self.detail.set('Choisissez le nombre de tirs puis cliquez sur « Lancer ».')

    def _build(self):
        self._build_advanced()
        self.advanced_stop=self.stop_button
        self.loop_button.master.pack_forget()
        root=self.root;root.title('Idleon Darts');root.geometry('680x430');root.minsize(640,410)
        root.configure(bg=BG)
        header=ttk.Frame(root,padding=(24,20,24,6));header.pack(fill='x')
        ttk.Label(header,text='Idleon Darts',font=('Segoe UI',22,'bold')).pack(side='left')
        ttk.Label(header,text=f'v{__version__}',style='Muted.TLabel').pack(side='right')
        ttk.Label(root,text='Ouvrez Throwy Darts dans Idleon, puis lancez une série.',style='Muted.TLabel').pack(anchor='w',padx=24,pady=(0,12))
        card=ttk.Frame(root,padding=18,style='Card.TFrame');card.pack(fill='x',padx=24)
        ttk.Label(card,text='Nombre de tirs',background=PANEL).pack(side='left')
        count=ttk.Spinbox(card,from_=0,to=10000,width=7,textvariable=self.series_count)
        count.pack(side='left',padx=14);self.controls.append(count)
        ttk.Label(card,text='0 = continuer jusqu’à l’arrêt',background=PANEL,foreground=MUTED).pack(side='left')
        actions=ttk.Frame(root);actions.pack(fill='x',padx=24,pady=16)
        self.loop_button=self.button(actions,'Lancer',self.continuous,accent=True)
        self.loop_button.pack(side='left',fill='x',expand=True)
        self.stop_button=ttk.Button(actions,text='Arrêter',command=self.stop)
        self.stop_button.pack(side='left',fill='x',expand=True,padx=10)
        self.export_button=self.button(actions,'Exporter',self.export_session)
        self.export_button.pack(side='left',fill='x',expand=True)
        banner=ttk.Frame(root,padding=(24,0));banner.pack(fill='both',expand=True)
        ttk.Label(banner,textvariable=self.status,font=('Segoe UI',12,'bold'),foreground=ACCENT).pack(anchor='w')
        ttk.Label(banner,textvariable=self.detail,wraplength=610,style='Muted.TLabel').pack(anchor='w',pady=(8,0))
        ttk.Label(banner,text='F8 pour arrêter • Données enregistrées automatiquement',style='Muted.TLabel').pack(anchor='w',pady=(12,0))
        footer=ttk.Frame(root,padding=(24,12));footer.pack(fill='x',side='bottom')
        ttk.Label(footer,text='Référence : 65 % de rouges sur 20 tirs',style='Muted.TLabel').pack(side='left')
        ttk.Button(footer,text='Options avancées',command=self.open_advanced).pack(side='right')
        footer.pack_configure(before=banner)

    def open_advanced(self):
        self.advanced_window.deiconify();self.advanced_window.lift()

    def _build_advanced(self):
        root=self.advanced_window=tk.Toplevel(self.root);root.withdraw()
        root.title('Idleon Darts — Options avancées');root.geometry('1100x850');root.minsize(1000,800)
        root.protocol('WM_DELETE_WINDOW',root.withdraw)
        root.bind('<F8>',lambda _:self.stop())
        root.configure(bg=BG)
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background=BG,foreground=TEXT)
        style.configure('TFrame',background=BG);style.configure('Card.TFrame',background=PANEL)
        style.configure('TLabel',background=BG,foreground=TEXT)
        style.configure('Muted.TLabel',foreground=MUTED)
        style.configure('TButton',padding=(12,8),background='#263d57',foreground=TEXT,borderwidth=0)
        style.map('TButton',background=[('active','#355471'),('disabled','#1b2b40')],foreground=[('disabled','#6d8297')])
        style.configure('Accent.TButton',background=ACCENT,foreground='#08251f',font=('Segoe UI',10,'bold'))
        style.map('Accent.TButton',background=[('active','#65e5d1'),('disabled','#1b2b40')],foreground=[('disabled','#6d8297')])
        style.configure('TCheckbutton',background=BG,foreground=TEXT)
        style.configure('TSpinbox',fieldbackground=PANEL,foreground=TEXT,arrowcolor=ACCENT)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
        style.map('TCheckbutton',background=[('active',BG)],foreground=[('disabled','#6d8297')])
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',padding=(20,10),background=PANEL,foreground=MUTED)
        style.map('TNotebook.Tab',background=[('selected','#263d57')],foreground=[('selected',TEXT)])
        header=ttk.Frame(root,padding=(24,16));header.pack(fill='x')
        ttk.Label(header,text='IDLEON  /  DARTS',font=('Segoe UI',21,'bold')).pack(side='left')
        ttk.Label(header,text=f'MODE ASSISTÉ  •  v{__version__}',foreground=ACCENT).pack(side='right')
        top=ttk.Frame(root,padding=(24,0,24,10));top.pack(fill='x')
        ttk.Label(top,text='1  Connecter le jeu',font=('Segoe UI',11,'bold')).pack(side='left',padx=(0,18))
        self.window_choice=ttk.Combobox(top,state='readonly',width=39);self.window_choice.pack(side='left',fill='x',expand=True)
        self.controls.append(self.window_choice)
        self.window_choice.bind('<<ComboboxSelected>>',self.window_changed)
        self.button(top,'Actualiser',self.refresh_windows).pack(side='left',padx=8)
        self.capture_button=self.button(top,'Capturer le mini-jeu',self.capture,accent=True);self.capture_button.pack(side='left')
        self.tabs=ttk.Notebook(root);self.tabs.pack(fill='x',padx=24,pady=(0,10))
        guide_tab=ttk.Frame(self.tabs,padding=12);shot_tab=ttk.Frame(self.tabs,padding=12)
        self.tabs.add(guide_tab,text='2  Calibration guidée');self.tabs.add(shot_tab,text='3  Séries et tirs')
        row=ttk.Frame(guide_tab);row.pack(fill='x')
        self.profile_button=self.button(row,'Charger un profil',self.choose_profile);self.profile_button.pack(side='left')
        self.auto_button=self.button(row,'Calibration automatique',self.auto_calibrate,accent=True);self.auto_button.pack(side='left',padx=8)
        ttk.Label(row,textvariable=self.profile_label,style='Muted.TLabel').pack(side='left',padx=14)
        self.verify_button=self.button(row,'Vérifier dans Idleon',self.verify,accent=True);self.verify_button.pack(side='right')
        ttk.Label(guide_tab,textvariable=self.guide,wraplength=1050).pack(anchor='w',pady=(12,8))
        row=ttk.Frame(guide_tab);row.pack(fill='x')
        self.back=self.button(row,'Retour',self.previous_region);self.back.pack(side='left')
        self.next=self.button(row,'Valider ce repère',self.next_region);self.next.pack(side='left',padx=8)
        self.none_check=ttk.Checkbutton(row,text='Le vent affiche bien « None »',variable=self.none,command=self._refresh_buttons)
        self.none_check.pack(side='left',padx=12);self.controls.append(self.none_check)
        self.save=self.button(row,'Créer le profil',self.calibrate,accent=True);self.save.pack(side='right')
        row=ttk.Frame(shot_tab);row.pack(fill='x')
        self.model_button=self.button(row,'Charger un modèle de tir',self.choose_model);self.model_button.pack(side='left')
        ttk.Label(row,textvariable=self.model_label,style='Muted.TLabel',wraplength=440,width=43).pack(side='left',padx=14)
        self.button(row,'Vérifier les repères',self.verify).pack(side='right')
        ttk.Label(shot_tab,text='Le modèle physique recalcule la visée selon la position et le vecteur du vent. Le taux de rouges est mesuré pendant la boucle.',
                  wraplength=1040,style='Muted.TLabel').pack(anchor='w',pady=10)
        row=ttk.Frame(shot_tab);row.pack(fill='x')
        self.arm_check=ttk.Checkbutton(row,text='J’autorise un essai incertain : un seul tir',variable=self.arm,command=self._refresh_buttons)
        self.arm_check.pack(side='left');self.controls.append(self.arm_check)
        self.shot=self.button(row,'Lancer un tir supervisé',self.shoot,accent=True);self.shot.pack(side='right')
        row=ttk.Frame(shot_tab);row.pack(fill='x',pady=(10,0))
        ttk.Label(row,text='Un clic démarre les tirs automatiques • Dernier test : 65 % de rouges',style='Muted.TLabel').pack(side='left')
        self.loop_button=self.button(row,'Lancer la série',self.continuous,accent=True);self.loop_button.pack(side='right')
        row=ttk.Frame(shot_tab);row.pack(fill='x',pady=(8,0))
        ttk.Label(row,text='Tirs :').pack(side='left')
        count=ttk.Spinbox(row,from_=0,to=10000,width=6,textvariable=self.series_count)
        count.pack(side='left',padx=6);self.controls.append(count)
        ttk.Label(row,text='0 = continu',style='Muted.TLabel').pack(side='left',padx=(0,15))
        record=ttk.Checkbutton(row,text='Enregistrer les trajectoires',variable=self.record_flight)
        record.pack(side='left');self.controls.append(record)
        self.export_button=self.button(row,'Exporter pour Codex',self.export_session);self.export_button.pack(side='right')
        self.results=ttk.Frame(shot_tab);self.results.pack(fill='x',pady=(10,0))
        ttk.Label(self.results,text='Résultat du dernier tir :').pack(side='left',padx=(0,10))
        for label,value in [('Rouge','centre'),('Autre zone','other'),('Raté','miss'),('Incertain','unknown')]:
            b=ttk.Button(self.results,text=label,command=lambda result=value:self.confirm(result))
            b.pack(side='left',padx=4);self.result_controls.append(b)
        banner=ttk.Frame(root,padding=(24,4,24,8));banner.pack(fill='x')
        ttk.Label(banner,textvariable=self.status,font=('Segoe UI',13,'bold'),foreground=ACCENT).pack(anchor='w')
        ttk.Label(banner,textvariable=self.detail,wraplength=1080,style='Muted.TLabel').pack(anchor='w',pady=(4,0))
        ttk.Label(banner,textvariable=self.telemetry,font=('Segoe UI',10)).pack(anchor='w',pady=(8,0))
        self.canvas=tk.Canvas(root,bg='#070d17',highlightthickness=1,highlightbackground='#2b3d52',height=330)
        self.canvas.pack(fill='both',expand=True,padx=24)
        self.canvas.create_text(500,150,text='L’aperçu du jeu apparaîtra ici',fill=MUTED,font=('Segoe UI',14))
        self.canvas.bind('<Configure>',lambda _:self.render())
        self.canvas.bind('<ButtonPress-1>',self.begin_drag);self.canvas.bind('<B1-Motion>',self.move_drag)
        self.canvas.bind('<ButtonRelease-1>',self.end_drag)
        footer=ttk.Frame(root,padding=(24,10));footer.pack(fill='x')
        self.stop_button=ttk.Button(footer,text='Arrêter l’opération',command=self.stop);self.stop_button.pack(side='right')
        ttk.Label(footer,text='F8 : arrêter la série  •  Résultats enregistrés automatiquement',style='Muted.TLabel').pack(side='left')
        self.log=tk.Text(root,height=3,bg=PANEL,fg=MUTED,font=('Segoe UI',9),relief='flat',wrap='word',state='disabled')
        self.log.pack(fill='x',padx=24,pady=(0,14))
        footer.pack_configure(side='bottom',before=self.canvas)
        self.log.pack_configure(side='bottom',before=self.canvas)

    def button(self,parent,text,command,accent=False):
        b=ttk.Button(parent,text=text,command=command,style='Accent.TButton' if accent else 'TButton')
        self.controls.append(b);return b

    def event(self,text):
        self.log.configure(state='normal');self.log.insert('end',f'{time.strftime("%H:%M:%S")}  {text}\n')
        self.log.see('end');self.log.configure(state='disabled')
        try:
            with (self.service.directory/'app-events.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(time=time.time(),message=text),ensure_ascii=False)+'\n')
        except OSError:self.detail.set('Le journal local ne peut pas être enregistré. Vérifiez le dossier de données.')

    def window_changed(self,_=None):
        self.assessment=None;self.arm.set(False);self.status.set('Fenêtre sélectionnée — vérification nécessaire')
        self._refresh_buttons()

    def show_error(self,message):
        self.status.set('Action interrompue');self.detail.set(message);self.assessment=None;self.arm.set(False)
        self.event(message)

    def persist(self):self.service.save_settings(self.calibration_path,self.model_path,self.session_path)

    def _cancel_jobs(self,event):
        if event.widget is not self.root:return
        for name in ('_drain_job','_watch_job'):
            job=getattr(self,name,None)
            if job:
                try:self.root.after_cancel(job)
                except tk.TclError:pass

    def _watch_windows(self):
        if not self.busy:
            try:
                fresh=list_game_windows()
                if [(w['id'],w['title']) for w in fresh]!=[(w['id'],w['title']) for w in self.windows]:
                    self.refresh_windows()
            except (OSError,RuntimeError):pass
        self._watch_job=self.root.after(2000,self._watch_windows)

    def refresh_windows(self):
        if self.busy:return
        try:
            previous=self.selected_window(optional=True)
            self.windows=list_game_windows();self.window_choice['values']=[w['title'] for w in self.windows]
            if self.windows:
                index=next((i for i,w in enumerate(self.windows) if w['id']==previous),0)
                self.window_choice.current(index)
                if previous is None:
                    self.status.set('Idleon détecté')
                    self.detail.set('Affichez Throwy Darts, puis cliquez sur Lancer ou Préparer et lancer.')
            else:
                self.window_choice.set('');self.status.set('Idleon introuvable')
                self.detail.set('Ouvrez Idleon sur Steam et affichez Throwy Darts. La détection est automatique.')
            self.assessment=None;self.arm.set(False);self._refresh_buttons()
        except Exception as exc:self.show_error(str(exc))

    def selected_window(self,optional=False):
        i=self.window_choice.current()
        if 0<=i<len(self.windows):return self.windows[i]['id']
        if optional:return None
        raise ValueError('Sélectionnez la fenêtre Idleon.')

    def load_profile(self,path,persist=True):
        calibration=load_visual_calibration(external_directory(path))
        self.calibration_path=str(calibration.directory);self.profile_label.set(f'Profil : {calibration.directory.name}')
        if self.model_path and load_impact_model(self.model_path).profile_id!=calibration.profile.profile_id:
            self.model_path='';self.model_label.set('Choisissez un modèle lié au nouveau profil')
        self.assessment=None;self.arm.set(False)
        self.guide.set('Profil chargé. Cliquez sur « Vérifier dans Idleon » pour contrôler les repères et le vent actuels.')
        if persist:self.persist()
        self._refresh_buttons()

    def load_model(self,path,persist=True):
        if not self.calibration_path:raise ValueError('Chargez d’abord un profil visuel.')
        calibration=load_visual_calibration(self.calibration_path);model=load_impact_model(path)
        if model.profile_id!=calibration.profile.profile_id:raise ValueError('Ce modèle est lié à un autre profil visuel.')
        self.model_path=str(Path(path).resolve())
        label='physique expérimental' if model.version=='discrete-ballistics-v1' else f'{len(model.contexts)} vents couverts'
        self.model_label.set('Modèle à relâchement programmé chargé' if getattr(model,'absolute_mouse_up',False)
                             else f'Modèle chargé : {Path(path).name}  •  {label}')
        self.assessment=None;self.arm.set(False)
        if persist:self.persist()
        self._refresh_buttons()

    def choose_profile(self):
        path=filedialog.askdirectory(title='Choisir le dossier du profil visuel',initialdir=self.service.directory)
        if path:
            try:self.load_profile(path);self.status.set('Profil chargé — vérification nécessaire')
            except Exception as exc:self.show_error(str(exc))

    def choose_model(self):
        directory=Path(self.model_path).parent if self.model_path else (Path(self.calibration_path).parent if self.calibration_path else self.service.directory)
        path=filedialog.askopenfilename(title='Choisir le modèle de trajectoire',initialdir=directory,filetypes=[('Modèle JSON','*.json')])
        if path:
            try:self.load_model(path);self.status.set('Modèle chargé — vérification nécessaire')
            except Exception as exc:self.show_error(str(exc))

    def _refresh_buttons(self):
        if not hasattr(self,'shot'):return
        for control in self.controls:
            control.state(['disabled'] if self.busy else ['!disabled'])
        if not self.busy:self.window_choice.configure(state='readonly')
        has_window=self.selected_window(optional=True) is not None
        pending=bool(self.calibration_path and (Path(self.calibration_path)/'pending-shot.json').exists())
        if self.busy or not self.calibration_path or not has_window:self.verify_button.state(['disabled'])
        ready=bool(self.assessment and self.assessment['ready'] and not pending)
        self.arm_check.state(['!disabled'] if ready and not self.busy else ['disabled'])
        self.shot.state(['!disabled'] if ready and self.arm.get() and not self.busy else ['disabled'])
        self.loop_button.state(['!disabled'] if has_window and not pending and not self.busy else ['disabled'])
        self.loop_button.configure(text='Lancer' if self.calibration_path and self.model_path else 'Préparer et lancer')
        self.export_button.state(['!disabled'] if self.session_path and not self.busy else ['disabled'])
        self.next.state(['!disabled'] if not self.busy and self.wizard is not None and self.wizard<5 and REGIONS[self.wizard][0] in self.rectangles else ['disabled'])
        self.back.state(['!disabled'] if not self.busy and self.wizard is not None and self.wizard>0 else ['disabled'])
        self.save.state(['!disabled'] if not self.busy and self.wizard==5 and self.none.get() else ['disabled'])
        self.stop_button.state(['!disabled'] if self.busy else ['disabled'])
        self.advanced_stop.state(['!disabled'] if self.busy else ['disabled'])
        for control in self.result_controls:control.state(['!disabled'] if pending and not self.busy else ['disabled'])
        if pending:
            self.auto_button.state(['disabled'])
            self.profile_button.state(['disabled']);self.model_button.state(['disabled'])
            self.capture_button.state(['disabled']);self.save.state(['disabled'])
            if not self.busy:
                self.status.set('Résultat à confirmer');self.detail.set('Ouvrez Options avancées → Séries et tirs pour confirmer le dernier résultat.')

    def start(self,title,function,game=True):
        if self.busy:return
        self.busy=True;self.cancel=Event();self.arm.set(False);self.loop_arm.set(False);self.assessment=None
        self.status.set(title);self.detail.set('Idleon passe au premier plan. L’interface revient à la fin de l’opération.' if game else 'Préparation de l’archive locale…')
        self._refresh_buttons();self.event(title)
        def work():
            try:self.queue.put(('done',function(self.cancel)))
            except Exception as exc:self.queue.put(('error',str(exc)))
        self.worker=Thread(target=work,name='idleon-assisted-operation',daemon=False);self.worker.start()

    def _drain(self):
        try:
            while True:
                kind,value=self.queue.get_nowait()
                if kind=='prepared':
                    self.completed(value);self._refresh_buttons();continue
                if kind=='progress':
                    if value.get('output') and value['output']!=self.session_path:
                        self.session_path=value['output'];self.persist()
                    self.status.set(value['message'])
                    rate=value.get('rate');text=f'{100*rate:.1f} % de rouges' if rate is not None else 'Mesure en cours'
                    self.detail.set(f'{value.get("shots",0)} tirs • {text} • {value.get("lives_lost",0)} vies perdues. Arrêt : F8 ou bouton Arrêter.')
                    continue
                self.busy=False
                try:
                    if kind=='error':self.show_error(value)
                    else:self.completed(value)
                except Exception as exc:self.show_error(str(exc))
                self._refresh_buttons()
                if self.closing:self.root.destroy();return
                self.root.deiconify();self.root.lift();self.root.focus_force()
        except Empty:pass
        self._drain_job=self.root.after(100,self._drain)

    def completed(self,result):
        self.event(json.dumps({k:v for k,v in result.items() if k not in ('observation','metrics')},ensure_ascii=False))
        if result.get('preview'):self.set_image(result['preview'])
        kind=result['kind']
        if kind=='capture':
            self.capture_region=Rect(**result['region']);self.rectangles={};self.wizard=0;self.none.set(False)
            self.tabs.select(0);self.status.set('Dessinez le premier repère sur l’image');self.show_step()
        elif kind=='auto-calibration':
            self.wizard=None;self.load_profile(result['calibration']);self.load_model(result['model'])
            self.status.set('Repères et modèle de tir chargés')
            self.detail.set('Prêt : choisissez le nombre de tirs et cliquez sur « Lancer ».')
            self.tabs.select(1)
        elif kind=='calibration':
            self.wizard=None;self.load_profile(result['calibration']);self.status.set('Profil visuel créé')
            self.detail.set('Vérifiez maintenant les repères dans Idleon. La trajectoire nécessite un modèle distinct.')
        elif kind=='verification':
            self.wizard=None;self.assessment=result['assessment'];self.status.set(self.assessment['title']);self.detail.set(self.assessment['detail'])
            o=result['observation'];wind=o.get('context_key') or 'inconnu';p=o.get('launcher_position')
            position=f'{p[0]:.0f}, {p[1]:.0f}' if p else 'inconnue'
            angle=self.assessment.get('aim_degrees');aim=f'{angle:.1f}°' if angle is not None else 'indisponible'
            self.telemetry.set(f'Vent : {wind}    |    Position : {position}    |    Visée : {aim}    |    {result["effective_fps"]:.0f} images/s')
            self.tabs.select(1)
        elif kind=='shot':
            self.wizard=None;self.tabs.select(1)
            self.status.set('Tir envoyé — confirmez le résultat' if result['inputs_sent'] else 'Aucun tir envoyé')
            self.detail.set('Regardez le score et l’impact, puis choisissez le résultat ci-dessus.' if result['inputs_sent'] else result.get('error','Essai arrêté.'))
        elif kind=='confirmation':
            self.status.set('Résultat enregistré');self.detail.set('Avant un nouvel essai, vérifiez à nouveau la position et le vent dans Idleon.')
        elif kind=='continuous':
            self.session_path=result['output']
            learned=Path(result.get('model') or Path(self.session_path)/'learned-model.json')
            if learned.exists():self.load_model(learned,persist=False)
            self.persist()
            rate=result.get('rate');text=f'{100*rate:.1f} %' if rate is not None else 'non mesuré'
            self.status.set('Série terminée' if result['state']=='complete' else 'Série arrêtée')
            self.detail.set(f'{result["shots"]} tirs, {result["bullseyes"]} rouges ({text}), {result["lives_lost"]} vies perdues. Données enregistrées. Cliquez sur « Exporter pour Codex ».')
        elif kind=='export':
            self.status.set('Session exportée pour analyse')
            self.detail.set(f'Archive locale : {result["archive"]}. Elle contient les résultats, les timings et les captures disponibles.')
        self.render()

    def capture(self):
        try:window=self.selected_window()
        except ValueError as exc:self.show_error(str(exc));return
        self.start('Capture de la référence…',lambda cancel:self.service.capture(window,cancel))

    def verify(self):
        try:window=self.selected_window()
        except ValueError as exc:self.show_error(str(exc));return
        profile,model=self.calibration_path,self.model_path
        if not profile:self.show_error('Chargez ou créez un profil visuel.');return
        self.start('Vérification des repères et du vent…',lambda cancel:self.service.verify(window,profile,model,cancel))

    def auto_calibrate(self):
        try:window=self.selected_window()
        except ValueError as exc:self.show_error(str(exc));return
        self.start('Calibration automatique du mini-jeu…',lambda cancel:self.service.auto_calibrate(window,cancel))

    def shoot(self):
        if not(self.assessment and self.assessment['ready'] and self.arm.get()) or self.busy:return
        window=self.selected_window();profile,model=self.calibration_path,self.model_path
        self.start('Un tir supervisé — F8 pour interrompre…',lambda cancel:self.service.shoot(window,profile,model,cancel))

    def confirm(self,result):
        profile=self.calibration_path
        self.start('Enregistrement du résultat…',lambda cancel:self.service.confirm(profile,result))

    def continuous(self):
        if self.busy:return
        try:
            count=int(self.series_count.get())
            if not 0<=count<=10000:raise ValueError()
        except ValueError:self.show_error('Nombre de tirs : 1 à 10 000, ou 0 pour continuer jusqu’à arrêt.');return
        recording=self.record_flight.get()
        window=self.selected_window();profile,model=self.calibration_path,self.model_path
        def launch(cancel):
            selected_profile,selected_model=profile,model
            if not selected_profile or not selected_model:
                prepared=self.service.auto_calibrate(window,cancel)
                selected_profile,selected_model=prepared['calibration'],prepared['model']
                self.queue.put(('prepared',prepared))
            return self.service.continuous(window,selected_profile,selected_model,cancel,
                lambda value:self.queue.put(('progress',value)),max_shots=count,record_flight=recording)
        self.start('Démarrage de la série et de la collecte…',launch)

    def export_session(self):
        if self.busy:return
        path=self.session_path
        if not path or not (Path(path)/'state.json').exists():
            path=filedialog.askdirectory(title='Choisir une série enregistrée',initialdir=self.service.directory/'reports')
        if path:self.start('Export des données pour Codex…',lambda cancel:self.service.export_session(path),game=False)


    def set_image(self,path):
        from .vision import cv2
        image=cv2.imread(str(path))
        if image is None:raise ValueError('L’aperçu ne peut pas être ouvert.')
        self.image=image;self.render()

    def render(self):
        if self.image is None:return
        from .vision import cv2
        height,width=self.image.shape[:2];cw,ch=self.canvas.winfo_width(),self.canvas.winfo_height()
        if min(cw,ch)<2:return
        scale=min(cw/width,ch/height);dw,dh=max(1,round(width*scale)),max(1,round(height*scale))
        scaled=cv2.resize(self.image,(dw,dh),interpolation=cv2.INTER_AREA)
        ok,encoded=cv2.imencode('.png',scaled)
        if not ok:return
        self.photo=tk.PhotoImage(data=base64.b64encode(encoded.tobytes()))
        left,top=(cw-dw)/2,(ch-dh)/2;self.viewport=(left,top,scale)
        self.canvas.delete('all');self.canvas.create_image(left,top,image=self.photo,anchor='nw')
        if self.wizard is not None:
            for key,rect in self.rectangles.items():
                x,y=left+rect.left*scale,top+rect.top*scale
                self.canvas.create_rectangle(x,y,x+rect.width*scale,y+rect.height*scale,outline=ACCENT,width=2)
                self.canvas.create_text(x+4,y+3,text=key,fill=ACCENT,anchor='nw',font=('Segoe UI',9,'bold'))

    def begin_drag(self,event):
        if self.busy or self.wizard is None or self.wizard>=5:return
        self.drag_start=(event.x,event.y)

    def move_drag(self,event):
        if not self.drag_start:return
        self.canvas.delete('selection');self.canvas.create_rectangle(*self.drag_start,event.x,event.y,
            outline='#fbbf24',width=2,tags='selection')

    def end_drag(self,event):
        if not self.drag_start:return
        start=self.drag_start;self.drag_start=None
        try:
            height,width=self.image.shape[:2]
            rect=selection_rect(start,(event.x,event.y),(width,height),self.viewport)
            if self.wizard>0 and not self.rectangles['scene'].contains(rect):raise ValueError('Ce repère doit être à l’intérieur du mini-jeu sélectionné.')
            self.rectangles[REGIONS[self.wizard][0]]=rect;self.render();self._refresh_buttons()
        except ValueError as exc:self.detail.set(str(exc));self.canvas.delete('selection')

    def show_step(self):
        if self.wizard<5:
            _,label,hint=REGIONS[self.wizard];self.guide.set(f'Étape {self.wizard+1}/5 — {label}. {hint}')
            self.detail.set('Glissez sur l’image pour dessiner le rectangle, puis validez ce repère.')
        else:
            self.guide.set('Repères sélectionnés. Vérifiez que le vent affiche None, puis créez le profil.')
            self.detail.set('Si le vent est différent, chargez un profil existant ou attendez une partie sans vent.')
        self._refresh_buttons();self.render()

    def next_region(self):
        if self.wizard is not None and self.wizard<5 and REGIONS[self.wizard][0] in self.rectangles:
            self.wizard+=1;self.show_step()

    def previous_region(self):
        if self.wizard is not None:self.wizard=max(0,self.wizard-1);self.show_step()

    def calibrate(self):
        window=self.selected_window();rectangles=dict(self.rectangles);region=self.capture_region;none=self.none.get()
        known=self.calibration_path or None
        self.start('Calibration visuelle — gardez le mini-jeu immobile…',
                   lambda cancel:self.service.calibrate(window,rectangles,region,none,cancel,known))

    def stop(self):
        if self.busy:
            self.cancel.set();self.status.set('Arrêt demandé…');self.detail.set('Attente de la libération des entrées et de l’enregistrement du résultat éventuel.')

    def close(self):
        if self.busy:self.closing=True;self.stop()
        else:self.root.destroy()


def main(args):
    import sys
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IdleonDarts.Assisted')
    home=Path(sys.executable).resolve().parent.parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[3]
    packaged_home=(next((p for p in Path(sys.executable).resolve().parents if p.name=='idleon-darts-app'),None)
                   if getattr(sys,'frozen',False) else None)
    directory=args.data_dir or str(packaged_home or home/'local'/'idleon-darts-app')
    service=AssistedService(directory)
    root=tk.Tk(className='IdleonDarts')
    def callback_error(_,value,__):
        messagebox.showerror('Idleon Darts',str(value),parent=root)
    root.report_callback_exception=callback_error
    AssistedApp(root,service,args.calibration,args.model)
    root.mainloop()
    return 0
