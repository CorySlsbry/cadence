import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { resolveChannel } from "@/lib/youtube";

// Watched YouTube channels — the outlier-discovery source list (cap 10, Sandy's number).

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data } = await supabase
    .from("watched_channels").select("*")
    .eq("user_id", user.id).order("created_at", { ascending: true });
  return NextResponse.json({ channels: data ?? [] });
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { input?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  const input = (body.input ?? "").trim();
  if (!input) return NextResponse.json({ error: "channel handle or URL required" }, { status: 422 });

  const { count } = await supabase
    .from("watched_channels").select("id", { count: "exact", head: true })
    .eq("user_id", user.id);
  if ((count ?? 0) >= 10) {
    return NextResponse.json({ error: "channel limit reached (10) — remove one first" }, { status: 422 });
  }

  let ch;
  try {
    ch = await resolveChannel(input);
  } catch (e) {
    return NextResponse.json({ error: `lookup failed: ${e instanceof Error ? e.message : "unknown"}` }, { status: 502 });
  }
  if (!ch) return NextResponse.json({ error: "channel not found — paste the @handle or channel URL" }, { status: 404 });

  const { data, error } = await supabase
    .from("watched_channels")
    .upsert(
      {
        user_id: user.id,
        channel_id: ch.channelId,
        title: ch.title,
        handle: ch.handle,
        thumbnail_url: ch.thumbnailUrl,
        uploads_playlist_id: ch.uploadsPlaylistId,
      },
      { onConflict: "user_id,channel_id" },
    )
    .select()
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ channel: data });
}

export async function DELETE(req: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { id?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  if (!body.id) return NextResponse.json({ error: "id required" }, { status: 422 });

  const { data: ch } = await supabase
    .from("watched_channels").select("channel_id")
    .eq("user_id", user.id).eq("id", body.id).maybeSingle();
  if (ch) {
    await supabase.from("outlier_videos").delete().eq("user_id", user.id).eq("channel_id", ch.channel_id);
  }
  const { error } = await supabase.from("watched_channels").delete().eq("user_id", user.id).eq("id", body.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
