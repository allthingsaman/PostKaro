"""Instagram Reels and Facebook Page Reels through Meta's Graph API, using the user's own Meta app.

One Facebook login connects both: it gives a user key (used for Instagram; about 60 days, and Meta asks
for a fresh login every 90 days for Instagram access) and one key per Facebook Page (does not run out).
The Instagram account must be a Creator/Business account linked to the Page.

  Instagram  no scheduling on Meta's side: upload up to 23 h before the time, PostKaro publishes at the time
  Facebook   Page Reels (3-90 s), scheduled on Facebook's side (10 minutes to 29 days ahead)

Both upload straight from the file on this laptop (resumable upload to rupload.facebook.com).
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .. import db, vault
from .base import Platform, PlatformError

VERSION = 'v27.0'
GRAPH = f'https://graph.facebook.com/{VERSION}'
DIALOG = f'https://www.facebook.com/{VERSION}/dialog/oauth'
SCOPES = ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts', 'business_management',
          'instagram_basic', 'instagram_content_publish']
TIMEOUT = (30, 900)


def _app():
    app = vault.get('app:meta')
    if not app:
        raise PlatformError('Save your Meta app first (⚙ page, Instagram and Facebook).')
    return app


def _http():
    import requests
    return requests


def _call(method, url, **kw):
    """One Graph API call -> JSON, with Meta's errors turned into plain-word PlatformErrors."""
    requests = _http()
    url = url if url.startswith('http') else GRAPH + url
    try:
        r = requests.request(method, url, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise PlatformError(f'Could not reach Meta ({str(e)[:150]}).', retry=True)
    try:
        j = r.json()
    except ValueError:
        if r.status_code >= 500:
            raise PlatformError(f'Meta is busy ({r.status_code}).', retry=True)
        raise PlatformError(f'Meta answered something unexpected ({r.status_code}).')
    if isinstance(j, dict) and 'error' in j:
        raise _err(j['error'], r.status_code)
    if r.status_code >= 400:
        raise PlatformError(f'Meta said {r.status_code}.', retry=r.status_code >= 500)
    return j


def _err(e, status=0):
    code, sub = e.get('code'), e.get('error_subcode')
    msg = e.get('error_user_msg') or e.get('message') or 'unknown problem'
    if code == 190 or sub in (458, 459, 460, 463, 464, 467):
        return PlatformError(f'The Meta login no longer works ({msg}).', login=True)
    if code in (10, 200) or (isinstance(code, int) and 200 <= code < 300):
        return PlatformError(f'A permission is missing ({msg}). Reconnect and allow everything Meta asks.', login=True)
    if code == 9 and sub == 2207042:
        return PlatformError('Instagram\'s daily posting limit is reached. Try again tomorrow.')
    if code in (1, 2, 4, 17, 24, 32, 341, 368, 613, 9007) or e.get('is_transient') or status >= 500:
        return PlatformError(f'Meta is busy or the video is not ready yet ({msg}).', retry=True)
    if code == 25 and sub == 2207050:
        return PlatformError('Instagram has restricted this account. Check it in the Instagram app.')
    if sub == 2207026 or sub in (1363040, 1363127, 1363128, 1363129):
        return PlatformError(f'Meta refused the video file ({msg}).')
    return PlatformError(f'Meta said: {msg}')


def _ts(epoch):
    return db.iso(datetime.fromtimestamp(int(epoch), timezone.utc)) if epoch else None


def _debug(token, app):
    d = _call('GET', '/debug_token', params={'input_token': token,
                                              'access_token': f"{app['app_id']}|{app['app_secret']}"}).get('data', {})
    ends = [int(x) for x in (d.get('expires_at'), d.get('data_access_expires_at')) if x]
    return d, (_ts(min(ends)) if ends else None)


# ---------- login ----------

def login_start(redirect_uri):
    app = _app()
    state = secrets.token_urlsafe(24)
    url = DIALOG + '?' + urlencode({'client_id': app['app_id'], 'redirect_uri': redirect_uri, 'state': state,
                                    'response_type': 'code', 'scope': ','.join(SCOPES), 'auth_type': 'rerequest'})
    return url, {'state': state}


def login_finish(query, data, redirect_uri):
    app = _app()
    short = _call('GET', '/oauth/access_token', params={
        'client_id': app['app_id'], 'client_secret': app['app_secret'], 'redirect_uri': redirect_uri,
        'code': query['code']})['access_token']
    long = _call('GET', '/oauth/access_token', params={
        'grant_type': 'fb_exchange_token', 'client_id': app['app_id'], 'client_secret': app['app_secret'],
        'fb_exchange_token': short})
    token = long['access_token']
    me = _call('GET', '/me', params={'fields': 'id,name', 'access_token': token})
    info, ends = _debug(token, app)
    granted = set(info.get('scopes') or [])
    pages, url = [], '/me/accounts'
    params = {'fields': 'id,name,access_token,tasks,instagram_business_account{id,username,name}', 'limit': 100,
              'access_token': token}
    while url:
        j = _call('GET', url, params=params)
        pages += j.get('data', [])
        url, params = (j.get('paging') or {}).get('next'), None
    if not pages:
        raise PlatformError('No Facebook Page came back. Press Connect again and, on Meta\'s page, choose your '
                            'Page (and its Instagram account) when it asks which ones PostKaro may use.')
    vault.put(f"meta-user:{me['id']}", {'token': token, 'ends': ends})
    saved = []
    old_fb, old_ig = db.active_account('facebook'), db.active_account('instagram')
    keep_fb = old_fb['account_id'] if old_fb and any(p['id'] == old_fb['account_id'] for p in pages) else None
    igs = [p['instagram_business_account']['id'] for p in pages if p.get('instagram_business_account')]
    keep_ig = old_ig['account_id'] if old_ig and old_ig['account_id'] in igs else None
    first_fb = keep_fb or pages[0]['id']
    first_ig = keep_ig or (igs[0] if igs else None)
    for p in pages:
        vault.put(f"facebook:{p['id']}", {'token': p['access_token'], 'user': me['id']})
        db.save_account('facebook', p['id'], p['name'], extra={'meta_user': me['id']}, expires=None,
                        active=p['id'] == first_fb)
        saved.append({'platform': 'facebook', 'name': p['name']})
        ig = p.get('instagram_business_account')
        if ig:
            name = ig.get('username') or ig.get('name') or ig['id']
            db.save_account('instagram', ig['id'], name, extra={'username': ig.get('username'), 'page_id': p['id'],
                                                                 'meta_user': me['id']},
                            expires=ends, active=ig['id'] == first_ig)
            saved.append({'platform': 'instagram', 'name': name})
    missing = {'instagram_content_publish', 'pages_manage_posts'} - granted
    if granted and missing:
        raise PlatformError(f"Connected, but Meta did not give these permissions: {', '.join(sorted(missing))}. "
                            'Press Connect again and allow everything.')
    if not igs:
        saved.append({'platform': 'instagram', 'name': 'none found: link your Instagram (Creator/Business) to '
                                                       'your Facebook Page, then press Reconnect'})
    return saved


def disconnect(account):
    """Forget the login on this laptop and ask Meta to cancel the app's access for this person."""
    uid = account['extra'].get('meta_user')
    others = [a for a in db.accounts() if a['extra'].get('meta_user') == uid and
              (a['platform'], a['account_id']) != (account['platform'], account['account_id'])]
    vault.delete(f"{account['platform']}:{account['account_id']}")
    if uid and not others:                          # the last account of this login: cancel it completely
        rec = vault.get(f'meta-user:{uid}')
        if rec:
            try:
                _call('DELETE', '/me/permissions', params={'access_token': rec['token']})
            except PlatformError:
                pass
        vault.delete(f'meta-user:{uid}')


def _user(account):
    rec = vault.get(f"meta-user:{account['extra'].get('meta_user')}")
    if not rec:
        raise PlatformError('The Meta login is missing on this laptop.', login=True)
    return rec


def _page_token(account):
    rec = vault.get(f"facebook:{account['account_id']}")
    if not rec:
        raise PlatformError('The Facebook Page login is missing on this laptop.', login=True)
    return rec['token']


class _Reader:
    """The video file, read in pieces, reporting progress (keeps memory low for big files)."""

    def __init__(self, path, progress):
        self.f, self.size, self.done, self.progress = open(path, 'rb'), os.path.getsize(path), 0, progress

    def __len__(self):
        return self.size

    def read(self, n=-1):
        b = self.f.read(n if n and n > 0 else 1024 * 1024)
        self.done += len(b)
        self.progress(self.done / self.size if self.size else 1.0)
        return b

    def close(self):
        self.f.close()


def _rupload(url, token, path, progress):
    reader = _Reader(path, progress)
    try:
        j = _call('POST', url, data=reader, headers={'Authorization': f'OAuth {token}', 'offset': '0',
                                                      'file_size': str(reader.size)})
    finally:
        reader.close()
    if not j.get('success', True):
        raise PlatformError(f"The upload to Meta did not finish ({j.get('message', '')}).", retry=True)
    return j


# ---------- Instagram ----------

class Instagram(Platform):
    name = 'instagram'
    remote_schedule = False
    upload_ahead = timedelta(hours=23)           # an upload ("container") lives 24 h
    min_ahead = timedelta(0)

    def check(self, account):
        rec = _user(account)
        app = _app()
        try:
            j = _call('GET', f"/{account['account_id']}", params={'fields': 'username', 'access_token': rec['token']})
        except PlatformError as e:
            if e.login:
                return {'ok': False, 'problem': str(e)}
            raise
        ends = rec.get('ends')
        try:
            _, ends = _debug(rec['token'], app)
            if ends and db.parse(ends) - db.now() < timedelta(days=15):
                ends = self._extend(account, rec, app) or ends
            rec['ends'] = ends
            vault.put(f"meta-user:{account['extra']['meta_user']}", rec)
        except PlatformError:
            pass
        return {'ok': True, 'name': j.get('username') or account['name'], 'expires': ends}

    def _extend(self, account, rec, app):
        """Ask for a fresh 60-day key while the old one still works (Meta may or may not give one)."""
        try:
            j = _call('GET', '/oauth/access_token', params={
                'grant_type': 'fb_exchange_token', 'client_id': app['app_id'], 'client_secret': app['app_secret'],
                'fb_exchange_token': rec['token']})
        except PlatformError:
            return None
        if j.get('access_token'):
            _, ends = _debug(j['access_token'], app)
            if ends and (not rec.get('ends') or ends > rec['ends']):
                rec['token'] = j['access_token']
                return ends
        return None

    def upload(self, post, account, progress):
        token = _user(account)['token']
        c = _call('POST', f"/{account['account_id']}/media", data={
            'media_type': 'REELS', 'upload_type': 'resumable', 'caption': post['body'] or '',
            'access_token': token})
        uri = c.get('uri') or f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{c['id']}"
        _rupload(uri, token, post['clip']['file'], progress)
        return {'id': c['id']}

    def poll(self, post, account):
        token = _user(account)['token']
        if post['remote'].get('media_id'):
            return 'live', post['remote'].get('url') or self._permalink(post['remote']['media_id'], token)
        j = _call('GET', f"/{post['remote_id']}", params={'fields': 'status_code,status', 'access_token': token})
        code = j.get('status_code')
        if code == 'FINISHED':
            return 'ready', None
        if code == 'PUBLISHED':
            return 'live', None
        if code in ('ERROR', 'EXPIRED'):
            return 'failed', f"Instagram could not take the video: {j.get('status') or code}."
        return 'processing', None

    def publish(self, post, account):
        token = _user(account)['token']
        j = _call('POST', f"/{account['account_id']}/media_publish",
                  data={'creation_id': post['remote_id'], 'access_token': token})
        mid = j.get('id')
        return {'media_id': mid, 'url': self._permalink(mid, token) if mid else None}

    def _permalink(self, mid, token):
        try:
            return _call('GET', f'/{mid}', params={'fields': 'permalink', 'access_token': token}).get('permalink')
        except PlatformError:
            return None

    def update(self, post, account):
        return False                              # an upload can't be changed: upload again with the new text

    def cancel(self, post, account):
        return None                               # unpublished uploads expire by themselves after 24 h


# ---------- Facebook Page ----------

class Facebook(Platform):
    name = 'facebook'
    remote_schedule = True
    max_ahead = timedelta(days=29) - timedelta(hours=1)
    min_ahead = timedelta(minutes=12)             # Facebook schedules only more than 10 minutes ahead

    def check(self, account):
        try:
            j = _call('GET', f"/{account['account_id']}", params={'fields': 'name',
                                                                   'access_token': _page_token(account)})
        except PlatformError as e:
            if e.login:
                return {'ok': False, 'problem': str(e)}
            raise
        return {'ok': True, 'name': j.get('name') or account['name'], 'expires': None}

    def upload(self, post, account, progress):
        token, page = _page_token(account), account['account_id']
        s = _call('POST', f'/{page}/video_reels', data={'upload_phase': 'start', 'access_token': token})
        vid = s['video_id']
        url = s.get('upload_url') or f'https://rupload.facebook.com/video-upload/{VERSION}/{vid}'
        _rupload(url, token, post['clip']['file'], progress)
        when = post.get('when')
        data = {'upload_phase': 'finish', 'video_id': vid, 'description': post['body'] or '', 'access_token': token}
        if when:
            data.update(video_state='SCHEDULED', scheduled_publish_time=str(int(when.timestamp())))
        else:
            data['video_state'] = 'PUBLISHED'
        _call('POST', f'/{page}/video_reels', data=data)
        return {'id': vid, 'scheduled': bool(when)}

    def poll(self, post, account):
        j = _call('GET', f"/{post['remote_id']}", params={'fields': 'status,permalink_url',
                                                          'access_token': _page_token(account)})
        st = j.get('status') or {}
        vs = st.get('video_status')
        if vs in ('error', 'upload_failed', 'expired'):
            why = ((st.get('processing_phase') or {}).get('error') or {}).get('message') or vs
            return 'failed', f'Facebook could not take the video ({why}).'
        pub = (st.get('publishing_phase') or {}).get('publish_status')
        if pub == 'published':
            link = j.get('permalink_url') or ''
            return 'live', ('https://www.facebook.com' + link) if link.startswith('/') else (link or None)
        if pub == 'scheduled' or (vs == 'ready' and pub in (None, 'draft')):
            return 'ready', None
        if pub == 'error':
            return 'failed', 'Facebook could not publish the reel.'
        return 'processing', None

    def update(self, post, account):
        return False                              # remove and upload again with the new text or time

    def cancel(self, post, account):
        if not post.get('remote_id'):
            return
        try:
            _call('DELETE', f"/{post['remote_id']}", params={'access_token': _page_token(account)})
        except PlatformError as e:
            raise PlatformError(f'Could not remove the scheduled reel from Facebook ({e}). Delete it in Meta '
                                'Business Suite (Content -> Scheduled), then try again.')

    def publish(self, post, account):
        raise PlatformError('Facebook publishes by itself.')
