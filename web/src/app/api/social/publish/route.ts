import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { SOCIAL, type SocialPlatform } from "@/lib/social-oauth";

// Direct publish of a finished render to a connected social account. X first
// (v2 chunked media upload + POST /2/tweets); other platforms join as their
// upload APIs get wired. Runs server-side with the user's own platform tokens.

export const maxDuration = 300; // video upload + processing poll

const Body = z.object({
  platform: z.enum(["x", "youtube", "linkedin", "facebook", "instagram"]),
  jobId: z.string().uuid(),
  caption: z.string().max(280).default(""),
});

const LI_HEADERS = (access: string) => ({
  authorization: `Bearer ${access}`,
  "LinkedIn-Version": "202505",
  "X-Restli-Protocol-Version": "2.0.0",
  "content-type": "application/json",
});

async function linkedinPublish(access: string, personId: string, video: Buffer, caption: string): Promise<string> {
  const owner = `urn:li:person:${personId}`;
  const initRes = await fetch("https://api.linkedin.com/rest/videos?action=initializeUpload", {
    method: "POST",
    headers: LI_HEADERS(access),
    body: JSON.stringify({ initializeUploadRequest: {
      owner, fileSizeBytes: video.length, uploadCaptions: false, uploadThumbnail: false,
    } }),
  });
  const init = await initRes.json().catch(() => ({}));
  const videoUrn: string | undefined = init?.value?.video;
  const parts: { uploadUrl: string; firstByte: number; lastByte: number }[] =
    init?.value?.uploadInstructions ?? [];
  if (!initRes.ok || !videoUrn || parts.length === 0) {
    throw new Error(`LinkedIn upload init failed (${initRes.status}): ${JSON.stringify(init).slice(0, 200)}`);
  }
  const etags: string[] = [];
  for (const p of parts) {
    const r = await fetch(p.uploadUrl, {
      method: "PUT",
      headers: { "content-type": "application/octet-stream" },
      body: Uint8Array.from(video.subarray(p.firstByte, p.lastByte + 1)),
    });
    if (!r.ok) throw new Error(`LinkedIn upload part failed (${r.status})`);
    const etag = r.headers.get("etag");
    if (etag) etags.push(etag);
  }
  const finRes = await fetch("https://api.linkedin.com/rest/videos?action=finalizeUpload", {
    method: "POST",
    headers: LI_HEADERS(access),
    body: JSON.stringify({ finalizeUploadRequest: { video: videoUrn, uploadToken: "", uploadedPartIds: etags } }),
  });
  if (!finRes.ok) {
    const t = await finRes.text().catch(() => "");
    throw new Error(`LinkedIn finalize failed (${finRes.status}): ${t.slice(0, 200)}`);
  }
  // Wait for transcode before posting (posting an unprocessed video 404s).
  const deadline = Date.now() + 180_000;
  for (;;) {
    const st = await fetch(`https://api.linkedin.com/rest/videos/${encodeURIComponent(videoUrn)}`, {
      headers: LI_HEADERS(access),
    });
    const sj = await st.json().catch(() => ({}));
    if (sj.status === "AVAILABLE") break;
    if (sj.status === "PROCESSING_FAILED") throw new Error("LinkedIn rejected the video during processing");
    if (Date.now() > deadline) throw new Error("LinkedIn video processing timed out");
    await new Promise((res) => setTimeout(res, 4000));
  }
  const postRes = await fetch("https://api.linkedin.com/rest/posts", {
    method: "POST",
    headers: LI_HEADERS(access),
    body: JSON.stringify({
      author: owner,
      commentary: caption || "New video",
      visibility: "PUBLIC",
      distribution: { feedDistribution: "MAIN_FEED", targetEntities: [], thirdPartyDistributionChannels: [] },
      content: { media: { id: videoUrn, title: (caption || "CloutHook short").slice(0, 60) } },
      lifecycleState: "PUBLISHED",
      isReshareDisabledByAuthor: false,
    }),
  });
  const postUrn = postRes.headers.get("x-restli-id");
  if (!postRes.ok || !postUrn) {
    const t = await postRes.text().catch(() => "");
    throw new Error(`LinkedIn post failed (${postRes.status}): ${t.slice(0, 200)}`);
  }
  return `https://www.linkedin.com/feed/update/${postUrn}/`;
}

