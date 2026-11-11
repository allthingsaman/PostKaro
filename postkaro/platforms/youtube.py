"""YouTube Shorts through the YouTube Data API v3, using the user's own Google app ("Desktop app" client).

A vertical video up to 3 minutes becomes a Short by itself (YouTube decides; there is no Shorts switch).
Scheduling happens on YouTube's side: the video is uploaded as private with `publishAt`, and YouTube makes
it public at that time, even when this laptop is off.

Login: Google's page in the browser, back to http://127.0.0.1:<port>/ (PKCE, offline access). The login
(with the refresh key) is kept in the vault as `youtube:<channel id>`.
"""
import json
import os
import time
from datetime import timedelta

from .. import db, settings, vault
from .base import Platform, PlatformError

SCOPES = ['https://www.googleapis.com/auth/youtube']
os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')   # Google may list the granted scope differently
TOKEN_URI = 'https://oauth2.googleapis.com/token'
CHUNK = 8 * 1024 * 1024


def _client_config():
    app = vault.get('app:google')
    if not app:
        raise PlatformError('Save your Google app first (Accounts page, YouTube).')
    return {'installed': {'client_id': app['client_id'], 'client_secret': app['client_secret'],
                          'auth_uri': 'https://accounts.google.com/o/oauth2/auth', 'token_uri': TOKEN_URI,
                          'redirect_uris': ['http://127.0.0.1', 'http://localhost']}}


# ---------- login ----------

def login_start(redirect_uri):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), SCOPES, redirect_uri=redirect_uri,
                                   autogenerate_code_verifier=True)
    url, state = flow.authorization_url(access_type='offline', prompt='consent select_account')
    return url, {'state': state, 'verifier': flow.code_verifier}


def login_finish(query, data, redirect_uri):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), SCOPES, redirect_uri=redirect_uri, state=data['state'],
                                   code_verifier=data['verifier'], autogenerate_code_verifier=False)
    try:
        flow.fetch_token(code=query['code'])
    except Exception as e:
        raise PlatformError(f'Google did not accept the login ({e}). Press Connect again.')
    creds = flow.credentials
    granted = set(creds.granted_scopes or creds.scopes or [])
    if granted and SCOPES[0] not in granted:
        raise PlatformError('YouTube access was not allowed. Press Connect again and tick the YouTube box on '
                            'Google\'s page.')
    if not creds.refresh_token:
        raise PlatformError('Google gave no lasting login. Press Connect again.')
    yt = _build(creds)
    try:
        r = yt.channels().list(part='snippet', mine=True).execute()
    except Exception as e:
        raise _err(e)
    if not r.get('items'):
        raise PlatformError('This Google account has no YouTube channel. Press Connect again and pick the account '
                            'that owns your channel.')
    ch = r['items'][0]
    cid, name = ch['id'], ch['snippet']['title']
    vault.put(f'youtube:{cid}', json.loads(creds.to_json()))
    db.save_account('youtube', cid, name, extra={'username': (ch['snippet'].get('customUrl') or '').lstrip('@')})
    return [{'platform': 'youtube', 'name': name}]


def disconnect(account):
    info = vault.get(f"youtube:{account['account_id']}")
    if info and info.get('refresh_token'):
        try:
            import requests
            requests.post('https://oauth2.googleapis.com/revoke', params={'token': info['refresh_token']},
                          headers={'content-type': 'application/x-www-form-urlencoded'}, timeout=20)
        except Exception:
            pass                                    # forget it locally anyway
    vault.delete(f"youtube:{account['account_id']}")


# ---------- helpers ----------

def _creds(account):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    info = vault.get(f"youtube:{account['account_id']}")
    if not info:
        raise PlatformError('The YouTube login is missing on this laptop.', login=True)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise PlatformError(f'The YouTube login no longer works ({_short(e)}).', login=True)
        except Exception as e:
            raise PlatformError(f'Could not reach Google ({_short(e)}).', retry=True)
        vault.put(f"youtube:{account['account_id']}", json.loads(creds.to_json()))
    return creds


