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

from postkaro import covers, db, kit, paths, planner, rules, settings, vault, worker  # noqa: E402
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
        self.used = []                         # (step, account id) for each upload and poll

    def check(self, account):
        if self.login_broken:
            return {'ok': False, 'problem': 'login gone'}
        return {'ok': True, 'name': account['name'], 'expires': account.get('expires')}

    def upload(self, post, account, progress):
        self.calls.append(('upload', post['id'], post['when']))
        self.used.append(('upload', account['account_id']))
        if self.login_broken:
            raise PlatformError('login gone', login=True)
        if self.fail_upload:
            raise self.fail_upload.pop(0)
        progress(1.0)
        return {'id': f'R{post["id"]}'}

    def poll(self, post, account):
        self.calls.append(('poll', post['id']))
        self.used.append(('poll', account['account_id']))
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

    cover_result = 'ok'

    def apply_cover(self, post, account):
        c = post['clip']
        if not c.get('cover') or post['remote'].get('cover_v') == c.get('cover_v'):
            return None
        self.calls.append(('cover', post['id'], c['cover_v']))
        if self.cover_result == 'boom':
            raise RuntimeError('thumbnail bug')
        return {'cover_v': c['cover_v'], 'note': None if self.cover_result == 'ok' else self.cover_result}


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

    def test_spread_over_even_gaps(self):
        """10 clips in 10 minutes: the first when Schedule is pressed, then one a minute; 100 in a day: 14 min 24 s."""
        now = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
        times, gap = planner.spread(list(range(1, 11)), 10, now)
        self.assertEqual(gap, timedelta(minutes=1))
        self.assertIsNone(times[1])
        self.assertEqual([times[k] - now for k in (2, 3, 10)], [timedelta(minutes=m) for m in (1, 2, 9)])
        _, gap = planner.spread(list(range(100)), 24 * 60, now)
        self.assertEqual(gap, timedelta(minutes=14, seconds=24))

    def test_spread_over_too_short(self):
        with self.assertRaises(ValueError) as cm:
            planner.spread(list(range(200)), 10, datetime(2026, 11, 20, tzinfo=UTC))
        self.assertIn('at least 200 minutes', str(cm.exception))
        with self.assertRaises(ValueError):
            planner.spread([], 60, datetime(2026, 11, 20, tzinfo=UTC))

    def test_day_peak(self):
        self.assertEqual(planner.day_peak(100, timedelta(minutes=14, seconds=24)), 100)   # 100 in one day: fits
        self.assertEqual(planner.day_peak(150, timedelta(minutes=14, seconds=24)), 101)   # more would pass 100
        self.assertEqual(planner.day_peak(30, timedelta(hours=2)), 13)

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

    def test_picked_account_is_used(self):
        """A post can go to another channel than the default; every step then uses that channel."""
        self.connect_all()
        db.save_account('youtube', 'UC2', 'Second Channel', active=False)
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', now + timedelta(hours=3))
        db.update_post(pid, account='UC2')
        self.tick(now)
        self.tick(now + timedelta(minutes=1))
        self.assertEqual(self.fakes['youtube'].used, [('upload', 'UC2'), ('poll', 'UC2')])

    def test_default_account_is_kept_after_upload(self):
        """No pick: the default at upload time is recorded, and a later change of default does not move it."""
        self.connect_all()
        db.save_account('youtube', 'UC2', 'Second Channel', active=False)
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', now + timedelta(hours=3))
        self.tick(now)
        self.assertEqual(db.post(pid)['account'], 'UC1')
        db.save_account('youtube', 'UC2', 'Second Channel', active=True)     # the default changes
        self.tick(now + timedelta(minutes=1))
        self.assertEqual(self.fakes['youtube'].used, [('upload', 'UC1'), ('poll', 'UC1')])

    def test_picked_account_gone(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('youtube', now + timedelta(hours=3))
        db.update_post(pid, account='UC9')
        self.tick(now)
        p = db.post(pid)
        self.assertEqual(p['state'], 'failed')
        self.assertIn('no longer connected', p['error'])
        self.assertEqual(self.fakes['youtube'].used, [])            # never sent to the default instead

    def test_platform_fault_waits_longer_and_says_when(self):
        """A fault on the platform's side (patient) gets more tries, further apart, and the post says when."""
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        pid = self.schedule('instagram', now + timedelta(hours=5))
        self.fakes['instagram'].fail_upload = [PlatformError('Meta error 1363008.', retry=True, patient=True)
                                               for _ in range(len(worker.RETRY_PATIENT) + 1)]
        t = now
        for n in range(1, len(worker.RETRY_PATIENT) + 1):
            self.tick(t)
            p = db.post(pid)
            self.assertEqual((p['state'], p['attempts']), ('scheduled', n))
            self.assertEqual(db.parse(p['next_try']) - t, worker.RETRY_PATIENT[n - 1])
            self.assertIn('PostKaro tries again at', p['error'])
            t = db.parse(p['next_try'])
        self.tick(t)
        self.assertEqual(db.post(pid)['state'], 'failed')

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

    def test_spread_over_fills_even_times(self):
        """2 clips over 10 minutes: clip 1 has no time (goes when Schedule is pressed), clip 2 five minutes on,
        on every ticked platform; a clip with all platforms off is left out; nothing is scheduled yet."""
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        kit.import_kit(clipkaro_project(self.tmp))
        bid = db.one('SELECT id FROM batches')['id']
        before = db.now()
        r = self.c.post(f'/api/batch/{bid}/spread', json={'minutes': 10}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()['clips'], r.json()['gap'], r.json()['warnings']), (2, 300.0, []))
        rows = db.rows('SELECT p.when_utc, p.state, c.no FROM posts p JOIN clips c ON c.id=p.clip_id WHERE p.enabled=1')
        self.assertTrue(all(x['state'] == 'draft' for x in rows))
        self.assertTrue(all(x['when_utc'] is None for x in rows if x['no'] == 1))
        self.assertTrue(any(x['no'] == 2 for x in rows))
        for x in (x for x in rows if x['no'] == 2):
            self.assertAlmostEqual((db.parse(x['when_utc']) - before).total_seconds(), 300, delta=5)
        r = self.c.post(f'/api/batch/{bid}/spread', json={'minutes': 1}, headers=self.h)
        self.assertEqual(r.status_code, 400)                          # 2 clips need at least 2 minutes

    def test_platform_switch_for_every_clip(self):
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        kit.import_kit(clipkaro_project(self.tmp))
        bid = db.one('SELECT id FROM batches')['id']
        done = db.one("SELECT id FROM posts WHERE platform='facebook'")['id']
        db.update_post(done, state='scheduled')                       # already scheduled: left alone
        r = self.c.post(f'/api/batch/{bid}/platform', json={'platform': 'facebook', 'enabled': False}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        fb = db.rows("SELECT id, enabled FROM posts WHERE platform='facebook'")
        self.assertEqual({x['id']: x['enabled'] for x in fb if x['id'] != done}, {x['id']: 0 for x in fb if x['id'] != done})
        self.assertEqual(db.post(done)['enabled'], 1)
        self.assertTrue(all(x['enabled'] == 1 for x in db.rows("SELECT enabled FROM posts WHERE platform='youtube'")))
        self.c.post(f'/api/batch/{bid}/platform', json={'platform': 'facebook', 'enabled': True}, headers=self.h)
        self.assertTrue(all(x['enabled'] == 1 for x in db.rows("SELECT enabled FROM posts WHERE platform='facebook'")))
        self.assertEqual(self.c.post(f'/api/batch/{bid}/platform', json={'platform': 'tiktok', 'enabled': True},
                                     headers=self.h).status_code, 400)

    def test_post_now_ignores_the_set_time(self):
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        kit.import_kit(clipkaro_project(self.tmp))
        yt = db.one("SELECT id FROM posts WHERE platform='youtube'")['id']
        fb = db.one("SELECT id FROM posts WHERE platform='facebook'")['id']
        db.update_post(yt, when_utc=db.iso(db.now() + timedelta(hours=5)))
        db.update_post(fb, enabled=0)                                   # not ticked: stays a draft
        r = self.c.post('/api/schedule', json={'ids': [yt, fb], 'now': True}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()['scheduled'], r.json()['now']), (1, 1))
        p = db.post(yt)
        self.assertEqual((p['state'], p['when_utc']), ('scheduled', None))
        self.assertEqual(db.post(fb)['state'], 'draft')

    def test_pick_account_for_a_post(self):
        self.c.cookies.set('pk', self.key)
        self.connect_all()
        db.save_account('youtube', 'UC2', 'Second Channel', active=False)
        kit.import_kit(clipkaro_project(self.tmp))
        pid = db.one("SELECT id FROM posts WHERE platform='youtube'")['id']
        r = self.c.patch(f'/api/post/{pid}', json={'account': 'UC9'}, headers=self.h)
        self.assertEqual(r.status_code, 400)                          # not a connected account
        r = self.c.patch(f'/api/post/{pid}', json={'account': 'UC2'}, headers=self.h)
        self.assertEqual((r.status_code, r.json()['account']), (200, 'UC2'))
        r = self.c.patch(f'/api/post/{pid}', json={'account': ''}, headers=self.h)
        self.assertEqual(r.json()['account'], '')                      # back to following the default
        db.update_post(pid, state='scheduled')
        r = self.c.patch(f'/api/post/{pid}', json={'account': 'UC2'}, headers=self.h)
        self.assertEqual(r.status_code, 400)                          # only while it is a draft

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


