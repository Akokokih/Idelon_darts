"""Build a source archive from an allowlist; reject private captures in the project."""
import argparse
import os
from pathlib import Path
import tempfile
import zipfile

TOP_FILES = {'README.md', 'pyproject.toml', '.gitignore', 'Start-Idleon-Darts.cmd', 'Install-Idleon-Darts.ps1'}
TOP_DIRS = {'src', 'tests', 'tools', 'specs', '.specify', '.agents'}
SKIP_DIRS = {'__pycache__', '.git', '.venv', 'venv', 'dist', 'build', '.pytest_cache'}
PRIVATE_DIRS = {'work', 'private', 'sessions', 'recordings', 'captures', 'datasets',
                'dataset', 'capture-windows-prive', 'calibration-privee-windows'}
PRIVATE_FILES = {'lancer.cmd', 'test-10-secondes.cmd', 'emballer-session.cmd',
                 'pack_session.py', 'voir.html', 'session.json', 'frames.csv', 'events.jsonl'}
MEDIA_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.avi', '.mp4',
                  '.mov', '.mkv', '.wav', '.mp3', '.jsonl', '.csv', '.zip', '.7z'}
SOURCE_SUFFIXES = {'.py', '.md', '.toml', '.json', '.yml', '.yaml', '.sh', '.ps1', '.txt'}


def release_files(root: Path) -> list[Path]:
    selected = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        parent = Path(current)
        for name in directories[:]:
            directory = parent/name
            if directory.is_symlink():
                raise ValueError(f'Lien symbolique interdit : {directory.relative_to(root)}')
            if name.casefold() in PRIVATE_DIRS:
                raise ValueError(f'Dossier prive dans le projet : {directory.relative_to(root)}')
            if name in SKIP_DIRS or name.endswith('.egg-info'):
                directories.remove(name)
        for name in filenames:
            path = parent/name
            relative = path.relative_to(root)
            if path.is_symlink():
                raise ValueError(f'Lien symbolique interdit : {relative}')
            if (path.suffix.casefold() in MEDIA_SUFFIXES or name.casefold() in PRIVATE_FILES
                    or (len(relative.parts) == 1 and name.casefold() == 'capture.py')):
                raise ValueError(f'Capture ou outil prive interdit dans le projet : {relative}')
            if (len(relative.parts) == 1 and name in TOP_FILES):
                selected.append(path)
            elif (relative.parts[0] in TOP_DIRS and
                  (path.suffix.casefold() in SOURCE_SUFFIXES or name == '.gitignore')):
                selected.append(path)
    return sorted(selected)


def build_release(root: Path, destination: Path) -> int:
    root = Path(root).resolve()
    destination = Path(destination).absolute()
    if not root.is_dir():
        raise ValueError('Dossier projet absent')
    if destination.is_symlink():
        raise ValueError('Destination symbolique interdite')
    resolved_destination = destination.resolve()
    if resolved_destination.is_relative_to(root):
        raise ValueError('Creer l’archive a l’exterieur du projet')
    files = release_files(root)
    for required in ('README.md', 'pyproject.toml', 'src/idleon_darts/__init__.py'):
        if root/required not in files:
            raise ValueError(f'Fichier obligatoire absent : {required}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Validate before replacing a previously verified archive.
    fd, temporary = tempfile.mkstemp(prefix='idleon-release-', suffix='.zip', dir=destination.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, Path(root.name)/path.relative_to(root))
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive invalide')
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Archive source sans donnees privees.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or root.parent/(root.name+'.zip')
    try:
        count = build_release(root, output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Archive refusee : {exc}\n')
    print(f'{count} fichiers sources archives : {output}')
