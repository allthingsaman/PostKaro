"""Custom thumbnails ("covers"), one per clip: a frame from the video, or an image the user uploads.

What each platform can take:
    YouTube    any cover. Set with thumbnails.set once the video has finished processing (Shorts too).
    Facebook   any cover. POST /{video-id}/thumbnails after the reel is uploaded.
    Instagram  only a frame from the video (thumb_offset). An uploaded image would need a public web
               link (cover_url), which a local app doesn't have, so Instagram keeps its own cover.

Covers live in the data folder (covers/<clip id>-<version>.jpg). They are made with ffmpeg.
"""
import shutil
import subprocess
import time
from pathlib import Path

from . import db, paths

MAX_UPLOAD = 20 * 1024 * 1024
MAGIC = {b'\xff\xd8\xff': 'jpeg', b'\x89PNG\r\n\x1a\n': 'png', b'RIFF': 'webp'}


class CoverError(Exception):
    pass


def _folder():
    d = paths.data_dir() / 'covers'
    d.mkdir(exist_ok=True)
    return d


def _ffmpeg(args):
    if not shutil.which('ffmpeg'):
        raise CoverError('Thumbnails need ffmpeg (the same one ClipKaro uses). Install it, then try again.')
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise CoverError(f'ffmpeg could not make the thumbnail: {(r.stderr or "").strip()[-200:]}')


def _store(cid, made, kind, ms):
    """Keep `made` as the clip's cover (a new version), drop the old file."""
    c = db.one('SELECT cover FROM clips WHERE id=?', (cid,))
    v = int(time.time() * 1000)
    final = _folder() / f'{cid}-{v}.jpg'
    Path(made).replace(final)
    db.run('UPDATE clips SET cover=?, cover_kind=?, cover_ms=?, cover_v=? WHERE id=?', (str(final), kind, ms, v, cid))
    if c and c['cover'] and Path(c['cover']).exists() and Path(c['cover']) != final:
        Path(c['cover']).unlink(missing_ok=True)


def from_frame(cid, seconds):
    """The frame at `seconds` of the clip becomes its cover (full size JPEG). Instagram can use it too."""
    c = db.one('SELECT file, duration FROM clips WHERE id=?', (cid,))
    if not c or not Path(c['file']).exists():
        raise CoverError('The video file is gone from its folder.')
    t = max(0.0, min(float(seconds or 0), max(0.0, (c['duration'] or 0) - 0.05)))
    tmp = _folder() / f'{cid}-new.jpg'
    _ffmpeg(['-ss', f'{t:.3f}', '-i', c['file'], '-frames:v', '1', '-q:v', '2', str(tmp)])
    if not tmp.exists():
        raise CoverError('No frame came out at that time. Pick another moment.')
    _store(cid, tmp, 'frame', int(round(t * 1000)))


def from_image(cid, data):
    """An uploaded JPEG/PNG/WebP becomes the cover: turned into a JPEG, longest side at most 1920 px."""
    if not db.one('SELECT id FROM clips WHERE id=?', (cid,)):
        raise CoverError('No such clip.')
    if not data:
        raise CoverError('The image was empty.')
    if len(data) > MAX_UPLOAD:
        raise CoverError('The image is over 20 MB. Use a smaller one.')
    kind = next((k for m, k in MAGIC.items() if data.startswith(m)), None)
    if not kind or (kind == 'webp' and data[8:12] != b'WEBP'):
        raise CoverError('Use a JPG, PNG or WebP image.')
    src = _folder() / f'{cid}-upload.{kind}'
    src.write_bytes(data)
    tmp = _folder() / f'{cid}-new.jpg'
    try:
        _ffmpeg(['-i', str(src), '-frames:v', '1', '-vf',
                 "scale='if(gt(iw,ih),min(1920,iw),-2)':'if(gt(iw,ih),-2,min(1920,ih))'", '-q:v', '3', str(tmp)])
    finally:
        src.unlink(missing_ok=True)
    _store(cid, tmp, 'image', None)


def remove(cid):
    c = db.one('SELECT cover FROM clips WHERE id=?', (cid,))
    if c and c['cover']:
        Path(c['cover']).unlink(missing_ok=True)
    db.run('UPDATE clips SET cover=NULL, cover_kind=NULL, cover_ms=NULL, cover_v=? WHERE id=?',
           (int(time.time() * 1000), cid))


def describe(clip):
    """A short line for the page about the clip's thumbnail and where it is used."""
    kind = clip.get('cover_kind')
    if kind == 'frame':
        s = (clip.get('cover_ms') or 0) // 1000
        return f'Frame at {s // 60}:{s % 60:02d}. Used on YouTube, Instagram and Facebook.'
    if kind == 'image':
        return 'Your image. Used on YouTube and Facebook. Instagram can only use a frame from the video.'
    return 'Automatic. Pause on a frame and use it, or upload an image (9:16, for example 1080×1920).'
