"""Package only the frozen application, public instructions and a launcher."""
from pathlib import Path
import argparse
import hashlib
import zipfile
from idleon_darts import __version__
from idleon_darts.calibration import external_directory


def package_windows(bundle, output, version=__version__):
    bundle=Path(bundle).resolve();output=external_directory(output)
    if not (bundle/'IdleonDarts.exe').is_file() or not (bundle/'_internal').is_dir():
        raise ValueError('Application Windows complète introuvable')
    files=[]
    for file in bundle.rglob('*'):
        if file.is_symlink():raise ValueError('Lien symbolique dans l’application')
        relative=file.relative_to(bundle)
        if any(part.lower() in {'profiles','reports','captures','recordings','local'} for part in relative.parts):
            raise ValueError('Données privées dans le dossier de distribution')
        if file.is_file():files.append(file)
    output.parent.mkdir(parents=True,exist_ok=True)
    prefix=f'IdleonDarts-{version}'
    launcher='@echo off\r\nstart "" "%~dp0IdleonDarts\\IdleonDarts.exe" --data-dir "%~dp0local\\idleon-darts-app"\r\n'
    guide=(f'IDLEON DARTS {version} - WINDOWS X64\n\n'
        '1. Extraire tout le ZIP dans un dossier personnel.\n'
        '2. Ouvrir Throwy Darts dans Idleon sur Steam.\n'
        '3. Double-cliquer sur Lancer.cmd. Python est inclus.\n'
        '4. Choisir le nombre de tirs et cliquer sur Lancer.\n'
        '   Au premier lancement, Preparer et lancer calibre automatiquement.\n'
        '5. Arreter ou F8 stoppe la serie. 0 tir signifie mode continu.\n\n'
        'Exporter enregistre les donnees pour une analyse ulterieure.\n'
        'Options avancees regroupe les reglages rarement necessaires.\n'
        'Garder le dossier IdleonDarts et son sous-dossier _internal ensemble.\n'
        'Les donnees sont creees dans local/idleon-darts-app, pres du lanceur.\n\n'
        'Reference de precision : 65 % de rouges sur 20 tirs. Les 90 % ne sont pas valides.\n'
        'Mode d emploi : https://github.com/Akokokih/Idelon_darts#mode-demploi\n')
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(files):archive.write(file,f'{prefix}/IdleonDarts/{file.relative_to(bundle).as_posix()}')
        archive.writestr(f'{prefix}/Lancer.cmd',launcher)
        archive.writestr(f'{prefix}/LIRE-MOI.txt',guide)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise ValueError('Archive Windows corrompue')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    return dict(archive=str(output),bytes=output.stat().st_size,files=len(files)+2,sha256=digest)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    import json
    print(json.dumps(package_windows(args.bundle,args.output),indent=2))
