# The post kit: `post.json`

The post kit is the one file ClipKaro hands to PostKaro. It keeps the two apps separate: PostKaro never
reads ClipKaro's other files when a `post.json` is there. Anything else that makes clips can write one too.

ClipKaro writes it to `output/<project>/post.json` after editing. Then
`python3 run.py open <that folder>` (or ClipKaro's "Post them" link) adds it to PostKaro.

```json
{
  "postkit": 1,
  "made_by": "ClipKaro 2.0",
  "project": "former-cia-agents-warning-china-doesnt-n-QPXJ3VL7Li4",
  "title": "Former CIA Agent's Warning: …",
  "source": {
    "channel": "Raj Shamani",
    "channel_url": "https://www.youtube.com/channel/…",
    "url": "https://youtu.be/QPXJ3VL7Li4"
  },
  "clips": [
    {
      "id": 1,
      "file": "edited/01-russia-is-almost-a-terrorist-state.mp4",
      "duration": 80.06,
      "clip_score": 7.3,
      "title": "Russia Is Almost A Terrorist State",
      "caption": "Ex-CIA agent ka seedha jawab… #CIA #Russia #RajShamani",
      "note": null,
      "deep": false,
      "text": {
        "youtube":   {"title": "Russia Is Almost A Terrorist State", "description": "…\n\nFull video: https://youtu.be/QPXJ3VL7Li4"},
        "instagram": {"caption": "Ex-CIA agent ka seedha jawab… #CIA #Russia #RajShamani"},
        "facebook":  {"caption": "Ex-CIA agent ka seedha jawab…"}
      }
    }
  ]
}
```

**Top-level fields**

| Field | Meaning |
|---|---|
| `postkit` | Format version. PostKaro refuses a higher number than it knows and says to update. |
| `source.channel` | Whose video the clips come from. If it isn't in "My channels" (Accounts page), PostKaro shows a copyright warning. |
| `source.url` | The full video, used for the "Full video: link" line in YouTube descriptions. |

**Clip fields**

| Field | Meaning |
|---|---|
| `file` | The finished clip, relative to the folder of `post.json` (or a full path). |
| `title`, `caption` | Used when `text` is missing for a platform. |
| `note` | Shown above the clip, for example a deep clip's honesty note. |
| `text` | What each platform gets. Any part may be left out. |

**When `text` is missing for a platform**

| Platform | What PostKaro uses |
|---|---|
| YouTube | Title = `title`. Description = `caption`, plus "Full video: link". |
| Instagram | Caption = `caption` without `#shorts`, keeping only the first 5 hashtags. |
| Facebook | Caption = `caption` without `#shorts`. |

**Adding the same project again** is safe:
- clips already in PostKaro keep any changes you made on the page;
- new clips are added;
- re-edited video files are picked up.

**No `post.json`:** PostKaro reads a ClipKaro project folder directly:
- `clips.json`: titles, captions, scores, honesty notes, and a `post` block per clip if present;
- `project.json`: the channel and the link;
- `edited/NN-*.mp4`, or else `clips/NN-*.mp4`.
