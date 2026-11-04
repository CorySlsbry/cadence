import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { publish, type BlotatoAccount, type Platform } from "@/lib/blotato";

const Body = z.object({
  jobId: z.string().uuid(),
  platforms: z.array(z.enum(["tiktok", "youtube", "instagram"])).min(1),
  // Edited per-platform captions from the UI: {tiktok:{caption,hashtags,mentions}, youtube:{title,description,hashtags}, ...}
  captions: z.record(z.string(), z.any()),
});

function postText(platform: Platform, block: Record<string, unknown>): string {
  const arr = (v: unknown) => (Array.isArray(v) ? (v as string[]) : []);
  if (platform === "youtube") {
    return [block.description, arr(block.hashtags).join(" ")].filter(Boolean).join("\n\n").trim();
  }
  const extras = [...arr(block.mentions), ...arr(block.hashtags)].join(" ");
  return [block.caption, extras].filter(Boolean).join("\n\n").trim();
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: z.infer<typeof Body>;
  try {
    body = Body.parse(await request.json());
  } catch {
    return NextResponse.json({ error: "invalid request body" }, { status: 422 });
  }

  // Blotato key + connected accounts (server-side only).
  const { data: profile } = await supabase
    .from("profiles")
    .select("blotato_api_key, blotato_accounts")
    .eq("id", user.id)
    .single();
  if (!profile?.blotato_api_key) {
    return NextResponse.json({ error: "Connect your Blotato account first." }, { status: 400 });
  }
  const accounts = (profile.blotato_accounts ?? []) as BlotatoAccount[];

  // The finished render — RLS guarantees it's this user's job.
  const { data: job } = await supabase
    .from("render_jobs")
    .select("output_path, status")
    .eq("id", body.jobId)
    .single();
  if (!job?.output_path || job.status !== "done") {
    return NextResponse.json({ error: "Render isn't finished yet." }, { status: 400 });
  }

  // Sign the private output so Blotato can fetch it (the owner may read their own object).
  const { data: signed } = await supabase.storage.from("outputs").createSignedUrl(job.output_path, 7200);
  if (!signed?.signedUrl) {
    return NextResponse.json({ error: "Could not create a video URL for publishing." }, { status: 500 });
  }

  const results: { platform: Platform; ok: boolean; id?: string | null; error?: string }[] = [];
  for (const platform of body.platforms) {
    const acct = accounts.find((a) => a.platform === platform);
    if (!acct) {
      results.push({ platform, ok: false, error: `No ${platform} account connected in Blotato.` });
      continue;
    }
    const block = (body.captions?.[platform] ?? {}) as Record<string, unknown>;
    try {
      const r = await publish(profile.blotato_api_key, {
        accountId: acct.accountId,
        platform,
        text: postText(platform, block),
        videoUrl: signed.signedUrl,
        title: typeof block.title === "string" ? block.title : undefined,
      });
      results.push({ platform, ok: true, id: r.postSubmissionId ?? r.id ?? null });
    } catch (e) {
      results.push({ platform, ok: false, error: e instanceof Error ? e.message : "publish failed" });
    }
  }

  return NextResponse.json({ results });
}
