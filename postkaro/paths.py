"""Where PostKaro keeps its files. Nothing secret lives here: logins go to the password store (vault.py).

    data folder     postkaro.db (queue, history), settings.json, waiting/ (clips waiting for Instagram), log
    config folder   app.json: where PostKaro is, its port and the key of the local page. ClipKaro reads it
                    to know PostKaro is installed.

POSTKARO_HOME=<folder> puts both in one folder (used by the tests).
"""
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
DEFAULT_PORT = 8765


def _home(kind):
    if os.environ.get('POSTKARO_HOME'):
        return Path(os.environ['POSTKARO_HOME'])
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'postkaro'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'postkaro'
    var, default = {'data': ('XDG_DATA_HOME', '.local/share'), 'config': ('XDG_CONFIG_HOME', '.config')}[kind]
    return Path(os.environ.get(var) or Path.home() / default) / 'postkaro'


def data_dir():
    d = _home('data')
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir():
    d = _home('config')
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path():
    return data_dir() / 'postkaro.db'


def waiting_dir():
    d = data_dir() / 'waiting'
    d.mkdir(exist_ok=True)
    return d


def app_file():
    return config_dir() / 'app.json'


def app_info():
    """{"path", "port", "key"}; made on first use. The key is part of the page link, so that other web
    pages open in the browser can't use PostKaro's page."""
    f = app_file()
    try:
        info = json.loads(f.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        info = {}
    changed = False
    if not info.get('key'):
        info['key'], changed = secrets.token_urlsafe(24), True
    if not info.get('port'):
        info['port'], changed = DEFAULT_PORT, True
    if info.get('path') != str(ROOT):
        info['path'], changed = str(ROOT), True
    if changed:
        f.write_text(json.dumps(info, indent=1), encoding='utf-8')
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return info


def base_url():
    return f"http://127.0.0.1:{app_info()['port']}"


def page_link(route=''):
    """The link that opens the page (with the key)."""
    return f"{base_url()}/?k={app_info()['key']}" + (f'#/{route}' if route else '')
