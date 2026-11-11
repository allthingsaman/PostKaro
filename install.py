"""One-time setup: a private Python environment (.venv), the packages, and PostKaro starting by itself at login.

    python install.py              # everything (python3 on macOS/Linux)
    python install.py --no-service # don't start by itself at login (then Instagram posts only go out while
                                   # you have  python run.py open  running)

Safe to run again at any time (also after  git pull).
"""
import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'
PY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def run(cmd, label=None, **kw):
    print('   $', label or ' '.join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-service', action='store_true')
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    print('== PostKaro setup ==')
    if sys.version_info < (3, 11):
        print(f'[X] Python 3.11 or newer is needed (you have {sys.version.split()[0]}). Install it from python.org.')
        sys.exit(1)
    print(f'[ok] Python {sys.version.split()[0]}')

    if not PY.exists():
        print('-> creating .venv ...')
        venv.EnvBuilder(with_pip=True).create(VENV)
    r = run([PY, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'])
    r = run([PY, '-m', 'pip', 'install', '-q', '-r', ROOT / 'requirements.txt'])
    if r.returncode:
        print('[X] installing the packages failed (see above). Check your internet connection and run this again.')
        sys.exit(1)
    print('[ok] packages')

    code = ('import sys; sys.path.insert(0, %r)\n'
            'from postkaro import paths, vault, db\n'
            'info = paths.app_info(); db.connect().close()\n'
            'v = vault.status()\n'
            'print("[ok] data folder:", paths.data_dir())\n'
            'print("[%%s] logins will be kept in: %%s" %% ("ok" if v["ok"] else "!", v["where"]))\n'
            'v["problem"] and print("    " + v["problem"])\n') % str(ROOT)
    r = run([PY, '-c', code], label='checking the data folder and the password store')
    if r.returncode:
        print('[X] PostKaro could not set up its folders or the password store (see above).')
        sys.exit(1)

    if a.no_service:
        print('[--] not starting by itself at login (--no-service)')
    else:
        r = run([PY, ROOT / 'run.py', 'service', 'on'])

    py = 'python' if os.name == 'nt' else 'python3'
    print(f"""
Done. Next:
  1. {py} run.py open          opens PostKaro in your browser
  2. On the ⚙ page, connect YouTube, Facebook and Instagram. The step-by-step guide (about 30-45 minutes,
     once) is docs/connect-accounts.md.
  3. In ClipKaro, finished clips now end with a "Post them" link. For older ClipKaro videos:
     {py} run.py open /path/to/Claude_Clipper/output/<project>
""")


if __name__ == '__main__':
    main()
