# How PostKaro works (for anyone changing the code)

## The parts

```
run.py / install.py      entry points (run.py always re-runs itself inside .venv)
postkaro/
  cli.py                 the commands: serve, open, link, status, check, service
  server.py              the local web server: the page, its API, video files and stills, login returns
  worker.py              the background loop: moves each post along, checks logins, sends notifications
  kit.py                 reads post.json or a ClipKaro project folder into drafts
  planner.py             "Plan for me"
  rules.py               each platform's limits (errors block, warnings only show)
  db.py                  SQLite: batches, clips, posts, accounts, events (no secrets)
  vault.py               logins and app secrets: an encrypted file, its key in the OS password store
  settings.py            the user's defaults (settings.json), local time helpers
  paths.py               data and config folders, app.json (port + page key)
  service.py             start at login (systemd user service / Windows Run key / macOS LaunchAgent)
  notify.py              desktop notifications without extra packages
  platforms/
    base.py              what a platform plug-in does: check, upload, poll, publish, update, cancel
    youtube.py           YouTube Data API v3 (Google login with PKCE, own Desktop client)
    meta.py              Instagram Reels + Facebook Page Reels (Graph API v27.0, own Meta app)
web/                     the page: index.html, app.js, style.css (no build step)
tests/                   unittest; fake platforms, no real accounts
```

## A post's life

One post = one clip on one platform. Its states are in `db.py`:

```
draft → scheduled → uploading → processing → waiting → (publishing) → live
                                                    ↘ failed / missed / cancelled
```

The worker wakes every 20 seconds, and at once after the page schedules something. It handles one post
at a time, so two big uploads never run together.

- **YouTube** (`remote_schedule`): uploads at once as private with `publishAt`. YouTube makes it public
  at the time. The worker then checks that it is public and saves the Shorts link.
- **Facebook** (`remote_schedule`, at most 29 days ahead, at least 12 minutes): `video_reels` start →
  upload → finish with `SCHEDULED`. Facebook publishes it.
- **Instagram** (no remote scheduling):
  - It uploads into a "container" up to 23 hours before the time (a container lives 24 hours).
  - At the time, the worker calls `media_publish`.
  - If the laptop was off at the time, the post becomes `missed`, or goes out at once if the "late"
    setting says so.

**Errors** come back from the plug-ins as `PlatformError`:
- `retry=True`: tried again after 1, 5 and 15 minutes, then the post fails.
- `login=True`: the account is marked broken and the post fails with "reconnect".
- anything else: the post fails at once with the plain-word message.

**Changing a post that is already uploaded:**
- YouTube changes it in place (`videos.update`).
- Instagram and Facebook remove it and upload it again (`update()` returns False).

## Logins

**Where they are kept** (`vault.py`): one Fernet-encrypted file in the data folder. Its key sits in the OS
password store through `keyring`.
- Only a short key goes into the password store, because Windows can't hold big entries.
- Every call to the password store has a 30-second limit, so a locked keyring can't freeze the app.
- With no password store at all, the key goes into a user-only file, and the ⚙ page says so.

**YouTube:**
- The user's own Google project and "Desktop app" client.
- Google's login page returns to `http://127.0.0.1:<port>/`.
- Uses PKCE and offline access, with the `youtube` scope (upload, change and delete).

**Meta:**
- The user's own app in Development mode, with Facebook Login.
- Meta's login page returns to `http://localhost:<port>/oauth/meta`.
- After login: a long-lived user key (about 60 days) for Instagram, and a Page key (no end date) for
  Facebook.
- `debug_token` gives the end dates, and the ⚙ page warns 7 days and 1 day before.

**Health check:** every 6 hours, and with "Check now", each plug-in's `check()` asks the platform "who
am I?".

## The page's safety

- **Listens on 127.0.0.1 only**, and checks the Host header (127.0.0.1 or localhost with the right
  port).
- **A key in `app.json`.** The link carries it once (`?k=`). Then a cookie keeps it (HttpOnly,
  SameSite=Strict).
- **Every change also needs:**
  - the key in an `X-PostKaro` header;
  - no foreign `Origin`;
  - `Sec-Fetch-Site: same-origin`.
- **Login returns are checked by their one-time `state` value.** The cookie isn't sent on a return from
  another site, so it can't do that job.
- **Secrets never go to the page.** The page only sees "connected".

## ClipKaro ↔ PostKaro

- **What ClipKaro hands over:** `output/<project>/post.json` ([post-kit.md](post-kit.md)).
- **How ClipKaro finds PostKaro:** through `app.json` in PostKaro's config folder:

  | OS | Folder |
  |---|---|
  | Linux | `~/.config/postkaro` |
  | macOS | `~/Library/Application Support/postkaro` |
  | Windows | `%LOCALAPPDATA%\postkaro` |

- **The link:** ClipKaro runs `python run.py link <project folder>` inside PostKaro, and prints the link
  it gets back.

## Tests

`.venv/bin/python -m unittest discover -s tests`.
- They use a throwaway folder (`POSTKARO_HOME`), a key file instead of the keyring
  (`POSTKARO_VAULT=file`), no notifications, and fake platforms.
- They need ffmpeg to make tiny test videos.

The real platform calls can only be tested with real accounts (docs/connect-accounts.md, Part C).
