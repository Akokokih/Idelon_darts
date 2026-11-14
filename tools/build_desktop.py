"""Build the desktop app outside the source tree. Private profiles stay external."""
from pathlib import Path
import argparse
import subprocess
import sys
from idleon_darts.calibration import external_directory


def main(argv=None):
    parser=argparse.ArgumentParser(description='Construire l’application Windows assistée.')
    parser.add_argument('--dist-dir',type=Path)
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    destination=external_directory(args.dist_dir or root.parent)
    work=external_directory(root.parent/'local'/'desktop-build')
    work.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
        '--name','IdleonDarts','--distpath',str(destination),'--workpath',str(work/'work'),
        '--specpath',str(work),'--paths',str(root/'src'),'--collect-all','dxcam',
        '--hidden-import','comtypes.client',str(root/'tools'/'desktop_entry.py')]
    return subprocess.run(command,cwd=root,check=False).returncode


if __name__=='__main__':raise SystemExit(main())
