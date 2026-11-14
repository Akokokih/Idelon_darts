"""Report implemented capabilities; unavailable operations never access the desktop."""
import argparse
from dataclasses import asdict
import json
import math
import sys
import time
from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='idleon-darts', description='Solveur Idleon — fondations en preparation.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='Afficher les fonctions reellement disponibles.')
    gui = commands.add_parser('gui', help='Ouvrir l’application Windows en mode assisté.')
    gui.add_argument('--data-dir', help='Dossier local hors dépôt pour les profils et résultats.')
    gui.add_argument('--calibration', help='Profil visuel existant à charger.')
    gui.add_argument('--model', help='Modèle lié à ce profil, sans armement automatique.')
    loop=commands.add_parser('auto-run',help='Boucle expérimentale avec lecture automatique des résultats et arrêt F8.')
    loop.add_argument('--window-id',required=True,type=lambda value:int(value,0))
    loop.add_argument('--calibration',required=True);loop.add_argument('--model',required=True)
    loop.add_argument('--output',required=True);loop.add_argument('--arm',action='store_true')
    loop.add_argument('--max-shots',type=int,default=0,help='0 : continuer jusqu’à arrêt ou résultat illisible.')
    loop.add_argument('--no-flight',dest='record_flight',action='store_false',help='Désactiver les images de vol pour cette série.')
    loop.add_argument('--adapt-timing',action='store_true',help='Ajustement expérimental du délai pendant la série; désactivé par défaut pour la collecte.')
    loop.add_argument('--resume',action='store_true',help='Reprendre une série arrêtée dans son dossier existant.')
    export=commands.add_parser('export-series',help='Exporter une série de tirs et ses données pour analyse dans Codex.')
    export.add_argument('--session',required=True);export.add_argument('--output',required=True)
    validate = commands.add_parser('validate-session', help='Valider un dossier ou ZIP externe, sans copie ni extraction.')
    validate.add_argument('session')
    validate.add_argument('--allow-partial', action='store_true', help='Accepter explicitement une session en erreur pour diagnostic.')
    fit = commands.add_parser('fit-model', help='Ajuster un modele experimental sur impacts mesures, par contexte de vent.')
    fit.add_argument('--calibration', required=True)
    fit.add_argument('--samples', required=True)
    fit.add_argument('--output', required=True)
    fit.add_argument('--trigger-delay-ms', type=float, default=0)
    fit.add_argument('--target-x-offset', type=float, default=0)
    auto = commands.add_parser('auto-test', help='Un lancer automatique experimental puis arret pour confirmation du resultat.')
    auto.add_argument('--window-id', required=True, type=lambda value: int(value, 0))
    auto.add_argument('--calibration', required=True)
    auto.add_argument('--model', required=True)
    auto.add_argument('--output', required=True)
    auto.add_argument('--arm', action='store_true', help='Activer explicitement cet essai unique.')
    auto.add_argument('--supervised-calibration',action='store_true',help='Essai unique incertain : accepte une dispersion supérieure au rouge, sans désactiver les contrôles de contexte.')
    auto.add_argument('--max-wait', type=float, default=15)
    auto.add_argument('--hold-ms', type=float, default=1)
    auto.add_argument('--click-x', type=int, default=2400)
    auto.add_argument('--click-y', type=int, default=900)
    confirm = commands.add_parser('confirm-shot', help='Annoter le resultat observe du dernier essai avant tout nouveau tir.')
    confirm.add_argument('--calibration', required=True)
    confirm.add_argument('--result', choices=('centre','other','miss','unknown'), required=True)
    confirm.add_argument('--source', required=True)
    capture = commands.add_parser('capture-check', help='Tester la capture Windows en memoire, sans calibration ni clic.')
    capture.add_argument('--window-id', required=True, type=lambda value: int(value, 0), help='HWND decimal ou hexadecimal (0x...).')
    capture.add_argument('--frames', type=int, default=10, help='Nombre de captures, de 1 a 300.')
    capture.add_argument('--backend', choices=('dxgi', 'mss'), default='dxgi', help='DXGI rapide par defaut, MSS pour compatibilite.')
    capture.add_argument('--delay', type=float, default=3, help='Delai avant capture pour placer le jeu au premier plan (0 a 30 s).')
    for name in ('calibrate-visual', 'check-calibration'):
        visual = commands.add_parser(name, help='Calibrer ou verifier les reperes visuels, sans entree souris.')
        visual.add_argument('--window-id', required=True, type=lambda value: int(value, 0))
        visual.add_argument('--frames', type=int, default=240)
        visual.add_argument('--delay', type=float, default=3)
        if name == 'calibrate-visual':
            visual.add_argument('--regions', required=True, help='JSON des regions annotees, en pixels ecran physiques.')
            visual.add_argument('--output', required=True, help='Nouveau dossier prive hors depot.')
        else:
            visual.add_argument('--calibration', required=True, help='Dossier prive contenant profile.json et visual.json.')
            visual.add_argument('--report', help='Nouveau fichier JSON prive des observations.')
            visual.add_argument('--preview', help='Nouveau PNG prive avec reperes superposes.')
    for name in ('observe', 'run', 'replay'):
        command = commands.add_parser(name, help='Reserve : disponible apres implementation et calibration.')
        if name == 'replay':
            command.add_argument('session')
        command.add_argument('--profile', required=True)
    args = parser.parse_args(argv)
    if args.command == 'gui':
        from .gui import main as launch_gui
        return launch_gui(args)
    if args.command=='export-series':
        from .session_export import export_session
        print(json.dumps(export_session(args.session,args.output),ensure_ascii=False));return 0
    if args.command=='auto-run':
        if args.window_id<=0 or args.max_shots<0:parser.error('Fenêtre positive et limite de tirs positive ou nulle requises.')
        if args.arm:
            from .assisted import focus_game
            focus_game(args.window_id)
        from .continuous import run as run_continuous
        args.on_progress=lambda state:print(json.dumps(state,ensure_ascii=False),flush=True)
        result=run_continuous(args);print(json.dumps(result,ensure_ascii=False));return 0
    if args.command == 'status':
        print(json.dumps(dict(version=__version__, stage='experimental-desktop',
                              available_commands=['gui', 'auto-run', 'export-series', 'status', 'validate-session', 'capture-check',
                                                  'calibrate-visual', 'check-calibration',
                                                  'fit-model', 'auto-test', 'confirm-shot'],
                              visual_calibration_available=True, visual_check_available=True,
                              experimental_auto_test_available=True,
                              assisted_gui_available=True,
                              screen_capture_implemented=True,
                              capture_backends=['dxgi', 'winrt', 'mss'], default_capture_backend='dxgi',
                              automatic_play_available=True, observation_available=False,
                              replay_available=False, frame_replay_available=True,
                              session_validation_available=True, private_capture_included=False), indent=2))
        return 0
    if args.command in ('fit-model', 'auto-test', 'confirm-shot'):
        if args.command == 'auto-test' and (args.window_id <= 0 or not math.isfinite(args.max_wait)
                or not 1 <= args.max_wait <= 30 or not math.isfinite(args.hold_ms) or not 1 <= args.hold_ms <= 50):
            parser.error('HWND positif, attente 1..30 secondes, maintien 1..50 ms requis')
        try:
            if args.command == 'fit-model':
                from .calibration import load_visual_calibration, external_directory, _visual_json
                from .prediction import fit_impact_model
                calibration = load_visual_calibration(args.calibration)
                data = _visual_json(args.samples)
                if not isinstance(data, dict) or not isinstance(data.get('samples'), list):
                    raise ValueError('Liste samples requise')
                if not math.isfinite(args.trigger_delay_ms) or not 0 <= args.trigger_delay_ms <= 200:
                    raise ValueError('Delai de declenchement requis entre 0 et 200 ms')
                model = fit_impact_model(data['samples'], profile_id=calibration.profile.profile_id,
                                        trigger_delay_ns=int(args.trigger_delay_ms * 1e6),
                                        target_x_offset=args.target_x_offset)
                destination = external_directory(args.output)
                model.save(destination)
                print(json.dumps(dict(stage='experimental', profile_id=model.profile_id,
                                      contexts=model.contexts, output=str(destination)), indent=2))
                return 0
            from .auto_test import run, confirm
            return run(args) if args.command == 'auto-test' else confirm(args.calibration, args.result, args.source)
        except (ValueError, OSError, RuntimeError, ImportError) as exc:
            print(f'Essai refuse : {exc}', file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print('Essai interrompu.', file=sys.stderr)
            return 130
    if args.command in ('calibrate-visual', 'check-calibration'):
        minimum = 30 if args.command == 'calibrate-visual' else 1
        if args.window_id <= 0 or not minimum <= args.frames <= 1000:
            parser.error(f'HWND positif et --frames entre {minimum} et 1000 requis')
        if not math.isfinite(args.delay) or not 0 <= args.delay <= 30:
            parser.error('--delay doit etre entre 0 et 30 secondes')
        from .visual_workflow import run
        return run(args)
    if args.command == 'capture-check':
        if args.window_id <= 0 or not 1 <= args.frames <= 300:
            parser.error('HWND positif et --frames entre 1 et 300 requis')
        if not math.isfinite(args.delay) or not 0 <= args.delay <= 30:
            parser.error('--delay doit etre entre 0 et 30 secondes')
        from .capture import CaptureError, WindowsFrameSource
        from .windows_io import WindowsDesktop
        try:
            if args.delay:
                print(f'Capture dans {args.delay:g} s : placer le jeu au premier plan.', file=sys.stderr)
                time.sleep(args.delay)
            desktop = WindowsDesktop(args.window_id)
            durations = []
            with WindowsFrameSource(desktop, backend=args.backend) as source:
                started = time.perf_counter_ns()
                for _ in range(args.frames):
                    frame = source.grab()
                    durations.append((frame.end_ns - frame.start_ns) / 1_000_000)
                elapsed_ns = time.perf_counter_ns() - started
            print(json.dumps(dict(frames=len(durations), backend=args.backend, region=asdict(frame.region),
                                  elapsed_seconds=elapsed_ns / 1_000_000_000,
                                  effective_fps=len(durations) * 1_000_000_000 / max(1, elapsed_ns),
                                  capture_ms_min=min(durations), capture_ms_max=max(durations),
                                  capture_ms_mean=sum(durations) / len(durations),
                                  capture_ms_p95=sorted(durations)[math.ceil(.95 * len(durations)) - 1],
                                  frames_over_16_67ms=sum(duration > 1000 / 60 for duration in durations),
                                  frames_over_100ms=sum(duration > 100 for duration in durations),
                                  images_saved=False, inputs_sent=False), indent=2))
            return 0
        except CaptureError as exc:
            print(f'Capture refusee : {exc}', file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print('Capture interrompue.', file=sys.stderr)
            return 130
    if args.command == 'validate-session':
        from .session import SessionValidationError, open_session
        try:
            with open_session(args.session, allow_partial=args.allow_partial) as session:
                print(json.dumps(dict(validation='complete' if session.summary.complete else 'partial',
                                      summary=asdict(session.summary) | {'complete': session.summary.complete},
                                      input_spans=len(session.clicks),
                                      manual_annotations=len(session.annotations), warnings=session.warnings),
                                 ensure_ascii=False, indent=2))
            return 0
        except SessionValidationError as exc:
            print(f'Session refusee : {exc}', file=sys.stderr)
            return 1
    print(f'{args.command} indisponible : adaptateurs, detection et calibration non implementes. '
          'Aucune entree envoyee au jeu.', file=sys.stderr)
    return 2
