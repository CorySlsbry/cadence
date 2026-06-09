import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { channelBaseline, fetchRecentVideos, outlierScore } from "@/lib/youtube";

// Outlier feed: GET = ranked list; POST = refresh all watched channels (pull recent
// uploads, recompute the channel baseline, upsert scored videos). 10-minute per-channel
// throttle keeps API quota + latency sane.

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const { data } = await supabase
    .from("outlier_videos").select("*")
    .eq("user_id", user.id)
    .order("outlier_score", { ascending: false })
    .limit(60);
  return NextResponse.json({ outliers: data ?? [] });
}

export async function POST() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { data: channels } = await supabase
    .from("watched_channels").select("*").eq("user_id", user.id);
  if (!channels?.length) return NextResponse.json({ refreshed: 0, outliers: [] });

  const cutoff = Date.now() - 10 * 60_000;
  let refreshed = 0;
  for (const ch of channels) {
    if (!ch.uploads_playlist_id) continue;
    if (ch.last_checked_at && Date.parse(ch.last_checked_at) > cutoff) continue;
    try {
      const videos = await fetchRecentVideos(ch.uploads_playlist_id, 25);
      if (!videos.length) continue;
      const baseline = channelBaseline(videos);
      const rows = videos.map((v) => ({
        user_id: user.id,
        channel_id: ch.channel_id,
        channel_title: ch.title,
        video_id: v.videoId,
        title: v.title,
        thumbnail_url: v.thumbnailUrl,
        published_at: v.publishedAt,
        views: v.views,
        channel_median_views: baseline,
        outlier_score: outlierScore(v.views, baseline),
      }));
      await supabase.from("outlier_videos").upsert(rows, { onConflict: "user_id,video_id", ignoreDuplicates: false });
      await supabase
        .from("watched_channels")
        .update({ median_views: baseline, last_checked_at: new Date().toISOString() })
        .eq("id", ch.id);
      refreshed += 1;
    } catch (e) {
      console.error(`outlier refresh failed for ${ch.title}:`, e);
    }
  }

  const { data: outliers } = await supabase
    .from("outlier_videos").select("*")
    .eq("user_id", user.id)
    .order("outlier_score", { ascending: false })
    .limit(60);
  return NextResponse.json({ refreshed, outliers: outliers ?? [] });
}
