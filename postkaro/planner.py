""""Plan for me": spread the clips over the coming days.

Each platform on its own: the best-scored clips first, `per_day` clips a day at the user's usual times
(settings "times"; a second clip on the same day goes 3 hours after the last usual time), starting with
the first free time at least 20 minutes from now. Times already taken in the queue are skipped.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, settings

LEAD = timedelta(minutes=20)       # time to upload before the first slot (Facebook needs 10 min ahead)
CLASH = timedelta(minutes=30)      # two posts on one platform closer than this count as the same slot


def day_times(platform, s):
    times = sorted(s['times'].get(platform) or ['18:00'])
    per_day = max(1, int(s.get('per_day') or 1))
    out = [tuple(map(int, t.split(':'))) for t in times[:per_day]]
    while len(out) < per_day:
        h, m = out[-1]
        if h + 3 > 23:
            break
        out.append((h + 3, m))
    return out


def slots(platform, s, now):
    tz = ZoneInfo(s.get('timezone') or 'UTC')
    day = now.astimezone(tz).date()
    while True:
        for h, m in day_times(platform, s):
            t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if t >= now + LEAD:
                yield t.astimezone(timezone.utc)
        day += timedelta(days=1)


def plan(posts, s=None, now=None, taken=None):
    """posts: [{'id', 'platform', 'score', 'no'}]  ->  {post id: UTC datetime}.
    taken: {platform: [UTC datetimes already in the queue]}."""
    s = s or settings.load()
    now = now or db.now()
    taken = taken or {}
    out = {}
    for plat in {p['platform'] for p in posts}:
        mine = sorted((p for p in posts if p['platform'] == plat), key=lambda p: (-(p.get('score') or 0), p['no']))
        busy = list(taken.get(plat, []))
        gen = slots(plat, s, now)
        for p in mine:
            t = next(gen)
            while any(abs(t - b) < CLASH for b in busy):
                t = next(gen)
            out[p['id']] = t
            busy.append(t)
    return out


def queue_taken(exclude_ids=()):
    """{platform: [UTC times]} of posts already scheduled or waiting."""
    taken = {}
    for r in db.rows(f"SELECT id, platform, when_utc FROM posts WHERE state IN ({','.join('?' * len(db.ACTIVE))})",
                     db.ACTIVE):
        if r['id'] not in exclude_ids and r['when_utc']:
            taken.setdefault(r['platform'], []).append(db.parse(r['when_utc']))
    return taken
