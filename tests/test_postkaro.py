"""PostKaro tests. No real accounts: the platforms are fakes, logins go to a throwaway folder.

    .venv/bin/python -m unittest discover -s tests -v        (Windows: .venv\\Scripts\\python)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = tempfile.mkdtemp(prefix='postkaro-test-')
os.environ.update(POSTKARO_HOME=HOME, POSTKARO_VAULT='file', POSTKARO_NO_NOTIFY='1')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from postkaro import db, kit, paths, planner, rules, settings, vault, worker  # noqa: E402
from postkaro import platforms  # noqa: E402
from postkaro.platforms.base import Platform, PlatformError  # noqa: E402

UTC = timezone.utc
HAS_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def make_mp4(path, seconds):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=blue:s=108x192:d={seconds}',
                    '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono', '-t', str(seconds), '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def reset_db():
    for f in Path(HOME).glob('postkaro.db*'):
        f.unlink()
    (Path(HOME) / 'settings.json').unlink(missing_ok=True)


def clipkaro_project(root, durations=(5, 100), channel='Some Podcast'):
    """A small ClipKaro project folder: clips.json, project.json, edited/NN-*.mp4."""
    p = Path(root) / 'my-video-abc123'
    (p / 'edited').mkdir(parents=True)
    clips = []
    for i, d in enumerate(durations, 1):
        make_mp4(p / 'edited' / f'{i:02d}-clip-{i}.mp4', d)
        clips.append({'id': i, 'title': f'Clip number {i}', 'ranges': [[10.0 * i, 10.0 * i + d]],
                      'caption': f'Kya baat hai {i} #one #two #three #four #five #six #Shorts', 'clip_score': 5 + i,
                      'honesty_note': 'one judge objected' if i == 2 else None})
    (p / 'clips.json').write_text(json.dumps({'clips': clips}))
    (p / 'project.json').write_text(json.dumps({'kind': 'youtube', 'source': 'https://youtu.be/abc123',
                                                'title': 'My long video', 'channel': channel, 'slug': p.name}))
    return p


class Fake(Platform):
    """remote=True behaves like YouTube/Facebook, remote=False like Instagram."""

    def __init__(self, name, remote):
        self.name, self.remote_schedule = name, remote
        self.upload_ahead = None if remote else timedelta(hours=23)
        self.max_ahead = None
        self.min_ahead = timedelta(0)
        self.calls, self.fail_upload, self.login_broken, self.now = [], [], False, None
        self.updatable = True

    def check(self, account):
        if self.login_broken:
            return {'ok': False, 'problem': 'login gone'}
        return {'ok': True, 'name': account['name'], 'expires': account.get('expires')}

    def upload(self, post, account, progress):
        self.calls.append(('upload', post['id'], post['when']))
        if self.login_broken:
            raise PlatformError('login gone', login=True)
        if self.fail_upload:
            raise self.fail_upload.pop(0)
        progress(1.0)
        return {'id': f'R{post["id"]}'}

    def poll(self, post, account):
        self.calls.append(('poll', post['id']))
        when = post['when']
        if self.remote_schedule and (when is None or self.now >= when):
            return 'live', f'https://example/{post["remote_id"]}'
        return 'ready', None

    def publish(self, post, account):
        self.calls.append(('publish', post['id']))
        return {'url': f'https://example/ig/{post["remote_id"]}'}

    def update(self, post, account):
        self.calls.append(('update', post['id']))
        return self.updatable

    def cancel(self, post, account):
        self.calls.append(('cancel', post['id']))


class Base(unittest.TestCase):
    def setUp(self):
        reset_db()
        self.tmp = tempfile.mkdtemp(prefix='pk-proj-')
        self.fakes = {'youtube': Fake('youtube', True), 'facebook': Fake('facebook', True),
                      'instagram': Fake('instagram', False)}
        platforms.OVERRIDE.clear()
        platforms.OVERRIDE.update(self.fakes)
        worker.progress.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        platforms.OVERRIDE.clear()

    def connect_all(self):
        db.save_account('youtube', 'UC1', 'My Channel')
        db.save_account('facebook', 'P1', 'My Page', extra={'meta_user': 'U1'})
        db.save_account('instagram', 'IG1', 'myhandle', extra={'meta_user': 'U1', 'username': 'myhandle'})


class TestRules(unittest.TestCase):
    def test_hashtags_and_drop(self):
        text = 'Ramayan ka budget #ramayan #बॉलीवुड #budget, #Shorts!'
        self.assertEqual(rules.hashtags(text), ['#ramayan', '#बॉलीवुड', '#budget', '#Shorts'])
        self.assertEqual(rules.drop_tags(text), 'Ramayan ka budget #ramayan #बॉलीवुड #budget, !')
        self.assertEqual(rules.hashtags(rules.drop_tags('#a #b #c #d #e #f #g', keep=5)), ['#a', '#b', '#c', '#d', '#e'])
        self.assertEqual(rules.hashtags('price is 5#3 and C# rocks'), [])

    def test_checks(self):
        err, _ = rules.check('youtube', 'x' * 101, '', {'duration': 30})
        self.assertTrue(any('101' in e for e in err))
        err, warn = rules.check('youtube', 'ok', 'd', {'duration': 200})
        self.assertFalse(err)
        self.assertTrue(any('normal video' in w for w in warn))
        err, _ = rules.check('youtube', 'a <b>', '', {'duration': 30})
        self.assertTrue(any('<' in e for e in err))
        err, _ = rules.check('youtube', 'ok', 'है' * 1700, {'duration': 30})
        self.assertTrue(any('bytes' in e for e in err))
        err, _ = rules.check('instagram', '', '#a #b #c #d #e #f', {'duration': 30})
        self.assertTrue(any('6 hashtags' in e for e in err))
        err, _ = rules.check('facebook', '', 'hi', {'duration': 95})
        self.assertTrue(any('90 seconds' in e for e in err))
        _, warn = rules.check('facebook', '', 'hi', {'duration': 30}, own=False, channel='X')
        self.assertTrue(any('Not your video (X)' in w for w in warn))


@unittest.skipUnless(HAS_FFMPEG, 'needs ffmpeg to make test videos')
class TestKit(Base):
    def test_import_clipkaro_folder(self):
        proj = clipkaro_project(self.tmp)
        bid = kit.import_kit(proj)
        clips = db.rows('SELECT * FROM clips WHERE batch_id=? ORDER BY no', (bid,))
        self.assertEqual(len(clips), 2)
        self.assertAlmostEqual(clips[0]['duration'], 5, delta=0.2)
        self.assertEqual(clips[1]['note'], 'one judge objected')
        posts = {(p['clip_id'], p['platform']): p for p in db.rows('SELECT * FROM posts')}
        self.assertEqual(len(posts), 6)
        yt = posts[(clips[0]['id'], 'youtube')]
        self.assertEqual(yt['title'], 'Clip number 1')
        self.assertIn('Full video: https://youtu.be/abc123', yt['body'])
        ig = posts[(clips[0]['id'], 'instagram')]
        self.assertEqual(len(rules.hashtags(ig['body'])), 5)
        self.assertNotIn('#Shorts', ig['body'])
        self.assertNotIn('#Shorts', posts[(clips[0]['id'], 'facebook')]['body'])
        self.assertFalse(posts[(clips[1]['id'], 'facebook')]['enabled'])      # 100 s: too long for a Reel
        self.assertTrue(posts[(clips[1]['id'], 'youtube')]['enabled'])
        b = db.one('SELECT * FROM batches WHERE id=?', (bid,))
        self.assertFalse(kit.is_own(b))
        settings.save({'my_channels': ['some podcast']})
        self.assertTrue(kit.is_own(b))

    def test_reimport_keeps_edits(self):
        proj = clipkaro_project(self.tmp)
        bid = kit.import_kit(proj)
        pid = db.one("SELECT id FROM posts WHERE platform='youtube'")['id']
        db.update_post(pid, title='My own title')
        self.assertEqual(kit.import_kit(proj), bid)
        self.assertEqual(db.post(pid)['title'], 'My own title')
        self.assertEqual(db.one('SELECT COUNT(*) n FROM posts')['n'], 6)

    def test_post_kit_file(self):
        d = Path(self.tmp) / 'kit'
        d.mkdir()
        make_mp4(d / 'a.mp4', 4)
        (d / 'post.json').write_text(json.dumps({'postkit': 1, 'project': 'p', 'title': 'T', 'source': {
            'channel': 'Me', 'url': 'https://youtu.be/x'}, 'clips': [{
                'id': 1, 'file': 'a.mp4', 'title': 'Hello', 'caption': 'cap #a', 'clip_score': 7.1, 'text': {
                    'youtube': {'title': 'YT title', 'description': 'YT desc'},
                    'instagram': {'caption': 'IG cap'}, 'facebook': {'caption': 'FB cap'}}}]}))
        bid = kit.import_kit(d)
        got = {p['platform']: p for p in db.rows('SELECT * FROM posts')}
        self.assertEqual((got['youtube']['title'], got['youtube']['body']), ('YT title', 'YT desc'))
        self.assertEqual(got['instagram']['body'], 'IG cap')
        self.assertEqual(got['facebook']['body'], 'FB cap')
        self.assertTrue(bid)
        (d / 'post.json').write_text(json.dumps({'postkit': 99, 'clips': []}))
        with self.assertRaises(ValueError):
            kit.load(d)


class TestPlanner(unittest.TestCase):
    def setUp(self):
        reset_db()

    def test_spread_best_first(self):
        s = settings.load()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)       # 15:30 in India
        posts = [{'id': i, 'platform': 'youtube', 'score': sc, 'no': i} for i, sc in ((1, 5.0), (2, 7.0), (3, 6.0))]
        posts += [{'id': 10 + i, 'platform': 'instagram', 'score': 5.0, 'no': i} for i in (1, 2)]
        out = planner.plan(posts, s, now=now)
        ist = timezone(timedelta(hours=5, minutes=30))
        local = {k: v.astimezone(ist).strftime('%d %H:%M') for k, v in out.items()}
        self.assertEqual([local[2], local[3], local[1]], ['11 18:00', '12 18:00', '13 18:00'])
        self.assertEqual([local[11], local[12]], ['11 19:00', '12 19:00'])

    def test_taken_and_per_day(self):
        s = settings.load()
        s['per_day'] = 2
        now = datetime(2026, 11, 11, 13, 0, tzinfo=UTC)       # 18:30 IST: today's 18:00 has passed
        taken = {'youtube': [datetime(2026, 11, 11, 15, 30, tzinfo=UTC)]}     # 21:00 IST today is taken
        out = planner.plan([{'id': 1, 'platform': 'youtube', 'score': 1, 'no': 1},
                            {'id': 2, 'platform': 'youtube', 'score': 1, 'no': 2}], s, now=now, taken=taken)
        ist = timezone(timedelta(hours=5, minutes=30))
        self.assertEqual(sorted(v.astimezone(ist).strftime('%d %H:%M') for v in out.values()),
                         ['12 18:00', '12 21:00'])


@unittest.skipUnless(HAS_FFMPEG, 'needs ffmpeg to make test videos')
class TestWorker(Base):
    def schedule(self, platform, when, clip_no=1):
        proj = clipkaro_project(self.tmp) if not db.one('SELECT id FROM batches') else None
        if proj:
            kit.import_kit(proj)
        p = db.one('SELECT p.id FROM posts p JOIN clips c ON c.id=p.clip_id WHERE p.platform=? AND c.no=?',
                   (platform, clip_no))
        db.update_post(p['id'], state='scheduled', when_utc=db.iso(when) if when else None)
        return p['id']

    def tick(self, now):
        for f in self.fakes.values():
            f.now = now
        worker.tick(now)

    def test_youtube_like_scheduled(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', now + timedelta(hours=3))
        self.tick(now)
        self.assertEqual(db.post(pid)['state'], 'processing')
        self.assertEqual(self.fakes['youtube'].calls[0][0], 'upload')
        self.assertEqual(self.fakes['youtube'].calls[0][2], now + timedelta(hours=3))   # the time goes along
        self.tick(now + timedelta(minutes=1))
        self.assertEqual(db.post(pid)['state'], 'waiting')
        self.tick(now + timedelta(hours=2))
        self.assertEqual(db.post(pid)['state'], 'waiting')
        self.tick(now + timedelta(hours=3, minutes=1))
        p = db.post(pid)
        self.assertEqual((p['state'], p['url']), ('live', 'https://example/R%d' % pid))

    def test_post_now(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('facebook', None)
        self.tick(now)
        self.tick(now + timedelta(seconds=20))
        self.assertEqual(db.post(pid)['state'], 'live')

    def test_instagram_like_waits_then_publishes(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        when = now + timedelta(hours=30)
        pid = self.schedule('instagram', when)
        self.tick(now)
        self.assertEqual(db.post(pid)['state'], 'scheduled')          # more than 23 h ahead: not yet
        self.assertEqual(self.fakes['instagram'].calls, [])
        self.tick(now + timedelta(hours=8))                           # 22 h before: upload
        self.tick(now + timedelta(hours=8, minutes=1))
        self.assertEqual(db.post(pid)['state'], 'waiting')
        self.tick(when - timedelta(minutes=1))
        self.assertEqual(db.post(pid)['state'], 'waiting')
        self.tick(when + timedelta(seconds=30))
        p = db.post(pid)
        self.assertEqual((p['state'], p['url']), ('live', f'https://example/ig/R{pid}'))
        self.assertIn(('publish', pid), self.fakes['instagram'].calls)

    def test_laptop_off_ask_or_post(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('instagram', now - timedelta(hours=2))
        self.tick(now)
        self.assertEqual(db.post(pid)['state'], 'missed')
        settings.save({'late': 'post'})
        db.update_post(pid, state='scheduled')
        self.tick(now)
        self.tick(now + timedelta(seconds=20))
        self.assertEqual(db.post(pid)['state'], 'live')

    def test_retry_then_fail(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', now + timedelta(hours=5))
        yt = self.fakes['youtube']
        yt.fail_upload = [PlatformError('net down', retry=True) for _ in range(4)]
        t = now
        for n in range(1, 4):
            self.tick(t)
            p = db.post(pid)
            self.assertEqual((p['state'], p['attempts']), ('scheduled', n))
            self.tick(t + timedelta(seconds=30))                     # too early for the next try
            self.assertEqual(db.post(pid)['attempts'], n)
            t = db.parse(p['next_try'])
        self.tick(t)
        p = db.post(pid)
        self.assertEqual(p['state'], 'failed')
        self.assertIn('net down', p['error'])

    def test_login_broken(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', None)
        self.fakes['youtube'].login_broken = True
        self.tick(now)
        p = db.post(pid)
        self.assertEqual(p['state'], 'failed')
        self.assertIn('Reconnect', p['error'])
        self.assertEqual(db.active_account('youtube')['status'], 'broken')

    def test_not_connected(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', None)
        self.tick(now)
        self.assertIn('not connected', db.post(pid)['error'])

    def test_expiry_warning(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        db.run("UPDATE accounts SET expires=?, checked=NULL WHERE platform='instagram'",
               (db.iso(now + timedelta(days=5)),))
        worker.health(now)
        a = db.active_account('instagram')
        self.assertEqual(a['status'], 'warn')
        self.assertIn('reconnect', a['problem'])
        self.assertEqual(a['extra']['warned'], 7)
        self.fakes['instagram'].login_broken = True
        worker.health(now, force=True)
        self.assertEqual(db.active_account('instagram')['status'], 'broken')


@unittest.skipUnless(HAS_FFMPEG, 'needs ffmpeg to make test videos')
class TestServer(Base):
    def setUp(self):
        super().setUp()
        from starlette.testclient import TestClient
        from postkaro import server
        self.server = server
        self.port = paths.app_info()['port']
        self.key = paths.app_info()['key']
        self.c = TestClient(server.make_app(), base_url=f'http://127.0.0.1:{self.port}')
        self.h = {'X-PostKaro': self.key}

    def test_access_rules(self):
        r = self.c.get('/api/state')
        self.assertEqual(r.status_code, 401)
        bad = self.c.get('/api/state', headers={'host': 'evil.example:8765'})
        self.assertEqual(bad.status_code, 403)
        r = self.c.get(f'/?k={self.key}', follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn('pk=', r.headers['set-cookie'])
        self.assertIn('samesite=strict', r.headers['set-cookie'].lower())
        self.c.cookies.set('pk', self.key)
        self.assertEqual(self.c.get('/api/state').status_code, 200)
        page = self.c.get('/')
        self.assertIn(self.key, page.text)                         # the page carries the key for its calls
        self.assertEqual(self.c.post('/api/import', json={'path': 'x'}).status_code, 401)    # no header
        r = self.c.post('/api/import', json={'path': 'x'}, headers={**self.h, 'Origin': 'https://evil.example'})
        self.assertEqual(r.status_code, 401)
        r = self.c.post('/api/import', json={'path': 'x'}, headers={**self.h, 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(r.status_code, 401)

    def test_flow(self):
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        proj = clipkaro_project(self.tmp)
        r = self.c.post('/api/import', json={'path': str(proj)}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        bid = r.json()['id']
        b = self.c.get(f'/api/batch/{bid}').json()
        self.assertEqual(len(b['clips']), 2)
        self.assertFalse(b['own'])
        self.assertTrue(any('Honesty note' in w for w in b['clips'][1]['warnings']))
        ig = b['clips'][0]['posts']['instagram']
        r = self.c.patch(f"/api/post/{ig['id']}", json={'body': '#a #b #c #d #e #f'}, headers=self.h)
        self.assertTrue(any('6 hashtags' in e for e in r.json()['errors']))
        b = self.c.post(f'/api/batch/{bid}/plan', json={}, headers=self.h).json()
        whens = [p['when'] for c in b['clips'] for p in c['posts'].values() if p['enabled']]
        self.assertTrue(all(whens))
        r = self.c.post('/api/schedule', json={'batch': bid}, headers=self.h).json()
        self.assertEqual(r['scheduled'], 4)                       # 5 ticked, the 6-hashtag caption is skipped
        self.assertEqual(r['skipped'][0]['platform'], 'instagram')
        q = self.c.get('/api/queue').json()
        self.assertEqual(len(q), 4)
        yt = b['clips'][0]['posts']['youtube']
        r = self.c.post(f"/api/post/{yt['id']}/cancel", json={}, headers=self.h)
        self.assertEqual(r.json()['state'], 'cancelled')
        r = self.c.post(f"/api/post/{yt['id']}/draft", json={}, headers=self.h)
        self.assertEqual(r.json()['state'], 'draft')
        # media with a Range request (the video player needs it)
        cid = b['clips'][0]['id']
        r = self.c.get(f'/media/clip/{cid}', headers={'Range': 'bytes=0-99'})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(len(r.content), 100)

    def test_edit_after_upload_reuploads(self):
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        kit.import_kit(clipkaro_project(self.tmp))
        pid = db.one("SELECT id FROM posts WHERE platform='facebook'")['id']
        db.update_post(pid, state='waiting', remote_id='R9', when_utc=db.iso(db.now() + timedelta(days=1)))
        self.fakes['facebook'].updatable = False
        r = self.c.patch(f'/api/post/{pid}', json={'body': 'new words'}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        p = db.post(pid)
        self.assertEqual((p['state'], p['remote_id'], p['body']), ('scheduled', None, 'new words'))
        self.assertIn(('cancel', pid), self.fakes['facebook'].calls)

    def test_settings_and_apps(self):
        self.c.cookies.set('pk', self.key)
        r = self.c.put('/api/settings', json={'timezone': 'Not/AZone'}, headers=self.h)
        self.assertEqual(r.status_code, 400)
        settings.save({'timezone': 'Asia/Kolkata'})
        r = self.c.post('/api/apps/google', json={'client': '{"web": {"client_id": "a", "client_secret": "b"}}'},
                        headers=self.h)
        self.assertIn('Desktop app', r.json()['error'])
        r = self.c.post('/api/apps/google', json={'client': {'installed': {'client_id': 'a', 'client_secret': 'b'}}},
                        headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(vault.get('app:google')['client_id'], 'a')
        self.assertTrue(self.c.get('/api/state').json()['apps']['google'])
        self.assertNotIn('"b"', self.c.get('/api/state').text)    # secrets never go to the page


class TestVault(unittest.TestCase):
    def test_roundtrip_and_encrypted(self):
        vault.put('x', {'token': 'secret-123'})
        self.assertEqual(vault.get('x'), {'token': 'secret-123'})
        self.assertNotIn(b'secret-123', (Path(HOME) / 'logins.enc').read_bytes())
        vault.delete('x')
        self.assertIsNone(vault.get('x'))


if __name__ == '__main__':
    unittest.main()
