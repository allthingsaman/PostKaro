"""The background part: moves every post along at its time, checks logins, sends notifications.

It wakes every 20 seconds (and at once after the page schedules something). One post is handled at a
time, so a big upload never runs next to another one (low memory, simple). See db.py for the states.

  YouTube, Facebook  scheduled -> uploading -> processing -> waiting (the platform makes it live at its
                     time) -> live
  Instagram          scheduled -> (up to 23 h before its time) uploading -> processing -> waiting ->
                     (at its time) publishing -> live

Late posts (the laptop was off, or the uploads kept failing until after the time): with the "late"
setting "ask" they become `missed` and the page asks what to do; with "post" they go out at once.
"""
import json
import threading
import traceback
from datetime import timedelta

from . import db, notify, settings
from .platforms import get as platform
from .platforms.base import PlatformError

TICK = 20                                   # seconds between rounds
HEALTH_EVERY = timedelta(hours=6)
RETRY = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15)]
PROCESSING_LIMIT = timedelta(hours=2)
LIVE_LIMIT = timedelta(hours=1)             # remote-scheduled post still not live this long after its time
REUPLOAD_AFTER = timedelta(hours=23)        # an Instagram upload expires after 24 h
WARN_DAYS = (7, 1)

progress = {}                               # post id -> 0..1 while uploading (shown on the page)
_locks, _guard = {}, threading.Lock()


def lock(pid):
    with _guard:
        return _locks.setdefault(pid, threading.Lock())


def label(p):
    c = p['clip']
    return f"#{c['no']} {c['title'] or ''}".strip()


def tick(now=None):
    now = now or db.now()
    s = settings.load()
    ids = [r['id'] for r in db.rows(
        f"SELECT id FROM posts WHERE state IN ({','.join('?' * len(db.ACTIVE))}) "
        "ORDER BY COALESCE(when_utc, '0'), id", db.ACTIVE)]
    for pid in ids:
        lk = lock(pid)
        if not lk.acquire(blocking=False):
            continue
        try:
            step(pid, now, s)
        finally:
            lk.release()
    health(now)


def step(pid, now, s):
    p = db.post_full(pid)
    if not p or p['state'] not in db.ACTIVE:
        return
    if p['next_try'] and db.parse(p['next_try']) > now:
        return
    plat = platform(p['platform'])
    acc = db.active_account(p['platform'])
    when = db.parse(p['when_utc'])
    p['when'] = when
    grace = timedelta(minutes=int(s.get('late_grace_min') or 15))
    st = p['state']
    try:
        if not acc:
            raise PlatformError(f'{settings.NAMES[p["platform"]]} is not connected. Connect it on the Accounts page, '
                                f'then press Retry.')
        if st == 'scheduled':
            if when and plat.remote_schedule and plat.max_ahead and when - now > plat.max_ahead:
                return                                      # too far ahead for the platform: wait
            if when and not plat.remote_schedule and plat.upload_ahead and when - now > plat.upload_ahead:
                return                                      # Instagram: not inside the last 23 h yet
            if when and now > when + grace:
                if s.get('late') != 'post':
                    return missed(p, when)
                when = None
            if when and when - now < plat.min_ahead:
                when = None                                 # too close to schedule: post at once
            if when is None and p['when_utc']:
                db.update_post(pid, when_utc=None)
            p['when'] = when
            db.update_post(pid, state='uploading', error=None)
            progress[pid] = 0.0
            remote = plat.upload(p, acc, lambda f: progress.__setitem__(pid, max(0.0, min(1.0, f))))
            progress.pop(pid, None)
            db.update_post(pid, state='processing', remote_id=str(remote.get('id')), remote=remote,
                           prepared_at=db.iso(now), attempts=0, next_try=None)
            db.log(pid, 'uploaded')
        elif st == 'processing':
            status, info = plat.poll(p, acc)
            if status == 'processing':
                if p['prepared_at'] and now - db.parse(p['prepared_at']) > PROCESSING_LIMIT:
                    fail(p, f'{settings.NAMES[p["platform"]]} was still processing the video after 2 hours.')
            elif status == 'ready':
                db.update_post(pid, state='waiting', attempts=0, next_try=None)
                if not plat.remote_schedule and (when is None or now >= when):
                    step_publish(p, now, s, grace)
            elif status == 'live':
                live(p, info)
            else:
                fail(p, info or 'The platform rejected the video.')
        elif st == 'waiting':
            if plat.remote_schedule:
                if when and now < when:
                    return
                status, info = plat.poll(p, acc)
                if status == 'live':
                    live(p, info)
                elif status == 'failed':
                    fail(p, info or 'The platform rejected the video.')
                else:
                    since = when or db.parse(p['prepared_at']) or now
                    if now > since + LIVE_LIMIT:
                        fail(p, f'It was not live an hour after its time. Check it on {settings.NAMES[p["platform"]]}.')
            else:
                prepared = db.parse(p['prepared_at'])
                if when and now < when:
                    if prepared and now - prepared > REUPLOAD_AFTER:
                        plat.cancel(p, acc)
                        db.update_post(pid, state='scheduled', remote_id=None, remote={}, prepared_at=None)
                        db.log(pid, 'upload expired before its time: uploading again')
                    return
                step_publish(p, now, s, grace)
        elif st == 'uploading':                              # left over from a stop in the middle
            db.update_post(pid, state='scheduled')
        elif st == 'publishing':
            status, info = plat.poll(p, acc)
            if status == 'live':
                live(p, info)
            else:
                db.update_post(pid, state='waiting')
    except PlatformError as e:
        progress.pop(pid, None)
        problem(p, st, e, now)
    except Exception as e:                                  # a bug or something unexpected: retry, then fail
        progress.pop(pid, None)
        db.log(pid, 'error: ' + traceback.format_exc(limit=3))
        problem(p, st, PlatformError(f'Unexpected problem: {e}', retry=True), now)


