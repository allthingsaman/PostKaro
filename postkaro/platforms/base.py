"""What every platform plug-in does. Adding a platform later = one new file with these methods.

The worker (worker.py) calls them; they never touch the database themselves except through the
`post` dict they get and the dict they return.
"""
from datetime import timedelta


class PlatformError(Exception):
    """retry=True: try again later (network, platform busy). login=True: the login is broken, the user must
    reconnect. Otherwise the post fails with this message (written for the user, in plain words)."""

    def __init__(self, message, retry=False, login=False):
        super().__init__(message)
        self.retry, self.login = retry, login


class Platform:
    name = ''
    remote_schedule = True             # True: the platform makes the post live at its time by itself
    upload_ahead = None                # how long before the time the upload may start (None: any time)
    max_ahead = None                   # remote_schedule only: the farthest ahead the platform accepts
    min_ahead = timedelta(0)           # a time closer than this is posted at once

    def check(self, account):
        """Is the login working? -> {'ok': bool, 'name': str, 'expires': iso or None, 'problem': str or None}"""
        raise NotImplementedError

    def upload(self, post, account, progress):
        """Send the video. progress(fraction) may be called. -> dict saved as post['remote']
        (must hold 'id'). The post's time is post['when'] (UTC datetime, or None for "now")."""
        raise NotImplementedError

    def poll(self, post, account):
        """-> ('processing', None) | ('ready', None) | ('live', url) | ('failed', reason)"""
        raise NotImplementedError

    def publish(self, post, account):
        """Only for platforms without remote scheduling (Instagram): make it live now. -> dict merged into
        post['remote'] (may hold 'url')."""
        raise NotImplementedError

    def update(self, post, account):
        """Change the text or time of an uploaded post on the platform. -> True if done, False if it can't
        be changed (the worker then removes it and uploads again)."""
        return False

    def cancel(self, post, account):
        """Remove an uploaded post that isn't live yet (or the waiting upload)."""
        return None
