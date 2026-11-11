"""The user's posting defaults. Saved in the data folder as settings.json and changed on the ⚙ page."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import paths

PLATFORMS = ('youtube', 'instagram', 'facebook')
NAMES = {'youtube': 'YouTube', 'instagram': 'Instagram', 'facebook': 'Facebook'}

DEFAULTS = {
    'timezone': 'Asia/Kolkata',
    'times': {'youtube': ['18:00'], 'instagram': ['19:00'], 'facebook': ['20:00']},
    'per_day': 1,                    # clips per day on each platform ("Plan for me")
    'my_channels': [],               # no "not your video" warning for these channel names
    'youtube_made_for_kids': False,
    'youtube_notify_subscribers': True,
    'youtube_category': '24',        # Entertainment. 22 = People & Blogs, 27 = Education, 20 = Gaming
    'youtube_visibility': 'public',  # public / unlisted / private
    'youtube_full_video_line': True,  # add "Full video: <link>" to YouTube descriptions
    'late': 'ask',                   # Instagram when the laptop was off at posting time: ask / post
    'late_grace_min': 15,            # minutes late that still count as on time
}


def load():
    try:
        saved = json.loads((paths.data_dir() / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    s = json.loads(json.dumps(DEFAULTS))
    for k, v in saved.items():
        if k in s and isinstance(s[k], dict) and isinstance(v, dict):
            s[k].update(v)
        elif k in s:
            s[k] = v
    return s


def save(new):
    s = load()
    for k, v in new.items():
        if k not in DEFAULTS:
            continue
        if isinstance(DEFAULTS[k], dict) and isinstance(v, dict):
            s[k].update(v)
        else:
            s[k] = v
    (paths.data_dir() / 'settings.json').write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding='utf-8')
    return s


def tz(s=None):
    return ZoneInfo((s or load()).get('timezone') or 'UTC')


def to_local(dt, s=None):
    """UTC datetime -> 'YYYY-MM-DDTHH:MM' in the user's time zone (what the page's time boxes use)."""
    return dt.astimezone(tz(s)).strftime('%Y-%m-%dT%H:%M')


def from_local(text, s=None):
    """'YYYY-MM-DDTHH:MM' in the user's time zone -> UTC datetime."""
    try:
        naive = datetime.strptime((text or '').strip()[:16], '%Y-%m-%dT%H:%M')
    except ValueError:
        raise ValueError(f'not a date and time: {text!r}')
    return naive.replace(tzinfo=tz(s)).astimezone(timezone.utc)
