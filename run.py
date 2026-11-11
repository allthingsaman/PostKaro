"""PostKaro's single entry point. Always runs inside the project's .venv (made by install.py).

    python run.py open [folder | post.json]   open the page (and add a ClipKaro project to it)
    python run.py status                      accounts, queue, helper
    python run.py check                       check every connected login now
    python run.py service on|off|status       start PostKaro by itself at login (install.py turns it on)
    python run.py serve                       run the page and helper in this terminal (normally automatic)
    python run.py link [folder | post.json]   (for ClipKaro) add a project and print its link

Windows: use  python  instead of  python3 .
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'
PY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
PYW = VENV / 'Scripts' / 'pythonw.exe'


def in_venv():
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


if __name__ == '__main__':
    if not in_venv():
        if not PY.exists():
            print('PostKaro is not set up yet. Run:  python install.py   (python3 on macOS/Linux)')
            sys.exit(1)
        sys.exit(subprocess.call([str(PY), str(ROOT / 'run.py'), *sys.argv[1:]]))
    sys.path.insert(0, str(ROOT))
    from postkaro.cli import main
    main(sys.argv[1:])