async function facebookPublish(userToken: string, video: Buffer, caption: string): Promise<string> {
  const pagesRes = await fetch(
    "https://graph.facebook.com/v23.0/me/accounts?fields=id,name,access_token&access_token=" +
      encodeURIComponent(userToken),
  );
  const pages = await pagesRes.json().catch(() => ({}));
  const page = pages?.data?.[0];
  if (!pagesRes.ok || !page?.access_token) {
    throw new Error("no Facebook Page on this account — posting goes to a Page you manage");
  }
  const form = new FormData();
  form.set("description", caption);
  form.set("access_token", page.access_token);
  form.set("source", new Blob([Uint8Array.from(video)], { type: "video/mp4" }), "video.mp4");
  const upRes = await fetch(`https://graph-video.facebook.com/v23.0/${page.id}/videos`, {
    method: "POST",
    body: form,
  });
  const up = await upRes.json().catch(() => ({}));
  if (!upRes.ok || !up.id) {
    throw new Error(`Facebook upload failed (${upRes.status}): ${JSON.stringify(up).slice(0, 200)}`);
  }
  return `https://www.facebook.com/watch/?v=${up.id}`;
}

async function instagramPublish(access: string, igUserId: string, videoUrl: string, caption: string): Promise<string> {
  const createRes = await fetch(`https://graph.instagram.com/v23.0/${igUserId}/media?` + new URLSearchParams({
    media_type: "REELS", video_url: videoUrl, caption, access_token: access,
  }).toString(), { method: "POST" });
  const created = await createRes.json().catch(() => ({}));
  if (!createRes.ok || !created.id) {
    throw new Error(`Instagram container failed (${createRes.status}): ${JSON.stringify(created).slice(0, 200)}`);
  }
  const deadline = Date.now() + 240_000;
  for (;;) {
    const st = await fetch(
      `https://graph.instagram.com/v23.0/${created.id}?fields=status_code&access_token=${encodeURIComponent(access)}`,
    );
    const sj = await st.json().catch(() => ({}));
    if (sj.status_code === "FINISHED") break;
    if (sj.status_code === "ERROR") throw new Error("Instagram rejected the video during processing");
    if (Date.now() > deadline) throw new Error("Instagram processing timed out");
    await new Promise((res) => setTimeout(res, 5000));
  }
  const pubRes = await fetch(`https://graph.instagram.com/v23.0/${igUserId}/media_publish?` + new URLSearchParams({
    creation_id: created.id, access_token: access,
  }).toString(), { method: "POST" });
  const pub = await pubRes.json().catch(() => ({}));
  if (!pubRes.ok || !pub.id) {
    throw new Error(`Instagram publish failed (${pubRes.status}): ${JSON.stringify(pub).slice(0, 200)}`);
  }
  const permRes = await fetch(
    `https://graph.instagram.com/v23.0/${pub.id}?fields=permalink&access_token=${encodeURIComponent(access)}`,
  );
  const perm = await permRes.json().catch(() => ({}));
  return (perm.permalink as string) || "https://www.instagram.com/";
}

const X_UPLOAD = "https://api.x.com/2/media/upload";
const CHUNK = 4 * 1024 * 1024;

