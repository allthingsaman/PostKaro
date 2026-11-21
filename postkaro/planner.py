""""Plan for me": spread the clips over the coming days.

Each platform on its own: the best-scored clips first, `per_day` clips a day at the user's usual times
(settings "times"; a second clip on the same day goes 3 hours after the last usual time), starting with
the first free time at least 20 minutes from now. Times already taken in the queue are skipped.

"Spread over" (spread()): every clip of a video over a time the owner picks, one even gap apart.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, settings

LEAD = timedelta(minutes=20)       # time to upload before the first slot (Facebook needs 10 min ahead)
CLASH = timedelta(minutes=30)      # two posts on one platform closer than this count as the same slot
MIN_GAP = timedelta(minutes=1)     # "Spread over": never closer together than this


def spread(clips, minutes, now):
    """clips: clip ids in posting order (clip number order) -> ({clip id: UTC time}, gap).
    The time is divided into one even gap: the first clip has no time (it goes out when Schedule is
    pressed), the next one gap later, and so on, so the last goes out just before the time is up.
    A clip's platforms all share its time."""
    n = len(clips)
    if not n:
        raise ValueError('No clip has a platform switched on.')
    if not minutes or minutes <= 0:
        raise ValueError('Pick how long to spread the clips over.')
    gap = timedelta(minutes=minutes) / n
    if gap < MIN_GAP:
        raise ValueError(f'{n} clips need at least {n} minutes (one a minute at most). Pick a longer time.')
    return {c: (None if k == 0 else now + gap * k) for k, c in enumerate(clips)}, gap


def day_peak(count, gap):
    """The most of `count` posts, one every `gap`, that can fall inside any 24 hours."""
    return min(count, int(timedelta(hours=24) / gap) + 1)


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
