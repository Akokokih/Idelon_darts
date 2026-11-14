"""Entry point for the desktop bundle; never arms a shot at startup."""
import sys
from idleon_darts.cli import main

if __name__=='__main__':
    raise SystemExit(main(['gui',*sys.argv[1:]]))
