<p align="center">
  <img src="https://res.cloudinary.com/amanupadhyay1211/image/upload/f_auto,q_auto,w_600/v1794369701/png_style_sticker_illustration_no_background_tr_ihlxsr.png" alt="PostKaro mascot: the ClipKaro bluebird as a postman in a yellow cap, with a yellow bag full of video cards, sending a film-strip paper plane past three check marks" width="260">
</p>

# PostKaro 📮

Post your clips to **YouTube Shorts**, **Instagram Reels** and your **Facebook Page** from your own laptop.
PostKaro is ClipKaro's partner: ClipKaro makes the clips, PostKaro posts them. It also works on its own
with any ClipKaro project folder.

- **One page in your browser.** Every clip already has its title and caption for each platform. Change
  anything, remove clips you don't want, press **Schedule**.
- **Each platform at its own time.** "Plan for me" spreads the clips over the coming days at your usual
  times, best clips first.
- **Custom thumbnails.** Pick a frame from the clip, or upload an image. YouTube and Facebook take either;
  Instagram takes a frame from the video (an uploaded image would need a public web link).
- **Checks every post.** Each post ends up as a live link, or a plain error with a **Retry** button. A
  desktop notification tells you either way.
- **Warns before a login runs out.** It also warns about clips of other people's videos (copyright).
  Warnings never block you: you decide.
- **Fully local.** No server of ours and no outside posting service. Your logins are encrypted on your
  laptop, and the key sits in your computer's password store.

## Set up (once)

Works on **Windows, Mac and Linux**. You need Python 3.11 or newer: use the same one as for ClipKaro.
Put PostKaro **next to** the ClipKaro folder, not inside it. Easiest: in Claude Code (inside ClipKaro),
say **"install PostKaro too"**. By hand:

**Windows** (PowerShell):
```powershell
git clone https://github.com/allthingsaman/PostKaro.git
cd PostKaro
python install.py
python run.py open
```

**Mac:**
```bash
git clone https://github.com/allthingsaman/PostKaro.git
cd PostKaro
python3.13 install.py
python3 run.py open
```

**Linux:** the same, with `python3`.