async function xUploadVideo(access: string, video: Buffer): Promise<string> {
  const auth = { authorization: `Bearer ${access}` };

  const initRes = await fetch(X_UPLOAD, {
    method: "POST",
    headers: { ...auth, "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      command: "INIT",
      total_bytes: String(video.length),
      media_type: "video/mp4",
      media_category: "tweet_video",
    }).toString(),
  });
  const init = await initRes.json().catch(() => ({}));
  const mediaId: string | undefined = init?.data?.id ?? init?.media_id_string;
  if (!initRes.ok || !mediaId) {
    throw new Error(`X media INIT failed (${initRes.status}): ${JSON.stringify(init).slice(0, 200)}`);
  }

  for (let i = 0; i * CHUNK < video.length; i++) {
    const part = video.subarray(i * CHUNK, Math.min((i + 1) * CHUNK, video.length));
    const form = new FormData();
    form.set("command", "APPEND");
    form.set("media_id", mediaId);
    form.set("segment_index", String(i));
    form.set("media", new Blob([Uint8Array.from(part)]), "chunk.mp4");
    const r = await fetch(X_UPLOAD, { method: "POST", headers: auth, body: form });
    if (!r.ok) throw new Error(`X media APPEND ${i} failed (${r.status})`);
  }

  const finRes = await fetch(X_UPLOAD, {
    method: "POST",
    headers: { ...auth, "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ command: "FINALIZE", media_id: mediaId }).toString(),
  });
  const fin = await finRes.json().catch(() => ({}));
  if (!finRes.ok) throw new Error(`X media FINALIZE failed (${finRes.status}): ${JSON.stringify(fin).slice(0, 200)}`);

  // Poll processing (video transcode) until X says it's ready.
  let info = fin?.data?.processing_info ?? fin?.processing_info;
  const deadline = Date.now() + 240_000;
  while (info && info.state !== "succeeded") {
    if (info.state === "failed") throw new Error("X rejected the video during processing");
    if (Date.now() > deadline) throw new Error("X video processing timed out");
    await new Promise((res) => setTimeout(res, Math.max(1, info.check_after_secs ?? 2) * 1000));
    const st = await fetch(`${X_UPLOAD}?command=STATUS&media_id=${mediaId}`, { headers: auth });
    const sj = await st.json().catch(() => ({}));
    info = sj?.data?.processing_info ?? sj?.processing_info;
  }
  return mediaId;
}

