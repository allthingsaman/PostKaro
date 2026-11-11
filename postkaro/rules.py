"""Each platform's limits, and the check the Post page shows next to every text box.

Errors are things the platform itself would refuse (PostKaro won't send those). Warnings are only
shown: the user decides (for example "not your video").
"""
import re

LIMITS = {
    'youtube': {'title': 100, 'desc_bytes': 5000, 'short_max': 180},
    'instagram': {'caption': 2200, 'hashtags': 5, 'mentions': 20, 'min': 3, 'max': 900, 'mb': 300},
    'facebook': {'caption': 5000, 'min': 3, 'max': 90},
}
TAG = re.compile(r'(?<![\w#])#[^\s#.,!?;:()\[\]{}"\'।]+')
MENTION = re.compile(r'(?<![\w@])@[\w.]+')


def hashtags(text):
    return TAG.findall(text or '')


def drop_tags(text, drop=('#shorts',), keep=None):
    """Remove the hashtags in `drop` (any case) and, if `keep` is set, every hashtag after the first
    `keep`. Tidies the spaces left behind."""
    seen = 0

    def repl(m):
        nonlocal seen
        if m.group(0).lower() in drop:
            return ''
        seen += 1
        return m.group(0) if keep is None or seen <= keep else ''
    out = TAG.sub(repl, text or '')
    out = re.sub(r'[ \t]+\n', '\n', re.sub(r'[ \t]{2,}', ' ', out))
    return out.strip()


def media_problems(platform, clip):
    """What no text change can fix: the video's length or size."""
    dur, lim, out = clip.get('duration') or 0, LIMITS[platform], []
    if platform == 'instagram':
        if dur and not lim['min'] <= dur <= lim['max']:
            out.append(f'{fmt(dur)} long; Instagram Reels must be 3 s to 15 min.')
        if (clip.get('size') or 0) > lim['mb'] * 1024 * 1024:
            out.append(f'File is over {lim["mb"]} MB.')
    elif platform == 'facebook' and dur and not lim['min'] <= dur <= lim['max']:
        out.append(f'{fmt(dur)} long; Facebook Reels must be 3 to 90 seconds.')
    return out


def check(platform, title, body, clip, own=True, channel=None):
    """(errors, warnings) for one post."""
    err, warn = media_problems(platform, clip), []
    dur = clip.get('duration') or 0
    lim = LIMITS[platform]
    if platform == 'youtube':
        if not (title or '').strip():
            err.append('YouTube needs a title.')
        if len(title or '') > lim['title']:
            err.append(f'Title is {len(title)} characters; YouTube allows {lim["title"]}.')
        n = len((body or '').encode('utf-8'))
        if n > lim['desc_bytes']:
            err.append(f'Description is {n} bytes; YouTube allows {lim["desc_bytes"]} (Hindi letters take 3 each).')
        if any(ch in (title or '') + (body or '') for ch in '<>'):
            err.append('YouTube does not allow the characters < and >.')
        if dur > lim['short_max']:
            warn.append(f'{fmt(dur)} long: over 3 minutes, so it becomes a normal video, not a Short.')
    elif platform == 'instagram':
        if len(body or '') > lim['caption']:
            err.append(f'Caption is {len(body)} characters; Instagram allows {lim["caption"]}.')
        n = len(hashtags(body))
        if n > lim['hashtags']:
            err.append(f'{n} hashtags; Instagram allows {lim["hashtags"]}.')
        if len(MENTION.findall(body or '')) > lim['mentions']:
            err.append(f'More than {lim["mentions"]} @mentions.')
    elif platform == 'facebook':
        if len(body or '') > lim['caption']:
            err.append(f'Caption is {len(body)} characters; keep it under {lim["caption"]}.')
    if not own:
        warn.append(f'Not your video{f" ({channel})" if channel else ""}: it may get a copyright claim or less '
                    f'reach. You decide.')
    return err, warn


def fmt(sec):
    sec = int(round(sec or 0))
    return f'{sec // 60}:{sec % 60:02d}'
