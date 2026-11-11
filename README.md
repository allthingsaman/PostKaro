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
- **Checks every post.** Each post ends up as a live link, or a plain error with a **Retry** button. A
  desktop notification tells you either way.
- **Warns before a login runs out.** It also warns about clips of other people's videos (copyright).
  Warnings never block you: you decide.
- **Fully local.** No server of ours and no outside posting service. Your logins are encrypted on your
  laptop, and the key sits in your computer's password store.

## Set up (once)

You need Python 3.11 or newer.

```
git clone <this repo> PostKaro
cd PostKaro
python3 install.py          # Windows: python install.py
python3 run.py open
```

`install.py` makes a private Python environment (`.venv`) and sets PostKaro to start by itself when you
log in. That keeps the page link working, and lets Instagram posts go out at their time.
`--no-service` skips that.

Then connect your accounts on the **Accounts** page. The step-by-step guide is
**[docs/connect-accounts.md](docs/connect-accounts.md)**: about 30–45 minutes, once.

## Every day

- **From ClipKaro:** finished clips end with a **"Post them"** link. Click it.
- **An older ClipKaro video:** `python3 run.py open /path/to/Claude_Clipper/output/<project>`

On the page:
1. Check each clip's text for each platform. The counters turn red over a platform's limit.
2. Press **Plan for me**, or type times yourself. An empty time means "as soon as I press Schedule".
3. Press **Schedule all**. The **Queue** shows what's waiting; **Posted** shows the links.

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
