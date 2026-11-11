"""Logins and app secrets, kept only on this laptop.

They sit in one encrypted file (data folder: logins.enc). The key that opens it is kept in the computer's
own password store (Windows Credential Manager, macOS Keychain, GNOME Keyring / KWallet on Linux) through
the `keyring` library. A short key there avoids the Windows size limit (about 1280 characters), and the file
is useless without it.

No password store on this computer (rare: some minimal Linux setups): the key goes into a file only your
user can read (config folder: logins.key), and the Accounts page says so.

Nothing in here is ever printed, logged, sent to Claude or to any server. POSTKARO_VAULT=file forces the
key file (used by the tests).
"""
import json
import os
import threading

from . import paths

SERVICE, KEYNAME = 'PostKaro', 'logins-key'
TIMEOUT = 30                                 # seconds to wait for a password store that shows an unlock prompt
_key, _where, _problem = None, None, None
_lock = threading.RLock()


class VaultError(Exception):
    pass


def _file():
    return paths.data_dir() / 'logins.enc'


def _keyfile():
    return paths.config_dir() / 'logins.key'


def _with_timeout(fn, *args):
    out, err = [], []

    def run():
        try:
            out.append(fn(*args))
        except Exception as e:               # keyring raises many kinds
            err.append(e)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(TIMEOUT)
    if t.is_alive():
        raise VaultError('The password store did not answer. If your computer asks to unlock the keyring, '
                         'unlock it, then try again.')
    if err:
        raise err[0]
    return out[0] if out else None


def _keyring():
    """The usable keyring backend, or None."""
    if os.environ.get('POSTKARO_VAULT') == 'file':
        return None
    try:
        import keyring
        from keyring.backends import fail, null
    except ImportError:
        return None
    kr = keyring.get_keyring()
    if isinstance(kr, (fail.Keyring, null.Keyring)) or getattr(kr, 'priority', 0) < 1:
        return None
    return kr


def _master():
    global _key, _where, _problem
    if _key:
        return _key
    from cryptography.fernet import Fernet
    kr = _keyring()
    if kr:
        k = _with_timeout(kr.get_password, SERVICE, KEYNAME)
        if not k:
            if _file().exists():
                raise VaultError('The key of your saved logins is missing from the password store, so they '
                                 f'can\'t be opened. Delete {_file()} and connect your accounts again.')
            k = Fernet.generate_key().decode()
            _with_timeout(kr.set_password, SERVICE, KEYNAME, k)
            if _with_timeout(kr.get_password, SERVICE, KEYNAME) != k:
                raise VaultError('The password store did not keep the key. Logins can\'t be saved safely.')
        _key, _where, _problem = k.encode(), _describe(kr), None
        return _key
    kf = _keyfile()
    if kf.exists():
        k = kf.read_text().strip()
    else:
        k = Fernet.generate_key().decode()
        kf.write_text(k)
        try:
            os.chmod(kf, 0o600)
        except OSError:
            pass
    _key, _where = k.encode(), f'an encrypted file whose key is in {kf} (this computer has no password store)'
    _problem = ('No password store found: anyone who can read your user\'s files could read the logins. '
                'Install GNOME Keyring or KWallet for better protection.') if os.environ.get('POSTKARO_VAULT') != 'file' else None
    return _key


def _describe(kr):
    name = type(kr).__module__ + '.' + type(kr).__name__
    for k, v in (('Windows', 'Windows Credential Manager'), ('macOS', 'macOS Keychain'),
                 ('SecretService', 'your Linux keyring (GNOME Keyring / KWallet)'), ('kwallet', 'KWallet')):
        if k in name:
            return v
    return name


def _load():
    f = _file()
    if not f.exists():
        return {}
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return json.loads(Fernet(_master()).decrypt(f.read_bytes()))
    except InvalidToken:
        raise VaultError(f'Your saved logins could not be opened (wrong key). Delete {f} and connect again.')


def _save(d):
    from cryptography.fernet import Fernet
    f = _file()
    tmp = f.with_suffix('.tmp')
    tmp.write_bytes(Fernet(_master()).encrypt(json.dumps(d).encode()))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, f)


def get(name):
    with _lock:
        return _load().get(name)


def put(name, value):
    with _lock:
        d = _load()
        d[name] = value
        _save(d)


def delete(name):
    with _lock:
        d = _load()
        if d.pop(name, None) is not None:
            _save(d)


def status():
    """For the Accounts page: where logins are kept, and any problem."""
    try:
        _master()
        return {'ok': _problem is None, 'where': _where, 'problem': _problem}
    except Exception as e:
        return {'ok': False, 'where': 'nowhere yet', 'problem': str(e)}


def forget_key_cache():
    """Tests: drop the key held in memory."""
    global _key
    _key = None