def _build(creds):
    from googleapiclient.discovery import build
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def _short(e):
    return str(e).split('\n')[0][:200]


REASONS = {
    'quotaExceeded': ('This Google project used up today\'s YouTube allowance (100 uploads a day). It resets at '
                      'midnight US Pacific time.', False),
    'uploadLimitExceeded': ('Your channel reached YouTube\'s daily upload limit. Try again tomorrow.', False),
    'insufficientPermissions': ('The login lacks YouTube permission.', None),
    'youtubeSignupRequired': ('This Google account has no YouTube channel.', None),
    'invalidPublishAt': ('YouTube refused the posting time.', False),
    'invalidTitle': ('YouTube refused the title (empty, too long or with < >).', False),
    'invalidDescription': ('YouTube refused the description (too long or with < >).', False),
    'invalidTags': ('YouTube refused the tags.', False),
    'forbidden': ('YouTube refused this request.', False),
}


def _err(e):
    """A googleapiclient / network error -> PlatformError with a plain message."""
    from googleapiclient.errors import HttpError
    if isinstance(e, PlatformError):
        return e
    if isinstance(e, HttpError):
        status = int(getattr(e.resp, 'status', 0) or 0)
        reason = ''
        try:
            reason = json.loads(e.content)['error']['errors'][0]['reason']
        except Exception:
            pass
        if reason in REASONS:
            msg, retry = REASONS[reason]
            return PlatformError(msg, retry=bool(retry), login=retry is None)
        if status == 401:
            return PlatformError('The YouTube login no longer works.', login=True)
        if status >= 500 or status == 429:
            return PlatformError(f'YouTube is busy ({status}).', retry=True)
        return PlatformError(f'YouTube said: {reason or status} {_short(e)}')
    return PlatformError(f'Could not reach YouTube ({_short(e)}).', retry=True)


# ---------- the plug-in ----------