def make_png(path):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=90x160', '-frames:v', '1', str(path)],
                   check=True)


@unittest.skipUnless(HAS_FFMPEG, 'needs ffmpeg')
class TestCovers(Base):
    def setUp(self):
        super().setUp()
        self.bid = kit.import_kit(clipkaro_project(self.tmp))
        self.cid = db.one('SELECT id FROM clips WHERE no=1')['id']

    def clip(self):
        return db.one('SELECT * FROM clips WHERE id=?', (self.cid,))

    def test_frame_and_image(self):
        covers.from_frame(self.cid, 2.5)
        c = self.clip()
        self.assertEqual((c['cover_kind'], c['cover_ms']), ('frame', 2500))
        self.assertTrue(Path(c['cover']).exists())
        self.assertIn('YouTube, Instagram and Facebook', covers.describe(c))
        old = c['cover']
        png = Path(self.tmp) / 'cover.png'
        make_png(png)
        covers.from_image(self.cid, png.read_bytes())
        c = self.clip()
        self.assertEqual((c['cover_kind'], c['cover_ms']), ('image', None))
        self.assertFalse(Path(old).exists())                       # the old file is gone
        self.assertTrue(Path(c['cover']).read_bytes().startswith(b'\xff\xd8\xff'))   # stored as JPEG
        self.assertIn('Instagram can only use a frame', covers.describe(c))
        with self.assertRaises(covers.CoverError):
            covers.from_image(self.cid, b'not an image at all')
        covers.remove(self.cid)
        self.assertIsNone(self.clip()['cover'])

    def test_worker_sets_cover_once_and_again_after_a_change(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        covers.from_frame(self.cid, 1)
        pid = db.one("SELECT id FROM posts WHERE clip_id=? AND platform='youtube'", (self.cid,))['id']
        db.update_post(pid, state='scheduled', when_utc=db.iso(now + timedelta(hours=5)))
        yt = self.fakes['youtube']
        for t in (now, now + timedelta(minutes=1), now + timedelta(minutes=2)):
            yt.now = t
            worker.tick(t)
        self.assertEqual(db.post(pid)['state'], 'waiting')
        self.assertEqual(sum(1 for c in yt.calls if c[0] == 'cover'), 1)  # set once, not every round
        covers.from_frame(self.cid, 3)                                    # changed before it went live
        yt.now = now + timedelta(minutes=3)
        worker.tick(yt.now)
        self.assertEqual(sum(1 for c in yt.calls if c[0] == 'cover'), 2)

    def test_cover_problem_is_a_note_never_a_failure(self):
        self.connect_all()
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        covers.from_frame(self.cid, 1)
        pid = db.one("SELECT id FROM posts WHERE clip_id=? AND platform='facebook'", (self.cid,))['id']
        db.update_post(pid, state='scheduled', when_utc=None)
        fb = self.fakes['facebook']
        fb.cover_result = 'boom'
        for t in (now, now + timedelta(seconds=20)):
            fb.now = t
            worker.tick(t)
        p = db.post(pid)
        self.assertEqual(p['state'], 'live')
        self.assertIn('thumbnail bug', p['note'])

    def test_instagram_gets_the_frame(self):
        from postkaro.platforms import meta
        sent = {}
        saved = (meta._call, meta._user, meta._rupload)
        meta._call = lambda method, url, **kw: sent.update(kw.get('data') or {}) or {'id': 'C1', 'uri': 'https://x'}
        meta._user = lambda account: {'token': 't'}
        meta._rupload = lambda *a: {'success': True}
        try:
            post = {'body': 'cap', 'clip': {'file': 'x.mp4', 'cover_kind': 'frame', 'cover_ms': 2500}}
            r = meta.Instagram().upload(post, {'account_id': 'IG1'}, lambda f: None)
            self.assertEqual(sent.get('thumb_offset'), '2500')
            self.assertIsNone(r['note'])
            sent.clear()
            post['clip'] = {'file': 'x.mp4', 'cover_kind': 'image', 'cover_ms': None}
            r = meta.Instagram().upload(post, {'account_id': 'IG1'}, lambda f: None)
            self.assertNotIn('thumb_offset', sent)
            self.assertIn('only use a frame', r['note'])
        finally:
            meta._call, meta._user, meta._rupload = saved

    def test_server_cover_actions(self):
        from starlette.testclient import TestClient
        from postkaro import server
        key, port = paths.app_info()['key'], paths.app_info()['port']
        c = TestClient(server.make_app(), base_url=f'http://127.0.0.1:{port}')
        c.cookies.set('pk', key)
        h = {'X-PostKaro': key}
        r = c.post(f'/api/clip/{self.cid}/cover-frame', json={'t': 1.2}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()['thumb'].startswith(f'/media/cover/{self.cid}?v='))
        self.assertEqual(c.get(r.json()['thumb']).headers['content-type'], 'image/jpeg')
        png = Path(self.tmp) / 'cover.png'
        make_png(png)
        r = c.put(f'/api/clip/{self.cid}/cover', content=png.read_bytes(), headers={**h, 'Content-Type': 'image/png'})
        self.assertEqual((r.status_code, r.json()['cover_kind']), (200, 'image'))
        r = c.put(f'/api/clip/{self.cid}/cover', content=b'hello', headers=h)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(c.put(f'/api/clip/{self.cid}/cover', content=png.read_bytes()).status_code, 401)   # no key header
        # an Instagram upload waiting for its time goes again with the new cover
        ig = db.one("SELECT id FROM posts WHERE clip_id=? AND platform='instagram'", (self.cid,))['id']
        db.update_post(ig, state='waiting', remote_id='C1', remote={'id': 'C1'})
        r = c.delete(f'/api/clip/{self.cid}/cover', headers=h)
        self.assertEqual((r.status_code, r.json()['cover']), (200, None))
        self.assertEqual((db.post(ig)['state'], db.post(ig)['remote_id']), ('scheduled', None))


class TestVault(unittest.TestCase):
    def test_roundtrip_and_encrypted(self):
        vault.put('x', {'token': 'secret-123'})
        self.assertEqual(vault.get('x'), {'token': 'secret-123'})
        self.assertNotIn(b'secret-123', (Path(HOME) / 'logins.enc').read_bytes())
        vault.delete('x')
        self.assertIsNone(vault.get('x'))


class TestMetaUploadErrors(unittest.TestCase):
    """Meta's video upload server (rupload) answers in its own shape; PostKaro must read it (no network)."""

    def fake(self, answers):
        class Answer:
            def __init__(self, status, body):
                self.status_code, self.body = status, body

            def json(self):
                return self.body

        class Requests:
            RequestException = Exception

            def __init__(self):
                self.calls = []

            def request(self, method, url, **kw):
                self.calls.append((method, url))
                return Answer(*answers.pop(0))
        return Requests()

    def run_with(self, answers, fn):
        from postkaro.platforms import meta
        old, req = meta._http, self.fake(answers)
        meta._http = lambda: req
        try:
            with self.assertRaises(PlatformError) as cm:
                fn(meta)
        finally:
            meta._http = old
        return cm.exception

    def test_upload_server_answer_is_read(self):
        e = self.run_with([(400, {'debug_info': {'retriable': False, 'type': 'ProcessingFailedError',
                                                 'message': 'Request processing failed'}})],
                          lambda meta: meta._call('POST', 'https://rupload.facebook.com/ig-api-upload/v27.0/1'))
        self.assertTrue(e.retry)
        self.assertIn('Request processing failed', str(e))
        self.assertNotIn('Meta said 400', str(e))

    def test_instagram_upload_fault_names_meta_error(self):
        vault.put('meta-user:U1', {'token': 't'})
        clip = Path(tempfile.mkdtemp(prefix='pk-ig-')) / 'clip.mp4'
        clip.write_bytes(b'\0' * 1000)
        answers = [(200, {'id': 'C1', 'uri': 'https://rupload.facebook.com/ig-api-upload/v27.0/C1'}),
                   (400, {'debug_info': {'retriable': False, 'type': 'ProcessingFailedError',
                                         'message': 'Request processing failed'}}),
                   (200, {'video_status': {'uploading_phase': {'status': 'error', 'errors': [
                       {'code': 1363008, 'message': 'OIL Error[FILE_NOT_FOUND: 6]: File not found.'}]}}})]
        account = {'account_id': 'IG1', 'extra': {'meta_user': 'U1'}}
        post = {'body': 'caption', 'clip': {'file': str(clip)}}
        e = self.run_with(answers, lambda meta: meta.Instagram().upload(post, account, lambda f: None))
        self.assertTrue(e.retry and e.patient)
        self.assertIn('1363008', str(e))
        shutil.rmtree(clip.parent, ignore_errors=True)


@unittest.skipUnless(HAS_FFMPEG, 'needs ffmpeg')
class TestPostNow(Base):
    """ClipKaro's live clipping: run.py post-now adds a project and posts every clip everywhere at once."""

    def run_cli(self, path, dry=False):
        import io
        from argparse import Namespace
        from contextlib import redirect_stdout
        from unittest import mock
        from postkaro import cli, service
        out = io.StringIO()
        with mock.patch.object(service, 'start_background', lambda: True), redirect_stdout(out):
            cli.cmd_post_now(Namespace(path=str(path), dry=dry))
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def test_dry_then_post_now(self):
        self.connect_all()
        proj = clipkaro_project(self.tmp, durations=(20, 30))
        res = self.run_cli(proj, dry=True)
        self.assertTrue(res['dry'])
        self.assertEqual(len(res['would_post']), 6)                    # 2 clips x 3 platforms
        self.assertFalse(db.rows("SELECT id FROM posts"))                # a test leaves nothing behind
        res = self.run_cli(proj)
        self.assertEqual(res['scheduled'], 6, res)
        rows = db.rows("SELECT state, when_utc FROM posts")
        self.assertTrue(all(r['state'] == 'scheduled' and r['when_utc'] is None for r in rows))

    def test_platform_not_connected_is_skipped(self):
        db.save_account('youtube', 'UC1', 'My Channel')                # only YouTube
        proj = clipkaro_project(self.tmp, durations=(20, 30))
        res = self.run_cli(proj)
        self.assertEqual(res['scheduled'], 2)
        self.assertEqual({s['platform'] for s in res['skipped']}, {'facebook', 'instagram'})


class TestWindowsAndMac(unittest.TestCase):
    """Install check for Windows and macOS: what this Linux laptop can still check."""

    def test_mac_finds_homebrews_ffmpeg(self):
        from unittest import mock
        import run
        full = '/opt/homebrew/opt/ffmpeg-full/bin'
        with mock.patch.object(sys, 'platform', 'darwin'), \
                mock.patch('os.path.isfile', lambda p: p == full + '/ffmpeg'), \
                mock.patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}):
            run.find_ffmpeg()
            self.assertTrue(os.environ['PATH'].startswith(full + os.pathsep))
        with mock.patch.object(sys, 'platform', 'darwin'), mock.patch('shutil.which', lambda n: None), \
                mock.patch('os.path.isfile', lambda p: p == '/opt/homebrew/bin/ffmpeg'), \
                mock.patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}):
            run.find_ffmpeg()                    # a login item doesn't see Homebrew's folder
            self.assertTrue(os.environ['PATH'].endswith(os.pathsep + '/opt/homebrew/bin'))

    def test_utf8_for_hindi_titles(self):
        from unittest import mock
        import run
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('PYTHONUTF8', None)
            run.utf8_output()
            self.assertEqual(os.environ['PYTHONUTF8'], '1')

    def test_login_start_on_each_system(self):
        from postkaro import service
        cmd = service.command(windowless=True)
        self.assertTrue(cmd[0].endswith(('python', 'pythonw.exe')))
        self.assertEqual(cmd[-2:], [str(paths.ROOT / 'run.py'), 'serve'])
        self.assertEqual(service._plist_path().name, 'com.postkaro.helper.plist')


if __name__ == '__main__':
    unittest.main()
