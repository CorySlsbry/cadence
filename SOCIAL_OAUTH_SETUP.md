# Direct social OAuth — setup (per platform)

Cadence now has a built-in per-user social OAuth connect flow (separate from Blotato) for
**YouTube, TikTok, Instagram**. The code (routes, encrypted token vault, `/connections` UI)
is deployed and waiting on each platform's app credentials. Each card shows **"Setup needed"**
until its `CADENCE_<PLATFORM>_*` secrets are mounted on `cadence-web`.

For every platform the **redirect/callback URI** is:

```
https://clouthook.com/api/social/oauth/<platform>/callback
```

(`<platform>` = `youtube` | `tiktok` | `instagram`). Register that EXACT URI on the platform.

After you create an app and have its credentials, add them as secrets + mount on the web
service (replace the values):

```bash
# example for youtube — repeat per platform
printf '%s' '<CLIENT_ID>'     | gcloud secrets create cadence-youtube-client-id     --data-file=- --project=builder-ai-497610
printf '%s' '<CLIENT_SECRET>' | gcloud secrets create cadence-youtube-client-secret --data-file=- --project=builder-ai-497610
for s in cadence-youtube-client-id cadence-youtube-client-secret; do
  gcloud secrets add-iam-policy-binding $s --member="serviceAccount:cadence-run@builder-ai-497610.iam.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor --project=builder-ai-497610; done
gcloud run services update cadence-web --region=us-west1 --project=builder-ai-497610 \
  --update-secrets="CADENCE_YOUTUBE_CLIENT_ID=cadence-youtube-client-id:latest,CADENCE_YOUTUBE_CLIENT_SECRET=cadence-youtube-client-secret:latest"
```

Env var names the code reads:
| Platform | Env vars |
|---|---|
| YouTube | `CADENCE_YOUTUBE_CLIENT_ID`, `CADENCE_YOUTUBE_CLIENT_SECRET` |
| TikTok | `CADENCE_TIKTOK_CLIENT_KEY`, `CADENCE_TIKTOK_CLIENT_SECRET` |
| Instagram | `CADENCE_INSTAGRAM_CLIENT_ID`, `CADENCE_INSTAGRAM_CLIENT_SECRET` |

---

## YouTube (easiest — start here; you already have GCP)
1. GCP Console → **APIs & Services → Library** → enable **YouTube Data API v3**.
2. **OAuth consent screen**: External; app name "Cadence"; add scopes
   `.../auth/youtube.upload` + `.../auth/youtube.readonly`; add yourself as a test user (or publish).
3. **Credentials → Create credentials → OAuth client ID → Web application**.
   - Authorized redirect URI = `…/api/social/oauth/youtube/callback` (above).
   - Copy the **Client ID** + **Client secret** → mount as `CADENCE_YOUTUBE_CLIENT_ID/SECRET`.
- Scopes requested: `youtube.upload youtube.readonly`. We request `access_type=offline` + `prompt=consent` so a refresh token is returned.

## TikTok (needs app review for posting)
1. **developers.tiktok.com** → Manage apps → create an app.
2. Add products **Login Kit** and **Content Posting API**.
3. Redirect URI = `…/api/social/oauth/tiktok/callback`.
4. Request scopes `user.info.basic`, `video.publish`, `video.upload` — **`video.publish` requires TikTok's audit/review** before it works for non-test users.
5. Copy **Client key** + **Client secret** → mount as `CADENCE_TIKTOK_CLIENT_KEY/SECRET`. (PKCE is handled in code.)

## Instagram (most involved — Business/Creator account + review)
1. **developers.facebook.com** → create an app (type **Business**).
2. Add the **Instagram** product → use **"Instagram API with Instagram Login"** (business login).
3. In the Instagram business-login settings, set the OAuth redirect URI = `…/api/social/oauth/instagram/callback`.
4. Permissions: `instagram_business_basic`, `instagram_business_content_publish` — content publishing requires **App Review** + an **Instagram Business/Creator account**.
5. Copy the **Instagram app ID** + **app secret** → mount as `CADENCE_INSTAGRAM_CLIENT_ID/SECRET`. (Code exchanges the short-lived token for a ~60-day long-lived token automatically.)