class YouTube(Platform):
    name = 'youtube'
    remote_schedule = True
    upload_ahead = None
    max_ahead = None
    min_ahead = timedelta(minutes=2)

    def check(self, account):
        try:
            yt = _build(_creds(account))
            r = yt.channels().list(part='snippet', mine=True).execute()
        except PlatformError as e:
            if e.login:
                return {'ok': False, 'problem': str(e)}
            raise
        except Exception as e:
            err = _err(e)
            if err.login:
                return {'ok': False, 'problem': str(err)}
            raise err
        if not r.get('items'):
            return {'ok': False, 'problem': 'The channel is gone from this Google account.'}
        return {'ok': True, 'name': r['items'][0]['snippet']['title'], 'expires': None}

    def upload(self, post, account, progress):
        from googleapiclient.http import MediaFileUpload
        s = settings.load()
        when = post.get('when')
        vis = s.get('youtube_visibility') or 'public'
        status = {'selfDeclaredMadeForKids': bool(s.get('youtube_made_for_kids')), 'containsSyntheticMedia': False}
        if when and vis == 'public':
            status.update(privacyStatus='private', publishAt=db.iso(when))
        else:
            status['privacyStatus'] = vis
        body = {'snippet': {'title': post['title'], 'description': post['body'] or '',
                            'categoryId': str(s.get('youtube_category') or '24')}, 'status': status}
        yt = _build(_creds(account))
        req = yt.videos().insert(part='snippet,status', body=body,
                                 notifySubscribers=bool(s.get('youtube_notify_subscribers', True)),
                                 media_body=MediaFileUpload(post['clip']['file'], mimetype='video/mp4',
                                                            chunksize=CHUNK, resumable=True))
        resp, tries = None, 0
        while resp is None:
            try:
                st, resp = req.next_chunk(num_retries=3)
                if st:
                    progress(st.progress())
            except Exception as e:
                err = _err(e)
                tries += 1
                if not err.retry or tries > 5:
                    raise err
                time.sleep(min(30, 2 ** tries))
        progress(1.0)
        return {'id': resp['id'], 'visibility': vis, 'scheduled': bool(when and vis == 'public')}

    def poll(self, post, account):
        vid = post['remote_id']
        try:
            r = _build(_creds(account)).videos().list(part='status,processingDetails', id=vid).execute()
        except Exception as e:
            raise _err(e)
        if not r.get('items'):
            return 'failed', 'The video is no longer on YouTube (deleted?).'
        item = r['items'][0]
        st = item.get('status', {})
        up = st.get('uploadStatus')
        if up == 'failed':
            return 'failed', f"YouTube could not process the video ({st.get('failureReason', 'unknown reason')})."
        if up == 'rejected':
            return 'failed', f"YouTube rejected the video ({st.get('rejectionReason', 'unknown reason')})."
        if up == 'deleted':
            return 'failed', 'The video was deleted on YouTube.'
        proc = (item.get('processingDetails') or {}).get('processingStatus')
        if proc in ('failed', 'terminated'):
            return 'failed', 'YouTube could not process the video.'
        if up != 'processed':
            return 'processing', None
        expected = post['remote'].get('visibility', 'public')
        if st.get('privacyStatus') == expected and not (expected == 'public' and st.get('publishAt')):
            return 'live', f'https://www.youtube.com/shorts/{vid}'
        return 'ready', None

    def update(self, post, account):
        """New title, description or time for an uploaded, not yet public video."""
        vid = post['remote_id']
        yt = _build(_creds(account))
        try:
            item = yt.videos().list(part='snippet,status', id=vid).execute()['items'][0]
        except (IndexError, KeyError):
            return False
        except Exception as e:
            raise _err(e)
        sn, st = item['snippet'], item['status']
        snippet = {'title': post['title'], 'description': post['body'] or '', 'categoryId': sn.get('categoryId', '24')}
        for k in ('tags', 'defaultLanguage', 'defaultAudioLanguage'):
            if sn.get(k):
                snippet[k] = sn[k]
        status = {k: st[k] for k in ('embeddable', 'license', 'publicStatsViewable') if k in st}
        vis = post['remote'].get('visibility', 'public')
        when = post.get('when')
        if vis == 'public' and when and when > db.now() + timedelta(minutes=2):
            status.update(privacyStatus='private', publishAt=db.iso(when))
        else:
            status['privacyStatus'] = vis               # no future time: publish now
        try:
            yt.videos().update(part='snippet,status', body={'id': vid, 'snippet': snippet, 'status': status}).execute()
        except Exception as e:
            raise _err(e)
        return True

    def cancel(self, post, account):
        if not post.get('remote_id'):
            return
        from googleapiclient.errors import HttpError
        try:
            _build(_creds(account)).videos().delete(id=post['remote_id']).execute()
        except HttpError as e:
            if int(getattr(e.resp, 'status', 0) or 0) != 404:
                raise _err(e)
        except Exception as e:
            raise _err(e)

    def publish(self, post, account):
        raise PlatformError('YouTube publishes by itself.')

    def apply_cover(self, post, account):
        """The clip's custom thumbnail (after processing, which poll() has seen by then). 50 quota units."""
        from pathlib import Path
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        c = post['clip']
        if not c.get('cover') or post['remote'].get('cover_v') == c.get('cover_v') or not Path(c['cover']).exists():
            return None
        try:
            _build(_creds(account)).thumbnails().set(
                videoId=post['remote_id'], media_body=MediaFileUpload(c['cover'], mimetype='image/jpeg')).execute()
        except HttpError as e:
            status = int(getattr(e.resp, 'status', 0) or 0)
            if status >= 500 or status == 429:
                raise PlatformError(f'YouTube is busy ({status}).', retry=True)
            why = ('your channel needs custom thumbnails switched on: verify it at youtube.com/verify, then set the '
                   'thumbnail again') if status == 403 else _short(e)
            return {'cover_v': c['cover_v'], 'note': f'Custom thumbnail not set on YouTube: {why}.'}
        return {'cover_v': c['cover_v'], 'note': None}