def step_publish(p, now, s, grace):
    """Instagram at its time: press publish (or ask, when the laptop was off at the time)."""
    when = p['when']
    if when and now > when + grace and s.get('late') != 'post':
        return missed(p, when)
    prepared = db.parse(p['prepared_at'])
    plat = platform(p['platform'])
    acc = db.active_account(p['platform'])
    if prepared and now - prepared > timedelta(hours=24):
        db.update_post(p['id'], state='scheduled', remote_id=None, remote={}, prepared_at=None)
        db.log(p['id'], 'upload expired: uploading again')
        return
    db.update_post(p['id'], state='publishing')
    res = plat.publish(p, acc) or {}
    remote = {**p['remote'], **res}
    db.update_post(p['id'], remote=remote)
    live(p, res.get('url'))


def live(p, url):
    db.update_post(p['id'], state='live', url=url, error=None, posted_at=db.iso(db.now()), next_try=None)
    db.log(p['id'], f'live {url or ""}')
    notify.send(f'✅ {label(p)} is live on {settings.NAMES[p["platform"]]}')


def fail(p, reason):
    db.update_post(p['id'], state='failed', error=reason, next_try=None)
    db.log(p['id'], f'failed: {reason}')
    notify.send(f'❌ {label(p)} on {settings.NAMES[p["platform"]]}: {reason}', urgent=True)


def missed(p, when):
    db.update_post(p['id'], state='missed')
    db.log(p['id'], 'missed its time (the laptop was off)')
    notify.send(f'⏰ {label(p)} was due on {settings.NAMES[p["platform"]]} while this laptop was off. '
                f'Open PostKaro to post it now, pick a new time, or skip it.', urgent=True)


def problem(p, st, e, now):
    if e.login:
        acc = db.active_account(p['platform'])
        if acc:
            db.run("UPDATE accounts SET status='broken', problem=? WHERE platform=? AND account_id=?",
                   (str(e), acc['platform'], acc['account_id']))
        return fail(p, f'{e} Reconnect on the Accounts page, then press Retry.')
    n = int(p['attempts'] or 0)
    if e.retry and n < len(RETRY):
        back = {'uploading': 'scheduled', 'publishing': 'waiting'}.get(st, st)
        db.update_post(p['id'], state=back, attempts=n + 1, next_try=db.iso(now + RETRY[n]), error=str(e))
        db.log(p['id'], f'retry {n + 1}: {e}')
        return
    fail(p, str(e))


def health(now, force=False):
    """Check each connected account every 6 hours: is the login working, does it end soon?"""
    for a in db.accounts():
        checked = db.parse(a['checked'])
        if not force and checked and now - checked < HEALTH_EVERY:
            continue
        check_account(a, now)


def check_account(a, now=None):
    now = now or db.now()
    try:
        r = platform(a['platform']).check(a)
    except Exception as e:                                  # network down etc.: try again in 10 minutes
        if isinstance(e, PlatformError) and e.login:
            r = {'ok': False, 'problem': str(e)}
        else:
            r = None
    if r is None:
        db.run('UPDATE accounts SET checked=? WHERE platform=? AND account_id=?',
               (db.iso(now - HEALTH_EVERY + timedelta(minutes=10)), a['platform'], a['account_id']))
        return a
    extra = a['extra']
    status, prob = 'ok', None
    expires = r.get('expires') or a.get('expires')
    if not r.get('ok'):
        status, prob = 'broken', r.get('problem') or 'The login no longer works.'
        if a['status'] != 'broken':
            notify.send(f'❌ {settings.NAMES[a["platform"]]} ({a["name"]}): {prob} Reconnect on the Accounts page.',
                        urgent=True)
    elif expires:
        left = db.parse(expires) - now
        for d in WARN_DAYS:
            if left < timedelta(days=d):
                status = 'warn'
                prob = f'The login ends on {db.parse(expires).date().isoformat()}: reconnect before then.'
                if extra.get('warned') != d:
                    extra['warned'] = d
                    notify.send(f'⚠ {settings.NAMES[a["platform"]]} login ends in {max(0, left.days)} day(s). '
                                f'Reconnect on the Accounts page.')
    db.run('UPDATE accounts SET checked=?, status=?, problem=?, expires=?, extra=?, name=COALESCE(?, name) '
           'WHERE platform=? AND account_id=?',
           (db.iso(now), status, prob, expires, json.dumps(extra), r.get('name'), a['platform'], a['account_id']))
    return db.one('SELECT * FROM accounts WHERE platform=? AND account_id=?', (a['platform'], a['account_id']))


class Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name='postkaro-worker')
        self.wake = threading.Event()
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                tick()
            except Exception:
                traceback.print_exc()
            self.wake.wait(TICK)
            self.wake.clear()

    def poke(self):
        self.wake.set()

    def stop(self):
        self.stopped.set()
        self.wake.set()
