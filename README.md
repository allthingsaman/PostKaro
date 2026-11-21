<p align="center">
  <img src="https://res.cloudinary.com/amanupadhyay1211/image/upload/f_auto,q_auto,w_600/v1794369701/png_style_sticker_illustration_no_background_tr_ihlxsr.png" alt="PostKaro mascot: the ClipKaro bluebird as a postman in a yellow cap, with a yellow bag full of video cards, sending a film-strip paper plane past three check marks" width="260">
</p>

# PostKaro 📮

**Post your clips to YouTube Shorts, Instagram Reels and your Facebook Page, from your own laptop.**
ClipKaro makes the clips. PostKaro posts them. It also works with any ClipKaro project folder.

<p align="center">
  <a href="https://youtu.be/Dlq4z26w1QM"><img src="https://img.youtube.com/vi/Dlq4z26w1QM/maxresdefault.jpg" alt="Watch the video guide on YouTube: I Built an AI That Clips Your GTA 6 Stream While You're Live (Windows Setup + Installation)" width="640"></a>
</p>
<p align="center"><b>▶ <a href="https://youtu.be/Dlq4z26w1QM">Watch the video guide</a></b> (16 min): how to install ClipKaro and
PostKaro on Windows and use them yourself.</p>

## What it does

- **One page in your browser.** Every clip already has its title and caption for each platform. You
  check them, change what you like, and press **Schedule**.
- **You choose the time.** Post right away, type a time, let PostKaro pick good times, or spread all
  the clips evenly over a few hours or days.
- **You choose where.** Turn a platform on or off for one clip or for all clips. With more than one
  channel, account or Page, pick which one gets each post.
- **It tells you what happened.** Every post ends as a link to the live post, or as a plain-words
  error with a **Retry** button. A desktop notification tells you either way.
- **It warns, it never blocks.** It warns before a login runs out, and when a clip comes from someone
  else's video (copyright). You decide.
- **Everything stays on your laptop.** There's no PostKaro server and no outside posting service. Your
  logins are locked on your laptop, and the key sits in your computer's password store.

## Set up (once)

Works on **Windows, Mac and Linux**. You need Python 3.11 or newer (the same one you use for
ClipKaro). Put the PostKaro folder **next to** the ClipKaro folder, not inside it.

**Easiest way:** in Claude Code, inside the ClipKaro folder, say **"install PostKaro too"**.

**By hand:**

Windows (PowerShell):
```powershell
git clone https://github.com/allthingsaman/PostKaro.git
cd PostKaro
python install.py
python run.py open
```

Mac:
```bash
git clone https://github.com/allthingsaman/PostKaro.git
cd PostKaro
python3.13 install.py
python3 run.py open
```

Linux: the same as Mac, with `python3` instead of `python3.13`.

**What `install.py` does:**
- It makes a private Python environment for PostKaro (the `.venv` folder).
- It makes PostKaro start by itself when you log in to your computer. That keeps the page link
  working, and lets Instagram posts go out at their time. Add `--no-service` if you don't want that.
- Your logins go into your computer's own password store: Windows Credential Manager, the Mac
  Keychain, or the Linux keyring. On a Mac, if it asks whether Python may use the "postkaro" item,
  choose **Always Allow**.
- Thumbnails use ffmpeg, the same one ClipKaro uses. PostKaro finds it by itself.

**Then connect your accounts** on the **Accounts** page. Follow
**[docs/connect-accounts.md](docs/connect-accounts.md)** step by step. It takes about 30–45 minutes,
and you only do it once.

## Post your clips, step by step

**1. Open the video in PostKaro.** Use any one of these:
- When ClipKaro finishes, it ends with a **"Post them"** link. Click it.
- On PostKaro's **Post** page, paste a ClipKaro project folder into **Add a video**.
- In a terminal: `python3 run.py open /path/to/Claude_Clipper/output/<project>`

**2. Check the words.** Each clip has one box per platform, with its own title and caption. Change
anything you like. A counter turns red when a text is too long for that platform.

**3. Choose where each clip goes.**
- Each box has an on/off switch for its platform.
- **Platforms for all clips**, at the top of the page, has one switch per platform. Turn Facebook off
  there, and it goes off on every clip that isn't scheduled yet. Each clip's own switch still works.
  A half-filled switch with "N of M" means it's on for only some clips.
- If you connected more than one YouTube channel, Instagram account or Facebook Page, each box has a
  **"to …"** list. It starts on your default account. Pick another one for just this post.

