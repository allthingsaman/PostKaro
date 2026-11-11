# Connect your accounts (one time, about 30–45 minutes)

PostKaro posts through **your own** small "developer apps": one at Google (for YouTube) and one at Meta
(for Instagram and Facebook). You make them once. They are free, need no review, no website and no
company, because they only post to **your own** accounts.

Your logins and app secrets stay on your laptop. You never type your Google or Facebook password into
PostKaro: you log in on Google's and Meta's own pages.

> Google and Meta move their buttons around now and then. If a screen looks a bit different, look for
> the words in **bold**. These steps were checked in November 2026.

**Before you start**
- Install PostKaro and open it: `python3 run.py open` (Windows: `python run.py open`), then click **⚙**.
- Have these ready:
  - the Google account that owns your YouTube channel;
  - the Facebook account that manages your Facebook Page;
  - your phone, because Meta checks it once.

---

## Part 0. Get Instagram ready (5 minutes)

Instagram only allows apps to post to **Creator** or **Business** accounts that are **linked to a Facebook
Page**. Both are free switches.

1. **Switch to a professional account.** In the Instagram app: your profile → **☰** → **Settings and
   activity** → **Account type and tools** → **Switch to professional account** → choose **Creator** (or
   Business).
   - If you see "Switch to personal account" there, you are already professional.
2. **Link your Facebook Page.** Instagram app → **Edit profile** → **Page** → **Connect** → pick your Page.
   - Or from Facebook: your Page → **Settings** → **Linked accounts** → **Instagram** → **Connect**.

---

## Part A. Your Google app, for YouTube (10–15 minutes)

1. Open <https://console.cloud.google.com/>. Sign in with the Google account that **owns your YouTube channel**.
2. **Make a project.** Click the project picker at the top → **New project** → name it `PostKaro` →
   **Create**. Then make sure `PostKaro` is selected at the top.
3. **Switch on YouTube.** In the search bar type **YouTube Data API v3** → open it → **Enable**.
4. **Set up the login screen.** Menu ☰ → **Google Auth platform** (if it says "not configured yet", click
   **Get started**):
   - **App name:** `PostKaro`. **User support email:** yours → Next
   - **Audience:** **External** → Next
   - **Contact information:** your email → Next
   - Tick that you agree → **Continue** → **Create**
5. **Add the YouTube permission.** **Data Access** → **Add or remove scopes** → find
   `.../auth/youtube` ("Manage your YouTube account") → tick it → **Update** → **Save**.
6. **Fill in Branding, then publish.** "Publish app" stays grey until the **Branding** page is complete.
   - On **Branding**, pick your **User support email** and type your email under **Developer contact
     information** (at the bottom). Click **Save**.
   - **Don't upload a logo.** A logo means Google must verify the app first.
   - Leave **App domain** (home page, privacy policy, terms) and **Authorized domains** empty.
   - Then **Audience** → **Publish app** → **Confirm**. The status must say **In production**.
   - Important: in "Testing", Google logs PostKaro out **every 7 days**.
   - If Google says the app needs verification, you can ignore it. That is only for apps used by
     strangers, and this one is just for you.
7. **Make the login key.** **Clients** → **Create client** → Application type **Desktop app** → name
   `PostKaro` → **Create**.
   - In the box that opens, click **Download JSON** right away. Google shows the secret **only once**.
8. **Give it to PostKaro.** PostKaro **⚙** → YouTube → **Choose File** → pick the downloaded
   `client_secret_….json` → **Save**.
9. **Connect.** Click **Connect YouTube**. On Google's page:
   - Pick the account that owns your channel.
   - You will see **"Google hasn't verified this app"**. That's normal: it's your own app. Click
     **Advanced** → **Go to PostKaro (unsafe)**.
   - Tick the YouTube box if there is one → **Continue**.
10. Back in PostKaro you should see **✅ YouTube: your channel name**.

---

## Part B. Your Meta app, for Instagram and Facebook (15–20 minutes)

1. **Become a Meta developer.** Open <https://developers.facebook.com/> and log in with the Facebook
   account that **manages your Page**. Click **Get started**, confirm your phone and email, and pick an
   occupation (any one).
