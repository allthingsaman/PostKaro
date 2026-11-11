"""Start PostKaro's helper when you log in to your computer, so the page link always works and Instagram
posts go out at their time.

    Linux    a systemd user service (~/.config/systemd/user/postkaro.service), started with your
             desktop session (after the keyring is unlocked)
    Windows  a "Run" entry for your user (no admin rights), started with pythonw (no console window)
    macOS    a LaunchAgent (~/Library/LaunchAgents/com.postkaro.helper.plist)
"""
import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import paths

UNIT = 'postkaro.service'
LABEL = 'com.postkaro.helper'


def venv_python(windowless=False):
    v = paths.ROOT / '.venv'
    if os.name == 'nt':
        return v / 'Scripts' / ('pythonw.exe' if windowless else 'python.exe')
    return v / 'bin' / 'python'


def command(windowless=False):
    return [str(venv_python(windowless)), str(paths.ROOT / 'run.py'), 'serve']


def running():
    try:
        with urllib.request.urlopen(paths.base_url() + '/health', timeout=2) as r:
            return b'postkaro' in r.read()
    except Exception:
        return False


def start_background():
    """Start the helper now (if it isn't running) and wait until it answers."""
    if running():
        return True
    if sys.platform.startswith('linux') and installed():
        subprocess.run(['systemctl', '--user', 'start', UNIT], check=False, capture_output=True)
    elif sys.platform == 'darwin' and installed():
        subprocess.run(['launchctl', 'kickstart', f'gui/{os.getuid()}/{LABEL}'], check=False, capture_output=True)
    else:
        log = open(paths.data_dir() / 'postkaro.log', 'ab')
        kw = {'stdout': subprocess.DEVNULL, 'stderr': log, 'stdin': subprocess.DEVNULL}
        if os.name == 'nt':
            kw['creationflags'] = 0x00000008 | 0x00000200       # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(command(windowless=True), **kw)
        else:
            subprocess.Popen(command(), start_new_session=True, **kw)
    for _ in range(40):
        if running():
            return True
        time.sleep(0.25)
    return running()


# ---------- autostart ----------

def _unit_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'systemd' / 'user' / UNIT


def _plist_path():
    return Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'


def installed():
    if sys.platform.startswith('linux'):
        return _unit_path().exists()
    if sys.platform == 'darwin':
        return _plist_path().exists()
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as k:
                winreg.QueryValueEx(k, 'PostKaro')
                return True
        except OSError:
            return False
    return False


def install():
    """-> a sentence for the user."""
    if sys.platform.startswith('linux'):
        if not shutil.which('systemctl'):
            return 'No systemd here: start PostKaro yourself with  python run.py open'
        target = 'graphical-session.target'
        r = subprocess.run(['systemctl', '--user', 'is-active', target], capture_output=True, text=True)
        if r.stdout.strip() != 'active':
            target = 'default.target'
        up = _unit_path()
        up.parent.mkdir(parents=True, exist_ok=True)
        exe = ' '.join(f'"{c}"' if ' ' in c else c for c in command())
        up.write_text(f"""[Unit]
Description=PostKaro (posts your clips at their time)
After={target}
PartOf={target}

[Service]
ExecStart={exe}
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy={target}
""")
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False)
        r = subprocess.run(['systemctl', '--user', 'enable', '--now', UNIT], capture_output=True, text=True)
        if r.returncode:
            return f'Could not switch on the service: {r.stderr.strip()}'
        return f'Starts by itself when you log in (systemd user service "{UNIT}"; logs: journalctl --user -u postkaro)'
    if sys.platform == 'darwin':
        logs = Path.home() / 'Library' / 'Logs' / 'postkaro'
        logs.mkdir(parents=True, exist_ok=True)
        pp = _plist_path()
        pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_bytes(plistlib.dumps({
            'Label': LABEL, 'ProgramArguments': command(), 'RunAtLoad': True,
            'KeepAlive': {'SuccessfulExit': False}, 'StandardOutPath': str(logs / 'out.log'),
            'StandardErrorPath': str(logs / 'err.log')}))
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'], capture_output=True)
        r = subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(pp)], capture_output=True, text=True)
        if r.returncode:
            return f'Could not add the login item: {r.stderr.strip()}'
        return 'Starts by itself when you log in (macOS may show "Background Items Added": that is PostKaro)'
    if os.name == 'nt':
        import winreg
        value = subprocess.list2cmdline(command(windowless=True))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, 'PostKaro', 0, winreg.REG_SZ, value)
        start_background()
        return 'Starts by itself when you log in to Windows'
    return 'Start PostKaro yourself with  python run.py open'


def uninstall():
    if sys.platform.startswith('linux'):
        subprocess.run(['systemctl', '--user', 'disable', '--now', UNIT], capture_output=True)
        _unit_path().unlink(missing_ok=True)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False)
    elif sys.platform == 'darwin':
        subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'], capture_output=True)
        _plist_path().unlink(missing_ok=True)
    elif os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, 'PostKaro')
        except OSError:
            pass
    return 'PostKaro no longer starts by itself. Instagram posts only go out while you run  python run.py open'