**4. Pick the times.** See the next section. Under every time, PostKaro shows roughly when it goes
live, like "under 1 hour" or "about 3 days". It turns red if the time has already passed.

**5. Press Schedule.** The blue button says how many posts it will schedule. Press it **once**.

**6. Watch it go.** The **Queue** page shows what's waiting. The **Posted** page shows the links to
your live posts.

## Picking the times

| What you want | What to do |
|---|---|
| Post as soon as possible | Leave the time empty, then press **Schedule**. |
| Post one clip right now | Press **Post now** at the top of that clip. |
| One time for all platforms of a clip | Type it in **Time for all platforms**, above the clip's boxes. |
| A different time on one platform | Type a time in that platform's own box. |
| Let PostKaro choose | Press **Plan for me**. |
| Even gaps over a few hours or days | Use **Spread over**. |

**Empty time:** PostKaro starts uploading as soon as you press Schedule. The clip goes live once the
platform has finished processing it, usually in a few minutes. Keep the laptop on until the Queue
shows **Live**.

**Post now:** it posts that one clip on its ticked platforms straight away, even if a time is typed in.
How long the upload takes depends on your internet.

**Plan for me:** it fills in times for you. The best clips go first, at your usual time on each
platform, a few clips a day. You set the usual times and "Clips per day" on the Accounts page.

**Spread over:** type a number, pick **minutes**, **hours** or **days**, and press **Spread**.
PostKaro divides that time evenly between the clips, starting with clip #1:
- 10 clips over 10 minutes: one clip every minute.
- 100 clips over 1 day: one clip every 14 minutes 24 seconds.