---

## What's built vs. pending
- **Built + deployed:** the OAuth connect flow (start → consent → callback → encrypted token store), the `/connections` "Social accounts" UI, disconnect, and per-platform token exchange (incl. TikTok PKCE + Instagram long-lived exchange). Tokens live in `social_connections` (AES-256-GCM, service-role only).
- **Pending (needs your apps):** mount each platform's `CADENCE_*` secrets (above) to flip the card from "Setup needed" → "Connect".
- **Next phase (after connect works):** wire **publishing** through these direct connections (upload the rendered video via each platform's content API), so users can post without Blotato. That's a separate per-platform build (each posting API differs); the connections built here are the prerequisite.

## X (added 2026-06-11)
- developer.x.com → pay-per-use tier → create app → OAuth 2.0: **Web App (confidential)**.
- Callback: `https://clouthook.com/api/social/oauth/x/callback` · Website: `https://clouthook.com`
- Secrets: `CADENCE_X_CLIENT_ID` / `CADENCE_X_CLIENT_SECRET`
- Scopes requested: tweet.read tweet.write users.read media.write offline.access (2h tokens, auto-refresh).
- Publish: v2 chunked media upload + POST /2/tweets (live same-day; ~$0.015/post).

## LinkedIn (added 2026-06-11)
- linkedin.com/developers → create app (needs a LinkedIn **Company Page** to bind to) → request
  **"Share on LinkedIn"** + **"Sign In with LinkedIn using OpenID Connect"** products (instant self-serve).
- Callback: `https://clouthook.com/api/social/oauth/linkedin/callback`
- Secrets: `CADENCE_LINKEDIN_CLIENT_ID` / `CADENCE_LINKEDIN_CLIENT_SECRET`
- Tokens last 60 days, no refresh on the standard tier → users reconnect every ~2 months.
- Publish: rest/videos initializeUpload → PUT parts → finalizeUpload → poll AVAILABLE → rest/posts.

## Facebook (added 2026-06-11)
- developers.facebook.com → create app (Business type) → add **Facebook Login for Business**.
- Callback: `https://clouthook.com/api/social/oauth/facebook/callback`
- Secrets: `CADENCE_FACEBOOK_CLIENT_ID` / `CADENCE_FACEBOOK_CLIENT_SECRET`
- Scopes: pages_show_list, pages_manage_posts, pages_read_engagement, business_management —
  Advanced Access for these needs Meta **App Review** (own pages work in Dev Mode immediately).
- Publish: first managed Page via /me/accounts → graph-video /{page}/videos (page token).

## Instagram (publish path added 2026-06-11; connect existed)
- Same Meta app: add **Instagram API with Instagram Login** product.
- Callback: `https://clouthook.com/api/social/oauth/instagram/callback`
- Secrets: `CADENCE_INSTAGRAM_CLIENT_ID` / `CADENCE_INSTAGRAM_CLIENT_SECRET`
- Account must be **Professional** (Business/Creator). App Review for instagram_business_content_publish.
- Publish: Reels container from a 1h signed video URL → poll FINISHED → media_publish → permalink.

## YouTube (publish path added 2026-06-11; connect existed)
- console.cloud.google.com → OAuth client (Web) + enable **YouTube Data API v3**.
- Callback: `https://clouthook.com/api/social/oauth/youtube/callback`
- Secrets: `CADENCE_YOUTUBE_CLIENT_ID` / `CADENCE_YOUTUBE_CLIENT_SECRET`
- Unverified app: uploads land **private** (flip in YouTube Studio). Start OAuth verification early (2-8 wks).
- Publish: resumable upload, snippet+status, privacyStatus=private.