`install.py` makes a private Python environment (`.venv`) and sets PostKaro to start by itself when you
log in: on Windows a login entry for your user, on a Mac a login item (macOS shows "Background Items
Added"), on Linux a systemd user service. That keeps the page link working, and lets Instagram posts go
out at their time. `--no-service` skips that.

- **Logins** stay in your computer's own password store: Windows Credential Manager, the Mac Keychain,
  or the Linux keyring. On a Mac, if it asks whether Python may use the "postkaro" Keychain item, choose
  **Always Allow**.
- **Thumbnails** use ffmpeg, the same one ClipKaro uses (on a Mac Homebrew's `ffmpeg-full`, which
  PostKaro finds by itself).

Then connect your accounts on the **Accounts** page. The step-by-step guide is
**[docs/connect-accounts.md](docs/connect-accounts.md)**: about 30–45 minutes, once.

## Every day

- **From ClipKaro:** finished clips end with a **"Post them"** link. Click it.
- **An older ClipKaro video:** `python3 run.py open /path/to/Claude_Clipper/output/<project>`

On the page:
1. Check each clip's text for each platform. The counters turn red over a platform's limit.
   - **Which channel or account:** with more than one YouTube channel, Instagram account or Facebook
     Page connected, each box has a "to …" list. It starts on your default (Accounts page); pick another
     for just this post. It can change until you press Schedule. The Queue shows where each post goes.
2. Press **Plan for me**, or type times yourself:
   - **Time for all platforms** (above each clip's three boxes) puts the same time on YouTube, Instagram
     and Facebook. Change one box to give that platform its own time.
   - Under every time PostKaro shows roughly when it goes live: "under 1 hour", "about 5 hours",
     "about 3 days".
   - **An empty time** means "as soon as I press Schedule": PostKaro starts uploading at once, and the
     clip goes live as soon as the platform has finished processing it (usually a few minutes). Keep
     the laptop on until it shows as Live.
3. Press **Schedule** (the button says how many posts). The **Queue** shows what's waiting; **Posted**
   shows the links.

**Post one clip right now:** press **Post now** at the top of the clip. Its ticked platforms upload at
once, even where a time is typed in, and each goes live as soon as the platform has processed it
(usually a few minutes; how long the upload takes depends on your internet). Keep the laptop on until
the Queue shows it live.

**Turn a platform off for every clip:** the **Platforms for all clips** row at the top of a video's page
has one switch per platform. Turn Facebook off there and it goes off on every clip that isn't scheduled
yet; each clip's own switch still works for exceptions. "Some" (a half switch) means it is on for only
some clips.

**Spread every clip over a time:** type a number, pick minutes, hours or days in **Spread over**, and
press **Spread**. PostKaro divides the time evenly between the clips that have a platform on, #1 first:
10 clips over 10 minutes is one a minute, 100 clips over 1 day one every 14 min 24 s. Clip #1 goes when
you press Schedule, and all of a clip's platforms share its time. Check the times, then press
**Schedule**. It warns you when a plan passes a daily limit: about 100 YouTube uploads a day (PostKaro
uploads YouTube posts right away and YouTube publishes each at its time) and 100 Instagram posts a day.
Instagram posts need the laptop on at their times; YouTube and Facebook post by themselves.

**How each platform goes live**

| | Goes live at its time by itself | Laptop needed at that time? |
|---|---|---|
| YouTube | yes: uploaded at once as private, YouTube makes it public at the time | no |
| Facebook Page | yes: uploaded at once, Facebook publishes it (10 minutes to 29 days ahead) | no |
| Instagram | no: Instagram can't schedule | **yes**. PostKaro uploads up to a day before and publishes at the time. If the laptop was off, it asks you what to do (or posts at once, if you choose that on the Accounts page). |

## Commands

```
python3 run.py open [folder | post.json]   open the page (and add a ClipKaro project)
python3 run.py status                      accounts, queue, and whether PostKaro runs
python3 run.py check                       check every login now
python3 run.py service on | off | status   start by itself at login
python3 run.py serve                       run it in this terminal (to see errors)
python3 run.py post-now <folder> [--dry]   (ClipKaro live clipping) add a project and post it everywhere now
```

## Limits worth knowing

| Platform | Limits |
|---|---|
| YouTube | Up to 3 minutes counts as a Short; longer becomes a normal video. Title up to 100 characters. Your Google project can upload 100 videos a day. |
| Instagram | At most 5 hashtags. Caption up to 2,200 characters. About 100 posts a day. The login lasts about 60 days, and PostKaro reminds you to reconnect. |
| Facebook | Pages only, not personal profiles. Reels must be 3–90 seconds. 30 Reels a day. |

## Your own website (needed once, for Google's login screen)
Google only lets your own Google app leave "Testing" when it has a homepage and a privacy policy
link. The `docs/` folder has both pages (`index.md`, `privacy.md`). Publish them for free with GitHub
Pages:
1. Put this repo on GitHub under your account (public).
2. Repo → **Settings** → **Pages** → **Source: Deploy from a branch**, branch **main**, folder **/docs**
   → **Save**.
3. A minute later the site is at `https://<github-user>.github.io/PostKaro/`. The privacy policy is
   at `…/PostKaro/privacy.html`.

## More

- [docs/connect-accounts.md](docs/connect-accounts.md): connecting YouTube, Instagram and Facebook
- [docs/how-it-works.md](docs/how-it-works.md): how the parts fit, for anyone changing the code
- [docs/post-kit.md](docs/post-kit.md): the `post.json` file ClipKaro (or anything else) hands over

Tests: `.venv/bin/python -m unittest discover -s tests` (Windows: `.venv\Scripts\python`).
