"""Desktop notifications ("✅ #1 is live on YouTube"). Best effort: if the system can't show one, the page
still shows everything. No extra packages: notify-send (Linux), osascript (macOS), PowerShell (Windows)."""
import base64
import os
import shutil
import subprocess
import sys

TITLE = 'PostKaro'

_WIN = r"""
$null=[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]
$null=[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]
$t=[Security.SecurityElement]::Escape($env:N_TITLE);$b=[Security.SecurityElement]::Escape($env:N_BODY)
$x=New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def send(text, urgent=False):
    if os.environ.get('POSTKARO_NO_NOTIFY'):
        return
    try:
        if sys.platform.startswith('linux') and shutil.which('notify-send'):
            subprocess.run(['notify-send', '--app-name=' + TITLE, '-u', 'critical' if urgent else 'normal', '--',
                            TITLE, text], timeout=10, check=False, capture_output=True)
        elif sys.platform == 'darwin':
            subprocess.run(['osascript', '-e', 'on run argv', '-e',
                            'display notification (item 2 of argv) with title (item 1 of argv)', '-e', 'end run',
                            TITLE, text], timeout=10, check=False, capture_output=True)
        elif os.name == 'nt':
            enc = base64.b64encode(_WIN.encode('utf-16-le')).decode()
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', enc],
                           env={**os.environ, 'N_TITLE': TITLE, 'N_BODY': text}, timeout=20, check=False,
                           capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        pass
