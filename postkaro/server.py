"""The local web server: the page (web/) and the small API it calls. Only reachable from this laptop.

Safety:
  - it listens on 127.0.0.1 only, so other devices on the Wi-Fi can't reach it;
  - requests must say Host 127.0.0.1:<port> or localhost:<port> (blocks "DNS rebinding" tricks);
  - the page needs the key from app.json: the link carries it once (?k=...), then a cookie that other
    websites can't send (SameSite=Strict); changes also need the key in a header, which other websites
    can't add without permission we never give (no CORS).
"""
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__, db, kit, paths, planner, rules, settings, vault, worker
from .platforms import get as platform
from .platforms.base import PlatformError

WORKER = None
PENDING = {}                                   # login state -> (platform, data, time)
LOCK_WAIT = 30


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ---------- helpers ----------

def key():
    return paths.app_info()['key']


def host_ok(request):
    port = paths.app_info()['port']
    return request.headers.get('host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')


def authed(request, write=False):
    k = key()
    ok = secrets.compare_digest(request.cookies.get('pk', ''), k) or \
        secrets.compare_digest(request.query_params.get('k', ''), k)
    if write:
        port = paths.app_info()['port']
        origin = request.headers.get('origin')
        ok = ok and secrets.compare_digest(request.headers.get('x-postkaro', ''), k) \
            and (origin is None or origin in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')) \
            and request.headers.get('sec-fetch-site', 'same-origin') == 'same-origin'
    return ok


def api(fn):
    """JSON endpoint: checks host and key, reads the body, runs fn(request, body) in a worker thread."""
    async def endpoint(request: Request):
        if not host_ok(request):
            return JSONResponse({'error': 'wrong host'}, 403)
        if not authed(request, write=request.method != 'GET'):
            return JSONResponse({'error': 'Open PostKaro with its link (python run.py open).'}, 401)
        body = {}
        if request.method in ('POST', 'PUT', 'PATCH'):
            raw = await request.body()
            body = json.loads(raw) if raw else {}
        try:
            out = await run_in_threadpool(fn, request, body)
        except ApiError as e:
            return JSONResponse({'error': str(e)}, e.status)
        except (ValueError, vault.VaultError) as e:
            return JSONResponse({'error': str(e)}, 400)
        except PlatformError as e:
            return JSONResponse({'error': str(e)}, 502)
        return JSONResponse(out if out is not None else {'ok': True})
    return endpoint


def poke():
    if WORKER:
        WORKER.poke()


def with_lock(pid):
    lk = worker.lock(pid)
    if not lk.acquire(timeout=LOCK_WAIT):
        raise ApiError('PostKaro is busy with this post right now (uploading). Try again in a minute.', 409)
    return lk


# ---------- views ----------

def post_view(p, clip, s):
    when = db.parse(p['when_utc'])
    errors, warnings = rules.check(p['platform'], p['title'], p['body'], clip)
    return {'id': p['id'], 'platform': p['platform'], 'enabled': bool(p['enabled']), 'title': p['title'],
            'body': p['body'], 'when': settings.to_local(when, s) if when else '', 'state': p['state'],
            'url': p['url'], 'error': p['error'], 'errors': errors, 'warnings': warnings,
            'progress': worker.progress.get(p['id']), 'attempts': p['attempts'],
            'hashtags': len(rules.hashtags(p['body'])), 'chars': len(p['body'] or ''),
            'title_chars': len(p['title'] or ''), 'desc_bytes': len((p['body'] or '').encode('utf-8'))}


def clip_view(c):
    warn = []                                  # "not your video" is shown once, above all the clips
    if c['note']:
        warn.append(f"Honesty note: {c['note']}")
    return {'id': c['id'], 'no': c['no'], 'title': c['title'], 'duration': c['duration'], 'score': c['score'],
            'deep': bool(c['deep']), 'removed': bool(c['removed']), 'warnings': warn,
            'exists': Path(c['file']).exists(), 'media': f"/media/clip/{c['id']}", 'thumb': f"/media/thumb/{c['id']}"}


def batch_view(bid):
    s = settings.load()
    b = db.one('SELECT * FROM batches WHERE id=?', (bid,))
    if not b:
        raise ApiError('No such batch.', 404)
    clips = db.rows('SELECT * FROM clips WHERE batch_id=? ORDER BY no', (bid,))
    out = []
    for c in clips:
        cv = clip_view(c)
        cv['posts'] = {p['platform']: post_view(p, c, s)
                       for p in db.rows('SELECT * FROM posts WHERE clip_id=?', (c['id'],))}
        out.append(cv)
    return {**{k: b[k] for k in ('id', 'project', 'title', 'channel', 'source_url')},
            'own': kit.is_own(b, s), 'clips': out}


def account_view(a):
    return {k: a[k] for k in ('platform', 'account_id', 'name', 'status', 'problem', 'expires', 'checked',
                              'active', 'connected')} | {'username': a['extra'].get('username')}


# ---------- endpoints ----------

def state(request, body):
    s = settings.load()
    return {'version': __version__, 'settings': s, 'accounts': [account_view(a) for a in db.accounts()],
            'apps': {'google': vault.get('app:google') is not None, 'meta': vault.get('app:meta') is not None},
            'vault': vault.status(), 'now': settings.to_local(db.now(), s), 'base': paths.base_url(),
            'redirects': {'google': redirect('google'), 'meta': redirect('meta')},
            'counts': {r['state']: r['n'] for r in db.rows('SELECT state, COUNT(*) n FROM posts GROUP BY state')}}


def batches(request, body):
    return db.rows('SELECT b.id, b.project, b.title, b.channel, b.created, COUNT(DISTINCT c.id) clips, '
                   "SUM(p.state='draft' AND p.enabled AND c.removed=0) drafts, SUM(p.state='live') live "
                   'FROM batches b LEFT JOIN clips c ON c.batch_id=b.id LEFT JOIN posts p ON p.clip_id=c.id '
                   'GROUP BY b.id ORDER BY b.id DESC')


def batch(request, body):
    return batch_view(int(request.path_params['id']))


def import_(request, body):
    path = (body.get('path') or '').strip()
    if not path:
        raise ApiError('Give the path of a post.json or a ClipKaro project folder.')
    try:
        bid = kit.import_kit(path)
    except (ValueError, OSError) as e:
        raise ApiError(str(e))
    return {'id': bid}


def edit_post(request, body):
    pid = int(request.path_params['id'])
    s = settings.load()
    lk = with_lock(pid)
    try:
        p = db.post_full(pid)
        if not p:
            raise ApiError('No such post.', 404)
        f = {}
        if 'enabled' in body:
            f['enabled'] = int(bool(body['enabled']))
        for k in ('title', 'body'):
            if k in body:
                f[k] = body[k] or ''
        if 'when' in body:
            f['when_utc'] = db.iso(settings.from_local(body['when'], s)) if body['when'] else None
        if p['state'] in ('uploading', 'publishing'):
            raise ApiError('This post is being sent right now. Try again in a minute.', 409)
        if p['state'] in ('live',):
            raise ApiError('This post is already live; change it on the platform itself.')
        db.update_post(pid, **f)
        if p['state'] in ('processing', 'waiting') and set(f) & {'title', 'body', 'when_utc'}:
            p2 = db.post_full(pid)
            p2['when'] = db.parse(p2['when_utc'])
            plat, acc = platform(p['platform']), db.active_account(p['platform'])
            if not plat.update(p2, acc):            # can't change it there: remove and upload again
                plat.cancel(p2, acc)
                db.update_post(pid, state='scheduled', remote_id=None, remote={}, prepared_at=None)
                db.log(pid, 'changed after upload: uploading again')
                poke()
        return post_view(db.post(pid), p['clip'], s)
    finally:
        lk.release()


def remove_clip(request, body):
    cid = int(request.path_params['id'])
    restore = request.url.path.endswith('/restore')
    if not restore:
        for p in db.rows("SELECT id FROM posts WHERE clip_id=? AND state IN ('scheduled', 'processing', 'waiting', "
                         "'missed')", (cid,)):
            cancel_post(p['id'])
    db.run('UPDATE clips SET removed=? WHERE id=?', (0 if restore else 1, cid))
    return {'ok': True}


def plan(request, body):
    """Fill in times for the batch's ticked drafts (still drafts: nothing is scheduled until Schedule)."""
    bid = int(request.path_params['id'])
    s = settings.load()
    connected = {a['platform'] for a in db.accounts() if a['active']}
    todo = db.rows("SELECT p.id, p.platform, c.score, c.no FROM posts p JOIN clips c ON c.id=p.clip_id "
                   "WHERE c.batch_id=? AND c.removed=0 AND p.enabled=1 AND p.state='draft'", (bid,))
    todo = [t for t in todo if t['platform'] in connected or body.get('all_platforms')]
    times = planner.plan(todo, s, taken=planner.queue_taken(exclude_ids={t['id'] for t in todo}))
    for pid, t in times.items():
        db.update_post(pid, when_utc=db.iso(t))
    return batch_view(bid)


def schedule(request, body):
    """Schedule the given posts (or every ticked draft of a batch). Posts with problems are skipped and
    listed with their reasons."""
    if 'batch' in body:
        ids = [r['id'] for r in db.rows("SELECT p.id FROM posts p JOIN clips c ON c.id=p.clip_id WHERE c.batch_id=? "
                                        "AND c.removed=0 AND p.enabled=1 AND p.state='draft'", (int(body['batch']),))]
    else:
        ids = [int(i) for i in body.get('ids', [])]
    done, now_n, skipped = 0, 0, []
    for pid in ids:
        p = db.post_full(pid)
        if not p or p['state'] != 'draft':
            continue
        why = list(rules.check(p['platform'], p['title'], p['body'], p['clip'])[0])
        if not db.active_account(p['platform']):
            why.append(f"{settings.NAMES[p['platform']]} is not connected (⚙ page).")
        if not Path(p['clip']['file']).exists():
            why.append('The video file is gone from its folder.')
        when = db.parse(p['when_utc'])
        if when and when < db.now():
            why.append('This time has passed. Pick a later time, or clear it to post now.')
        if why:
            skipped.append({'id': pid, 'clip': p['clip']['no'], 'platform': p['platform'], 'why': why})
            continue
        db.update_post(pid, state='scheduled', attempts=0, error=None, next_try=None)
        db.log(pid, f"scheduled for {p['when_utc'] or 'now'}")
        done += 1
        now_n += not when
    poke()
    return {'scheduled': done, 'now': now_n, 'skipped': skipped}


def cancel_post(pid):
    lk = with_lock(pid)
    try:
        p = db.post_full(pid)
        if p['state'] in ('uploading', 'publishing'):
            raise ApiError('This post is being sent right now. Try again in a minute.', 409)
        if p['state'] == 'live':
            raise ApiError('This post is already live; delete it on the platform itself.')
        if p['remote_id'] and p['state'] in ('processing', 'waiting'):
            p['when'] = db.parse(p['when_utc'])
            platform(p['platform']).cancel(p, db.active_account(p['platform']))
        db.update_post(pid, state='cancelled', remote_id=None, remote={}, prepared_at=None, next_try=None)
        db.log(pid, 'cancelled')
    finally:
        lk.release()


def post_action(request, body):
    pid = int(request.path_params['id'])
    action = request.path_params['action']
    s = settings.load()
    p = db.post(pid)
    if not p:
        raise ApiError('No such post.', 404)
    if action == 'cancel':
        cancel_post(pid)
    elif action == 'draft':                         # back to the Post page (after cancel / fail)
        if p['state'] not in ('cancelled', 'failed', 'missed'):
            raise ApiError('Only cancelled, failed or missed posts can go back to drafts.')
        db.update_post(pid, state='draft', remote_id=None, remote={}, prepared_at=None, error=None, attempts=0)
    elif action in ('retry', 'now', 'time'):
        if p['state'] not in ('failed', 'missed', 'draft'):
            raise ApiError('Only failed, missed or draft posts can be sent again.')
        when = None
        if action == 'time':
            when = settings.from_local(body.get('when', ''), s)
            if when < db.now():
                raise ApiError('Pick a time in the future.')
        elif action == 'retry':
            old = db.parse(p['when_utc'])
            when = old if old and old > db.now() else None
        f = {'state': 'scheduled', 'when_utc': db.iso(when) if when else None, 'attempts': 0, 'next_try': None,
             'error': None}
        if p['state'] == 'failed' and p['remote_id']:
            f.update(remote_id=None, remote={}, prepared_at=None)
        db.update_post(pid, **f)
        db.log(pid, f'{action}: scheduled for {f["when_utc"] or "now"}')
        poke()
    elif action == 'skip':
        db.update_post(pid, state='cancelled')
    else:
        raise ApiError('Unknown action.', 404)
    return post_view(db.post(pid), db.one('SELECT * FROM clips WHERE id=?', (p['clip_id'],)), s)


def listing(states, order, limit=300):
    s = settings.load()
    out = []
    for p in db.rows(f"SELECT p.*, c.no, c.title clip_title, c.duration, c.size, b.project, b.title video, b.id batch "
                     f"FROM posts p JOIN clips c ON c.id=p.clip_id JOIN batches b ON b.id=c.batch_id "
                     f"WHERE p.state IN ({','.join('?' * len(states))}) ORDER BY {order} LIMIT {limit}", states):
        v = post_view(p, {'duration': p['duration'], 'size': p['size']}, s)
        v.update(no=p['no'], clip_title=p['clip_title'], video=p['video'] or p['project'], batch=p['batch'],
                 posted=settings.to_local(db.parse(p['posted_at']), s) if p['posted_at'] else '',
                 updated=settings.to_local(db.parse(p['updated']), s) if p['updated'] else '')
        out.append(v)
    return out


def queue(request, body):
    return listing((*db.ACTIVE, 'missed'), "COALESCE(p.when_utc, '0'), p.id")


def posted(request, body):
    return listing(db.DONE, 'p.updated DESC')


def save_settings(request, body):
    s = settings.save(body)
    try:
        settings.to_local(db.now(), s)
    except Exception:
        raise ApiError('Unknown time zone.')
    return s


# ---------- apps and accounts ----------

def redirect(name):
    """Where Google / Meta send the browser back. Google: the page's own address (desktop apps use the plain
    loopback address). Meta: a fixed localhost address, which Meta allows while the app is in development."""
    port = paths.app_info()['port']
    return f'http://localhost:{port}/oauth/meta' if name == 'meta' else f'http://127.0.0.1:{port}/'


def save_app(request, body):
    name = request.path_params['name']
    if name == 'google':
        cfg = body.get('client') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except ValueError:
                raise ApiError('That is not the JSON file Google gave you (client_secret_....json).')
        inner = cfg.get('installed') or cfg.get('web') or cfg
        if not inner.get('client_id') or not inner.get('client_secret'):
            raise ApiError('The file needs client_id and client_secret. Download it again from Google Cloud '
                           '(Clients -> your Desktop client -> Download JSON).')
        if 'web' in cfg:
            raise ApiError('This is a "Web application" client. Make a "Desktop app" client instead '
                           '(docs/connect-accounts.md).')
        vault.put('app:google', {'client_id': inner['client_id'], 'client_secret': inner['client_secret']})
    elif name == 'meta':
        app_id, secret_ = str(body.get('app_id', '')).strip(), str(body.get('app_secret', '')).strip()
        if not app_id.isdigit() or len(secret_) < 16:
            raise ApiError('Paste the App ID (only digits) and the App Secret from the Meta app\'s Basic settings.')
        vault.put('app:meta', {'app_id': app_id, 'app_secret': secret_})
    else:
        raise ApiError('Unknown app.', 404)
    return {'ok': True}


def delete_app(request, body):
    vault.delete('app:' + request.path_params['name'])
    return {'ok': True}


def connect(request, body):
    name = request.path_params['name']
    mod = login_module(name)
    url, data = mod.login_start(redirect(name))
    st = data['state']
    PENDING[st] = (name, data, time.time())
    for k in [k for k, v in PENDING.items() if time.time() - v[2] > 1800]:
        PENDING.pop(k, None)
    return {'url': url}


def login_module(name):
    if name == 'google':
        from .platforms import youtube
        return youtube
    if name == 'meta':
        from .platforms import meta
        return meta
    raise ApiError('Unknown login.', 404)


async def oauth_callback(request: Request, name=None):
    """Google / Meta send the browser back here after "Allow". Checked by the one-time `state` value (the
    cookie isn't sent on a return from another site, so it can't be the check)."""
    if not host_ok(request):
        return Response('wrong host', 403)
    name = name or request.path_params['name']
    q = dict(request.query_params)
    pending = PENDING.pop(q.get('state', ''), None)
    back = f"{paths.base_url()}/#/accounts"
    if not pending or pending[0] != name:
        return HTMLResponse(page_msg('This login link is old or was already used. Go back to PostKaro and press '
                                     'Connect again.', back), 400)
    if 'error' in q or 'code' not in q:
        why = q.get('error_description') or q.get('error_reason') or q.get('error') or 'no permission was given'
        return HTMLResponse(page_msg(f'The login was not completed ({why}).', back), 400)
    try:
        saved = await run_in_threadpool(login_module(name).login_finish, q, pending[1], redirect(name))
    except PlatformError as e:
        return HTMLResponse(page_msg(str(e), back), 400)
    names = ', '.join(f"{settings.NAMES[a['platform']]}: {a['name']}" for a in saved) or 'nothing'
    return HTMLResponse(page_msg(f'Connected ({names}). You can close this tab.', back, ok=True))


def page_msg(text, back, ok=False):
    from html import escape
    return (f'<!doctype html><meta charset="utf-8"><title>PostKaro</title><body style="font:16px system-ui;'
            f'max-width:560px;margin:15vh auto;padding:0 16px"><h2>{"✅" if ok else "⚠"} PostKaro</h2>'
            f'<p>{escape(text)}</p><p><a href="{escape(back)}">Back to PostKaro</a></p>'
            f'{"<script>setTimeout(()=>location.href=" + json.dumps(back) + ",1500)</script>" if ok else ""}')


def account_action(request, body):
    plat, aid, action = request.path_params['platform'], request.path_params['aid'], request.path_params['action']
    a = next((x for x in db.accounts(plat) if x['account_id'] == aid), None)
    if not a:
        raise ApiError('No such account.', 404)
    if action == 'check':
        return account_view(worker.check_account(a) or a)
    if action == 'activate':
        db.run('UPDATE accounts SET active=(account_id=?) WHERE platform=?', (aid, plat))
        return {'ok': True}
    if action == 'disconnect':
        mod = login_module('google' if plat == 'youtube' else 'meta')
        mod.disconnect(a)
        db.run('DELETE FROM accounts WHERE platform=? AND account_id=?', (plat, aid))
        return {'ok': True}
    raise ApiError('Unknown action.', 404)


# ---------- page, media, health ----------

async def index(request: Request):
    if not host_ok(request):
        return Response('wrong host', 403)
    st = request.query_params.get('state')
    if st and st in PENDING and PENDING[st][0] == 'google':     # Google's login coming back
        return await oauth_callback(request, 'google')
    if not authed(request):
        return HTMLResponse(page_msg('Open PostKaro with its link. In a terminal, in the PostKaro folder: '
                                     'python run.py open', paths.base_url()), 401)
    html = (paths.WEB / 'index.html').read_text(encoding='utf-8').replace('{{KEY}}', key()) \
        .replace('{{VERSION}}', __version__)
    r = HTMLResponse(html, headers={'Cache-Control': 'no-store'})
    r.set_cookie('pk', key(), httponly=True, samesite='strict', max_age=3600 * 24 * 365)
    if request.query_params.get('k'):                # drop the key from the address bar (the #/page stays)
        r = RedirectResponse('/', 303)
        r.set_cookie('pk', key(), httponly=True, samesite='strict', max_age=3600 * 24 * 365)
    return r


async def media(request: Request):
    if not host_ok(request) or not authed(request):
        return Response('no', 403)
    c = db.one('SELECT file FROM clips WHERE id=?', (int(request.path_params['id']),))
    if not c or not Path(c['file']).exists():
        return Response('not found', 404)
    return FileResponse(c['file'], media_type='video/mp4')


def make_thumb(cid):
    """A still frame for the video player (made once with ffmpeg, kept in the data folder)."""
    import shutil
    import subprocess
    c = db.one('SELECT file FROM clips WHERE id=?', (cid,))
    if not c or not Path(c['file']).exists() or not shutil.which('ffmpeg'):
        return None
    f = Path(c['file'])
    out = paths.data_dir() / 'thumbs' / f'{cid}-{int(f.stat().st_mtime)}.jpg'
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', str(f), '-frames:v', '1', '-vf', 'scale=360:-2',
                        '-q:v', '4', str(out)], capture_output=True, timeout=60)
    return out if out.exists() else None