Clip #1 goes when you press Schedule. All platforms of a clip get the same time. Spread only fills
in the times. Check them, then press **Schedule** straight away, because the times count from the
moment you pressed Spread. PostKaro warns you if the plan goes over a daily limit (see
[Daily limits](#daily-limits)).

> **Tip for many clips:** over 1 day, more than 100 clips go over Instagram's 100 posts a day. Spread
> them over 2 days or more.

## Looking at a clip

- **Preview** opens the clip on a big screen. Use the arrow keys (or the buttons) for the previous and
  next clip, and **Esc** to close it. **Use this frame as thumbnail** works there too.
- **Thumbnail:** pause the video on the frame you like and press **Use this frame**, or press **Upload
  image**. YouTube and Facebook take either. Instagram takes only a frame from the video.
- **Don't want a clip?** Press the bin icon to remove it. Removed clips wait under **Removed clips** at
  the bottom of the page. Press **Restore** to bring one back.

## The Queue: what the words mean

| Word | What it means |
|---|---|
| **Scheduled** | Waiting its turn to upload. |
| **Uploading 40%** | Sending the video now. |
| **Processing** | The platform is preparing the video. |
| **Uploaded, live at 18:00** | YouTube or Facebook has it, and makes it live at that time by itself. |
| **Ready, publishes 18:00** | Instagram has it, and PostKaro publishes it at that time. Keep the laptop on. |
| **Publishing** | Going live now. |
| **Live** | Done. Press **Open** to see the post. |
| **Failed** | Something went wrong. The reason is written under it. |
| **Missed** | The laptop was off at its time. |
| **Cancelled** | You cancelled it. |

**The buttons:**
- **Cancel:** stops a post. If it was already uploaded, PostKaro removes it from the platform.
- **Retry:** tries a failed post again.
- **Back to drafts:** puts a failed or cancelled post back on the Post page. There you can change its
  text, time or channel, and schedule it again.
- **Post now / New time / Skip:** for a missed post. Post it at once, give it a new time, or let it go.

The Queue shows each post as **"#N Short title"**. The same #N on YouTube, Instagram and Facebook means
it's the same clip. Under that you see the posted title or caption, and where it goes ("to …").

## How each platform goes live

| Platform | Goes live at its time by itself? | Laptop needed at that time? |
|---|---|---|
| YouTube | **Yes.** PostKaro uploads it right away as private, and YouTube makes it public at its time. | No |
| Facebook Page | **Yes.** PostKaro uploads it right away, and Facebook publishes it at its time (10 minutes to 29 days ahead). | No |
| Instagram | **No.** Instagram can't schedule. PostKaro uploads it up to a day before, then publishes it at its time. | **Yes** |

If the laptop was off at an Instagram post's time, PostKaro asks you what to do (the post shows as
**Missed**). If you'd rather it posts by itself when the laptop is back on, change "Instagram, if this
computer was off" on the Accounts page.

## When something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| An Instagram post says "Instagram's upload server could not store the video" | Instagram's upload server was too slow (Meta error 1363008). It's on Meta's side, not yours. | Nothing. PostKaro tries again by itself after 1, 2, 5, 15, 30, 60 and 120 minutes, and the error says when the next try is. |
| A YouTube post says "used up today's YouTube allowance" | Your Google app can upload 100 videos a day. | Press **Retry** after YouTube's daily reset: midnight in California (1:30 pm in India). The post keeps its time. |
| **Reconnect soon** on the Accounts page | A login is about to run out (Instagram's lasts about 60 days). PostKaro also sends a notification 7 days and 1 day before. | Press **Reconnect** on that account. |
| **Login failed** on the Accounts page | The login no longer works. | Press **Reconnect**, then **Retry** on the failed posts. |
| A dark warning about "not one of your channels" | The clip comes from someone else's video. It may get a copyright claim or less reach. | Your choice. Add your own channels under **My channels** on the Accounts page, so their videos get no warning. |
| **Video file not found** | The clip's video file was moved or deleted. | Put the file back, or add the video again. |

Short hiccups, like a dropped internet connection, are tried again by themselves after 1, 5 and 15
minutes. If a post still fails after that, press **Retry**.

## Accounts and settings

The **Accounts** page lists your YouTube channels, Instagram accounts and Facebook Pages.
- **Default:** new posts go to this account. Press **Make default** on another one to change it.
- **Add channel:** connect another YouTube channel.
- **Reconnect:** log in again (one Meta login connects Instagram and Facebook together).
- The round-arrow button checks a login now. The plug button disconnects an account.

Under **Posting defaults** on the same page:

| Setting | What it does |
|---|---|
| Time zone | The times you type and see are in this zone. |
| Clips per day | How many clips "Plan for me" puts on each platform per day. |
| Usual times | Where "Plan for me" puts each day's first clip, per platform. |
| My channels | Videos from these channels get no copyright warning. One per line. |
| YouTube visibility | Public, Unlisted or Private. Unlisted is handy for a quiet test. |
| Made for kids | YouTube asks this for every video. |
| YouTube category | The category YouTube files the Short under. |
| Tell subscribers | Lets YouTube notify your subscribers about new Shorts. |
| "Full video" link | Adds "Full video: link" to new YouTube descriptions. |
| Instagram, if this computer was off | **Ask me**, or **Post it when the computer is back on**. |

## Daily limits

| Platform | Limits |
|---|---|
| YouTube | Up to 3 minutes counts as a Short; longer becomes a normal video. Titles up to 100 characters. Your Google app can upload **100 videos a day**. PostKaro uploads YouTube posts as soon as you press Schedule, so more than 100 YouTube clips at once go over it, however far apart their times are. |
| Instagram | **About 100 posts a day.** At most 5 hashtags. Captions up to 2,200 characters. The login lasts about 60 days, and PostKaro reminds you to reconnect. |
| Facebook | Pages only, not personal profiles. Reels must be 3–90 seconds. **30 Reels a day.** |

## Commands

Run these in the PostKaro folder (on Windows, `python` instead of `python3`):

```
python3 run.py open [folder | post.json]   open the page (and add a ClipKaro project)
python3 run.py status                      your accounts, the queue, and whether PostKaro runs
python3 run.py check                       check every login now
python3 run.py service on | off | status   start PostKaro by itself at login, or not
python3 run.py serve                       run it in this window (to see errors)
python3 run.py post-now <folder> [--dry]   (for ClipKaro's live clipping) add a project and post it everywhere now;
                                           --dry only lists what it would post
```

## Your own website (needed once, for Google)

Google lets your Google app leave "Testing" only when it has a homepage and a privacy policy link.
The `docs/` folder has both pages (`index.md` and `privacy.md`). Put them online for free with GitHub
Pages:
1. Put this repo on GitHub under your account, as a public repo.
2. Go to the repo's **Settings** → **Pages** → **Source: Deploy from a branch**. Pick branch **main**
   and folder **/docs**, then press **Save**.
3. A minute later, your site is at `https://<github-user>.github.io/PostKaro/`, and the privacy
   policy is at `…/PostKaro/privacy.html`.

## More help

- [docs/connect-accounts.md](docs/connect-accounts.md): connecting YouTube, Instagram and Facebook, step by step
- [docs/how-it-works.md](docs/how-it-works.md): how the parts fit together, for anyone changing the code
- [docs/post-kit.md](docs/post-kit.md): the `post.json` file that ClipKaro (or anything else) hands to PostKaro

Tests: `.venv/bin/python -m unittest discover -s tests` (Windows: `.venv\Scripts\python`).
