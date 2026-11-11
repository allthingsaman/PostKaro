"""The queue and history (SQLite, one file in the data folder). No logins in here.

A batch is one ClipKaro video (or one post.json). Each clip in it has one post per platform. A post
moves through these states:

    draft       on the Post page, not scheduled yet
    scheduled   waiting for its time (or for the moment it may be uploaded)
    uploading   the video is being sent
    processing  the platform is processing the video
    waiting     uploaded; goes live at its time (YouTube and Facebook by themselves, Instagram by PostKaro)
    publishing  PostKaro is pressing "publish" (Instagram)
    live        posted, link known
    failed      something went wrong; the reason is in `error`, the page offers Retry
    missed      Instagram: the laptop was off at posting time; the page asks what to do
    cancelled   removed by the user
"""
import json
import sqlite3
from datetime import datetime, timezone

from . import paths

ACTIVE = ('scheduled', 'uploading', 'processing', 'waiting', 'publishing')
DONE = ('live', 'failed', 'cancelled')

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY, kit TEXT UNIQUE, project TEXT, title TEXT, channel TEXT, channel_url TEXT,
    source_url TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY, batch_id INTEGER, no INTEGER, file TEXT, duration REAL, size INTEGER,
    score REAL, title TEXT, caption TEXT, note TEXT, deep INTEGER DEFAULT 0, removed INTEGER DEFAULT 0,
    UNIQUE (batch_id, no));
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY, clip_id INTEGER, platform TEXT, enabled INTEGER DEFAULT 1,
    title TEXT DEFAULT '', body TEXT DEFAULT '', when_utc TEXT, state TEXT DEFAULT 'draft', account TEXT,
    remote_id TEXT, remote TEXT DEFAULT '{}', url TEXT, error TEXT, attempts INTEGER DEFAULT 0,
    next_try TEXT, prepared_at TEXT, posted_at TEXT, updated TEXT,
    UNIQUE (clip_id, platform));
CREATE TABLE IF NOT EXISTS accounts (
    platform TEXT, account_id TEXT, name TEXT, extra TEXT DEFAULT '{}', connected TEXT, expires TEXT,
    checked TEXT, status TEXT DEFAULT 'ok', problem TEXT, active INTEGER DEFAULT 1,
    PRIMARY KEY (platform, account_id));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, post_id INTEGER, at TEXT, text TEXT);
"""


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None


def parse(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(timezone.utc)


_ready = set()


def connect():
    """A new connection (the caller closes it). The tables are made once per database file."""
    path = paths.db_path()
    fresh = str(path) not in _ready or not path.exists()
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    if fresh:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript(SCHEMA)
        _ready.add(str(path))
    return con


def rows(sql, args=()):
    con = connect()
    try:
        with con:
            return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def one(sql, args=()):
    r = rows(sql, args)
    return r[0] if r else None


def run(sql, args=()):
    con = connect()
    try:
        with con:
            return con.execute(sql, args).lastrowid
    finally:
        con.close()


def post(pid):
    p = one('SELECT * FROM posts WHERE id=?', (pid,))
    if p:
        p['remote'] = json.loads(p.get('remote') or '{}')
    return p


def update_post(pid, **f):
    if 'remote' in f and not isinstance(f['remote'], str):
        f['remote'] = json.dumps(f['remote'])
    f['updated'] = iso(now())
    cols = ', '.join(f'{k}=?' for k in f)
    run(f'UPDATE posts SET {cols} WHERE id=?', (*f.values(), pid))


def log(pid, text):
    run('INSERT INTO events (post_id, at, text) VALUES (?, ?, ?)', (pid, iso(now()), text))


def post_full(pid):
    """A post with its clip and batch fields (what a platform needs to upload it)."""
    p = post(pid)
    if not p:
        return None
    c = one('SELECT * FROM clips WHERE id=?', (p['clip_id'],))
    b = one('SELECT * FROM batches WHERE id=?', (c['batch_id'],))
    p['clip'], p['batch'] = c, b
    return p


def accounts(platform=None):
    sql, args = 'SELECT * FROM accounts', ()
    if platform:
        sql, args = sql + ' WHERE platform=?', (platform,)
    out = rows(sql + ' ORDER BY platform, name', args)
    for a in out:
        a['extra'] = json.loads(a.get('extra') or '{}')
    return out


def active_account(platform):
    for a in accounts(platform):
        if a['active']:
            return a
    return None


def save_account(platform, account_id, name, extra=None, expires=None, active=True):
    if active:
        run('UPDATE accounts SET active=0 WHERE platform=?', (platform,))
    run('INSERT INTO accounts (platform, account_id, name, extra, connected, expires, checked, status, problem, '
        'active) VALUES (?, ?, ?, ?, ?, ?, ?, "ok", NULL, ?) ON CONFLICT (platform, account_id) DO UPDATE SET '
        'name=excluded.name, extra=excluded.extra, connected=excluded.connected, expires=excluded.expires, '
        'checked=excluded.checked, status="ok", problem=NULL, active=excluded.active',
        (platform, account_id, name, json.dumps(extra or {}), iso(now()), expires, iso(now()), int(active)))
