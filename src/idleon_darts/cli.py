"""Report implemented capabilities; unavailable operations never access the desktop."""
import argparse
from dataclasses import asdict
import json
import sys
from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='idleon-darts', description='Solveur Idleon — fondations en preparation.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='Afficher les fonctions reellement disponibles.')
    validate = commands.add_parser('validate-session', help='Valider un dossier ou ZIP externe, sans copie ni extraction.')
    validate.add_argument('session')
    validate.add_argument('--allow-partial', action='store_true', help='Accepter explicitement une session en erreur pour diagnostic.')
    for name in ('observe', 'run', 'replay'):
        command = commands.add_parser(name, help='Reserve : disponible apres implementation et calibration.')
        if name == 'replay':
            command.add_argument('session')
        command.add_argument('--profile', required=True)
    args = parser.parse_args(argv)
    if args.command == 'status':
        print(json.dumps(dict(version=__version__, stage='foundation',
                              available_commands=['status', 'validate-session'],
                              automatic_play_available=False, observation_available=False,
                              replay_available=False, frame_replay_available=True,
                              session_validation_available=True, private_capture_included=False), indent=2))
        return 0
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