async function youtubeUpload(access: string, video: Buffer, title: string): Promise<string> {
  // Resumable upload; "private" until the Google app clears OAuth verification —
  // creators can flip visibility in YouTube Studio meanwhile.
  const initRes = await fetch(
    "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${access}`,
        "content-type": "application/json",
        "x-upload-content-type": "video/mp4",
        "x-upload-content-length": String(video.length),
      },
      body: JSON.stringify({
        snippet: { title: title.slice(0, 95) || "CloutHook short", categoryId: "22" },
        status: { privacyStatus: "private", selfDeclaredMadeForKids: false },
      }),
    },
  );
  if (!initRes.ok) {
    const t = await initRes.text().catch(() => "");
    throw new Error(`YouTube upload init failed (${initRes.status}): ${t.slice(0, 200)}`);
  }
  const session = initRes.headers.get("location");
  if (!session) throw new Error("YouTube did not return an upload session");
  const upRes = await fetch(session, {
    method: "PUT",
    headers: { "content-type": "video/mp4", "content-length": String(video.length) },
    body: Uint8Array.from(video),
  });
  const up = await upRes.json().catch(() => ({}));
  if (!upRes.ok || !up.id) {
    throw new Error(`YouTube upload failed (${upRes.status}): ${JSON.stringify(up).slice(0, 200)}`);
  }
  return up.id as string;
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await req.json());
  } catch {
    return NextResponse.json({ error: "platform 'x', jobId and caption (<=280) required" }, { status: 422 });
  }
  const platform: SocialPlatform = body.platform;

  // The finished render must belong to the caller.
  const { data: job } = await supabase
    .from("render_jobs")
    .select("id, status, output_path, customization")
    .eq("id", body.jobId)
    .single();
  if (!job || job.status !== "done" || !job.output_path) {
    return NextResponse.json({ error: "render not found or not finished" }, { status: 404 });
  }

  const admin = createAdminClient();
  const { data: conn } = await admin
    .from("social_connections")
    .select("id, access_token_enc, refresh_token_enc, expires_at, username, platform_user_id")
    .eq("user_id", user.id)
    .eq("platform", platform)
    .single();
  if (!conn) {
    return NextResponse.json(
      { error: `connect your ${SOCIAL[platform].label} account first (Connections page)` },
      { status: 409 },
    );
  }

  let access = decryptSecret(conn.access_token_enc);
  const cfg = SOCIAL[platform];
  const expired = conn.expires_at && new Date(conn.expires_at).getTime() < Date.now() + 60_000;
  if (expired && conn.refresh_token_enc && cfg.refreshToken) {
    try {
      const fresh = await cfg.refreshToken(decryptSecret(conn.refresh_token_enc));
      access = fresh.access;
      await admin.from("social_connections").update({
        access_token_enc: encryptSecret(fresh.access),
        refresh_token_enc: fresh.refresh ? encryptSecret(fresh.refresh) : conn.refresh_token_enc,
        expires_at: fresh.expiresIn ? new Date(Date.now() + fresh.expiresIn * 1000).toISOString() : null,
      }).eq("id", conn.id);
    } catch {
      return NextResponse.json(
        { error: `${SOCIAL[platform].label} session expired — reconnect on the Connections page` },
        { status: 409 },
      );
    }
  }

  const { data: blob, error: dlErr } = await admin.storage.from("outputs").download(job.output_path);
  if (dlErr || !blob) return NextResponse.json({ error: "could not read the video" }, { status: 500 });
  const video = Buffer.from(await blob.arrayBuffer());
  if (video.length > 512 * 1024 * 1024) {
    return NextResponse.json({ error: "video exceeds X's 512MB limit" }, { status: 413 });
  }

  const caption =
    body.caption.trim() ||
    String((job.customization as { faceless?: { topic?: string } })?.faceless?.topic ?? "").slice(0, 270);

  try {
    if (platform === "youtube") {
      const videoId = await youtubeUpload(access, video, caption);
      return NextResponse.json({
        ok: true,
        url: `https://youtube.com/watch?v=${videoId}`,
        note: "uploaded as private — set visibility in YouTube Studio",
      });
    }
    if (platform === "linkedin") {
      if (!conn.platform_user_id) {
        return NextResponse.json({ error: "reconnect LinkedIn to refresh your profile id" }, { status: 409 });
      }
      const url = await linkedinPublish(access, conn.platform_user_id, video, caption);
      return NextResponse.json({ ok: true, url });
    }
    if (platform === "facebook") {
      const url = await facebookPublish(access, video, caption);
      return NextResponse.json({ ok: true, url });
    }
    if (platform === "instagram") {
      if (!conn.platform_user_id) {
        return NextResponse.json({ error: "reconnect Instagram to refresh your account id" }, { status: 409 });
      }
      // Instagram pulls the video from a URL — hand it a 1h signed link to the render.
      const { data: signed } = await admin.storage.from("outputs").createSignedUrl(job.output_path, 3600);
      if (!signed?.signedUrl) {
        return NextResponse.json({ error: "could not stage the video for Instagram" }, { status: 500 });
      }
      const url = await instagramPublish(access, conn.platform_user_id, signed.signedUrl, caption);
      return NextResponse.json({ ok: true, url });
    }
    const mediaId = await xUploadVideo(access, video);
    const postRes = await fetch("https://api.x.com/2/tweets", {
      method: "POST",
      headers: { authorization: `Bearer ${access}`, "content-type": "application/json" },
      body: JSON.stringify({ text: caption, media: { media_ids: [mediaId] } }),
    });
    const post = await postRes.json().catch(() => ({}));
    const tweetId: string | undefined = post?.data?.id;
    if (!postRes.ok || !tweetId) {
      throw new Error(`tweet failed (${postRes.status}): ${JSON.stringify(post).slice(0, 200)}`);
    }
    return NextResponse.json({
      ok: true,
      url: `https://x.com/${conn.username ?? "i"}/status/${tweetId}`,
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "publish failed" },
      { status: 502 },
    );
  }
}
