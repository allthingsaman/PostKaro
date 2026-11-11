"""Reading what to post, and adding it to the queue as drafts.

PostKaro reads either
  - a post kit: `post.json` (docs/post-kit.md; ClipKaro writes one after editing), or
  - a ClipKaro project folder without one (output/<project>/: clips.json, project.json, edited/ or clips/),
    so older ClipKaro runs can be posted too.

Text for each platform comes from the kit when it has some, otherwise from the clip's title and caption:
  YouTube    title = clip title; description = caption (+ "Full video: <link>")
  Instagram  caption = caption without #shorts, at most 5 hashtags
  Facebook   caption = caption without #shorts
"""
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

from . import db, rules, settings

KIT_VERSION = 1


def load(path):
    """A normalized kit from a post.json or a ClipKaro project folder."""
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        return from_file(p / 'post.json') if (p / 'post.json').exists() else from_clipkaro(p)
    if p.suffix == '.json' and p.exists():
        return from_file(p)
    raise ValueError(f'not a post.json or a ClipKaro project folder: {p}')


def from_file(f):
    k = json.loads(f.read_text(encoding='utf-8'))
    if int(k.get('postkit', 0)) > KIT_VERSION:
        raise ValueError(f'{f} is a newer post kit (version {k["postkit"]}); update PostKaro (git pull)')
    src = k.get('source') or {}
    clips = []
    for c in k.get('clips', []):
        fp = Path(c['file'])
        fp = fp if fp.is_absolute() else (f.parent / fp)
        clips.append({**c, 'file': str(fp.resolve())})
    # a project folder is one batch, whether it came in as its folder or as its post.json
    key = str(f.parent.resolve()) if f.name == 'post.json' else str(f.resolve())
    return {'kit': key, 'project': k.get('project') or f.parent.name, 'title': k.get('title'),
            'channel': src.get('channel'), 'channel_url': src.get('channel_url'), 'source_url': src.get('url'),
            'clips': clips}


def from_clipkaro(folder):
    cj = folder / 'clips.json'
    if not cj.exists():
        raise ValueError(f'no clips.json in {folder}: is this a ClipKaro project folder?')
    clips_in = json.loads(cj.read_text(encoding='utf-8')).get('clips', [])
    try:
        proj = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        proj = {}
    files = {}
    for sub in ('clips', 'edited'):                 # edited wins
        for f in (folder / sub).glob('*.mp4') if (folder / sub).is_dir() else ():
            head = f.name.split('-')[0]
            if head.isdigit():
                files[int(head)] = f
    clips = []
    for c in clips_in:
        f = files.get(c.get('id'))
        if not f:
            continue
        clips.append({'id': c['id'], 'file': str(f.resolve()), 'title': c.get('title'), 'caption': c.get('caption'),
                      'clip_score': c.get('clip_score', c.get('score')), 'note': c.get('honesty_note'),
                      'deep': bool(c.get('deep')), 'text': c.get('post') or c.get('text') or {},
                      'duration': sum(e - s for s, e in c.get('ranges', [])) or None})
    src = proj.get('source') if proj.get('kind') == 'youtube' else None
    return {'kit': str(folder.resolve()), 'project': proj.get('slug') or folder.name, 'title': proj.get('title'),
            'channel': proj.get('channel'), 'channel_url': proj.get('channel_url'), 'source_url': src,
            'clips': clips}


def default_text(c, source_url, s=None):
    """{platform: (title, body)} for one clip."""
    s = s or settings.load()
    title = (c.get('title') or '').strip()
    cap = (c.get('caption') or '').strip() or title
    t = c.get('text') or {}
    yt, ig, fb = t.get('youtube') or {}, t.get('instagram') or {}, t.get('facebook') or {}
    desc = yt.get('description')
    if desc is None:
        desc = cap
        if source_url and s.get('youtube_full_video_line') and source_url not in desc:
            desc = f'{desc}\n\nFull video: {source_url}'
    return {'youtube': ((yt.get('title') or title)[:100], desc),
            'instagram': ('', ig.get('caption') or rules.drop_tags(cap, keep=rules.LIMITS['instagram']['hashtags'])),
            'facebook': ('', fb.get('caption') or rules.drop_tags(cap))}