async def thumb(request: Request):
    if not host_ok(request) or not authed(request):
        return Response('no', 403)
    out = await run_in_threadpool(make_thumb, int(request.path_params['id']))
    if not out:
        return Response('no still frame', 404)
    return FileResponse(out, media_type='image/jpeg', headers={'Cache-Control': 'max-age=86400'})


async def health(request: Request):
    return JSONResponse({'app': 'postkaro', 'version': __version__})


@asynccontextmanager
async def lifespan(app):
    global WORKER
    db.connect().close()
    WORKER = worker.Worker()
    WORKER.start()
    yield
    WORKER.stop()


def routes():
    R = Route
    return [
        R('/', index), R('/health', health), R('/media/clip/{id:int}', media), R('/media/thumb/{id:int}', thumb),
        R('/oauth/{name}', oauth_callback),
        R('/api/state', api(state)), R('/api/batches', api(batches)),
        R('/api/batch/{id:int}', api(batch)), R('/api/import', api(import_), methods=['POST']),
        R('/api/batch/{id:int}/plan', api(plan), methods=['POST']),
        R('/api/schedule', api(schedule), methods=['POST']),
        R('/api/post/{id:int}', api(edit_post), methods=['PATCH']),
        R('/api/post/{id:int}/{action}', api(post_action), methods=['POST']),
        R('/api/clip/{id:int}/remove', api(remove_clip), methods=['POST']),
        R('/api/clip/{id:int}/restore', api(remove_clip), methods=['POST']),
        R('/api/queue', api(queue)), R('/api/posted', api(posted)),
        R('/api/settings', api(save_settings), methods=['PUT']),
        R('/api/apps/{name}', api(save_app), methods=['POST']),
        R('/api/apps/{name}', api(delete_app), methods=['DELETE']),
        R('/api/connect/{name}', api(connect), methods=['POST']),
        R('/api/account/{platform}/{aid}/{action}', api(account_action), methods=['POST']),
        Mount('/static', StaticFiles(directory=paths.WEB), name='static'),
    ]


def make_app():
    return Starlette(routes=routes(), lifespan=lifespan)


def serve():
    import uvicorn
    info = paths.app_info()
    uvicorn.run(make_app(), host='127.0.0.1', port=int(info['port']), log_level='warning', log_config=None)