2. **Create the app.** **My Apps** → **Create app**:
   - **App details:** name `PostKaro`, your email → Next
   - **Use cases:** pick **Other** (at the bottom) → Next. Then **App type: Business** → Next.
   - If Meta asks about a **business portfolio**: choose **"I don't want to connect a business portfolio
     yet"**.
   - **Create app**, and enter your Facebook password if asked.

   If your screen offers **use cases** instead of "Other", pick **Manage everything on your Page** and
   **Manage messaging & content on Instagram**.
3. **Add Facebook login.** In the app's dashboard: **Add product** → **Facebook Login for Business** →
   **Set up**.
   - Then **Facebook Login for Business** → **Settings** → **Valid OAuth Redirect URIs** → paste exactly
     `http://localhost:8765/oauth/meta` → **Save changes**.
   - PostKaro's ⚙ page shows this address too, in case you changed the port.
   - If Meta refuses an `http` address there, skip this step: `localhost` is allowed by itself while the
     app is in Development mode.
4. **Add Instagram.** **Add product** → **Instagram** → **API setup with Facebook login** → **Set up**.
5. **Copy the ID and secret.** **App settings** → **Basic**:
   - copy the **App ID**;
   - click **Show** next to **App Secret** (enter your Facebook password) and copy it.
6. **Leave the app in Development mode.** Don't switch it to Live. As the app's admin you can use every
   permission for your own Page and Instagram without any review.
7. **Give it to PostKaro.** PostKaro **⚙** → Instagram and Facebook Page → paste the **App ID** and **App
   Secret** → **Save**.
8. **Connect.** Click **Connect Facebook and Instagram**. On Meta's page:
   - **Continue** as you.
   - When it asks which Pages and Instagram accounts PostKaro may use, **pick your Page and its Instagram**.
   - Allow everything it asks.
9. Back in PostKaro you should see **✅ Facebook: your Page** and **✅ Instagram: @your_handle**.

---

## Part C. Check it works

1. Run `python3 run.py status`. Every account should show `[ok]`.
2. **Add your channel names** under **My channels** on the ⚙ page, so your own videos don't get the "not
   your video" warning. Use the exact names, for example the channel name ClipKaro shows for your videos.
3. **A quiet first test on YouTube:**
   - On the ⚙ page set **YouTube visibility** to **unlisted**, and save.
   - Open a clip on the **Post** page, untick Instagram and Facebook, and leave **When** empty.
   - Press **Schedule all**.
   - Within a minute or two, **Posted** shows the link.
   - Then set visibility back to **public**.
4. **Instagram and Facebook** have no "unlisted". Post one real clip, or post one and delete it afterwards
   in the app.

---

## When something goes wrong

| You see | Fix |
|---|---|
| "Google hasn't verified this app" | Normal for your own app. Click **Advanced → Go to PostKaro (unsafe)**. |
| "Access blocked: … has not completed the Google verification process" or "only test users" | The app is still in **Testing**. Google Auth platform → **Audience** → **Publish app**. |
| `redirect_uri_mismatch` (Google) | You made a "Web application" client. Make a **Desktop app** client (Part A, step 7) and save its JSON instead. |
| YouTube login stops working after a week | The app is in Testing. Publish it (Part A, step 6), then **Reconnect**. |
| "URL blocked" or "redirect URI is not whitelisted" (Meta) | Add `http://localhost:8765/oauth/meta` to **Valid OAuth Redirect URIs** (Part B, step 3), and check the app is in **Development** mode. |
| "Instagram: none found" after connecting | Instagram isn't a Creator/Business account, or isn't linked to the Page (Part 0). Fix that, then **Reconnect**. |
| "A permission is missing" | Click **Reconnect** and, on Meta's page, allow everything and pick your Page and Instagram. |
| A yellow dot: "login ends on …" | Instagram's login lasts about 60 days, and Meta asks for a fresh login every 90 days. Click **Reconnect** on the ⚙ page; it takes a minute. PostKaro warns you 7 days and 1 day before. |
| "today's YouTube allowance" is used up | Your Google project can upload 100 videos a day. It resets at midnight US Pacific time. |

**Where things are kept**
- **Your logins:** an encrypted file in PostKaro's data folder. Its key is in your computer's password
  store (GNOME Keyring on Linux, Keychain on macOS, Credential Manager on Windows).
- **Your app secrets:** inside that same encrypted file.
- **Disconnect** on the ⚙ page deletes a login and asks Google or Meta to cancel PostKaro's access.