def import_kit(path):
    """Add a kit to the queue as drafts. Safe to repeat: clips already there keep the user's edits; new
    clips are added; changed video files (re-edited clips) are picked up. Returns the batch id."""
    k = load(path)
    s = settings.load()
    b = db.one('SELECT id FROM batches WHERE kit=?', (k['kit'],))
    if b:
        bid = b['id']
        db.run('UPDATE batches SET project=?, title=?, channel=?, channel_url=?, source_url=? WHERE id=?',
               (k['project'], k['title'], k['channel'], k['channel_url'], k['source_url'], bid))
    else:
        bid = db.run('INSERT INTO batches (kit, project, title, channel, channel_url, source_url, created) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?)', (k['kit'], k['project'], k['title'], k['channel'],
                                                       k['channel_url'], k['source_url'], db.iso(db.now())))
    for c in k['clips']:
        f = Path(c['file'])
        if not f.exists():
            continue
        dur = probe_duration(f) or c.get('duration')
        size = f.stat().st_size
        row = db.one('SELECT id FROM clips WHERE batch_id=? AND no=?', (bid, c['id']))
        if row:
            db.run('UPDATE clips SET file=?, duration=?, size=?, score=?, title=?, caption=?, note=?, deep=? '
                   'WHERE id=?', (str(f), dur, size, c.get('clip_score'), c.get('title'), c.get('caption'),
                                  c.get('note'), int(bool(c.get('deep'))), row['id']))
            cid = row['id']
        else:
            cid = db.run('INSERT INTO clips (batch_id, no, file, duration, size, score, title, caption, note, deep) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (bid, c['id'], str(f), dur, size, c.get('clip_score'), c.get('title'), c.get('caption'),
                          c.get('note'), int(bool(c.get('deep')))))
        texts = default_text(c, k['source_url'], s)
        clip = {'duration': dur, 'size': size}
        for plat, (title, body) in texts.items():
            if db.one('SELECT id FROM posts WHERE clip_id=? AND platform=?', (cid, plat)):
                continue
            # a video the platform can't take (too long for a Facebook Reel) starts unticked; text can be fixed
            hard = rules.media_problems(plat, clip)
            db.run('INSERT INTO posts (clip_id, platform, enabled, title, body, state, updated) '
                   'VALUES (?, ?, ?, ?, ?, "draft", ?)', (cid, plat, int(not hard), title, body, db.iso(db.now())))
    return bid


def is_own(batch, s=None):
    s = s or settings.load()
    ch = (batch.get('channel') or '').strip().lower()
    return not ch or ch in {m.strip().lower() for m in s.get('my_channels', [])}


def probe_duration(f):
    """Length of a video in seconds: ffprobe when it's there, otherwise read from the MP4 header."""
    if shutil.which('ffprobe'):
        try:
            r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
                                'default=nw=1:nk=1', str(f)], capture_output=True, text=True, timeout=30)
            return round(float(r.stdout.strip()), 2)
        except (ValueError, subprocess.SubprocessError, OSError):
            pass
    return mp4_duration(f)


def mp4_duration(path):
    try:
        with open(path, 'rb') as f:
            total, pos = os.fstat(f.fileno()).st_size, 0
            while pos + 8 <= total:
                f.seek(pos)
                size, typ = struct.unpack('>I4s', f.read(8))
                head = 8
                if size == 1:
                    size, head = struct.unpack('>Q', f.read(8))[0], 16
                elif size == 0:
                    size = total - pos
                if size < 8:
                    return None
                if typ == b'moov':
                    q, end = pos + head, pos + size
                    while q + 8 <= end:
                        f.seek(q)
                        s2, t2 = struct.unpack('>I4s', f.read(8))
                        if t2 == b'mvhd':
                            version = f.read(4)[0]
                            if version == 1:
                                f.read(16)
                                scale, dur = struct.unpack('>IQ', f.read(12))
                            else:
                                f.read(8)
                                scale, dur = struct.unpack('>II', f.read(8))
                            return round(dur / scale, 2) if scale else None
                        if s2 < 8:
                            return None
                        q += s2
                    return None
                pos += size
    except (OSError, struct.error, IndexError):
        return None
    return None
