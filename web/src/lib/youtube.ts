// YouTube Data API v3 helpers for outlier discovery. The "outlier score" follows
// Sandy Lee's method (views vs the channel's own baseline × 100), with the channel
// median of recent uploads as the baseline — robust to one mega-hit skewing a mean,
// and computable without first-48h history (which the API can't backfill).

const API = "https://www.googleapis.com/youtube/v3";

export type YtChannel = {
  channelId: string;
  title: string;
  handle: string | null;
  thumbnailUrl: string | null;
  uploadsPlaylistId: string | null;
};

export type YtVideo = {
  videoId: string;
  title: string;
  thumbnailUrl: string | null;
  publishedAt: string;
  views: number;
  durationSec: number;
};

function key(): string {
  const k = process.env.YOUTUBE_API_KEY;
  if (!k) throw new Error("YOUTUBE_API_KEY not configured");
  return k;
}

/** Accepts @handle, handle, UC… id, or any youtube.com channel URL form we can parse. */
export function parseChannelInput(raw: string): { kind: "id" | "handle"; value: string } | null {
  const s = raw.trim();
  if (!s) return null;
  const idMatch = s.match(/(UC[0-9A-Za-z_-]{22})/);
  if (idMatch) return { kind: "id", value: idMatch[1] };
  const urlHandle = s.match(/youtube\.com\/@([A-Za-z0-9._-]+)/i);
  if (urlHandle) return { kind: "handle", value: urlHandle[1] };
  const at = s.match(/^@?([A-Za-z0-9._-]{3,})$/);
  if (at) return { kind: "handle", value: at[1] };
  return null;
}

export async function resolveChannel(input: string): Promise<YtChannel | null> {
  const parsed = parseChannelInput(input);
  if (!parsed) return null;
  const param = parsed.kind === "id" ? `id=${parsed.value}` : `forHandle=${encodeURIComponent(parsed.value)}`;
  const res = await fetch(
    `${API}/channels?part=snippet,contentDetails&${param}&key=${key()}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`youtube channels.list ${res.status}`);
  const data = (await res.json()) as {
    items?: {
      id: string;
      snippet: { title: string; customUrl?: string; thumbnails?: { medium?: { url?: string }; default?: { url?: string } } };
      contentDetails?: { relatedPlaylists?: { uploads?: string } };
    }[];
  };
  const item = data.items?.[0];
  if (!item) return null;
  return {
    channelId: item.id,
    title: item.snippet.title,
    handle: item.snippet.customUrl ?? null,
    thumbnailUrl: item.snippet.thumbnails?.medium?.url ?? item.snippet.thumbnails?.default?.url ?? null,
    uploadsPlaylistId: item.contentDetails?.relatedPlaylists?.uploads ?? null,
  };
}

function isoDurationToSec(iso: string): number {
  const m = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!m) return 0;
  return (parseInt(m[1] ?? "0", 10) * 3600) + (parseInt(m[2] ?? "0", 10) * 60) + parseInt(m[3] ?? "0", 10);
}

/** Recent uploads with view counts (2 API units: playlistItems + videos). */
export async function fetchRecentVideos(uploadsPlaylistId: string, max = 25): Promise<YtVideo[]> {
  const pl = await fetch(
    `${API}/playlistItems?part=contentDetails&playlistId=${uploadsPlaylistId}&maxResults=${Math.min(max, 50)}&key=${key()}`,
    { cache: "no-store" },
  );
  if (!pl.ok) throw new Error(`youtube playlistItems.list ${pl.status}`);
  const plData = (await pl.json()) as { items?: { contentDetails: { videoId: string } }[] };
  const ids = (plData.items ?? []).map((i) => i.contentDetails.videoId).slice(0, max);
  if (!ids.length) return [];

  const vids = await fetch(
    `${API}/videos?part=snippet,statistics,contentDetails&id=${ids.join(",")}&key=${key()}`,
    { cache: "no-store" },
  );
  if (!vids.ok) throw new Error(`youtube videos.list ${vids.status}`);
  const vData = (await vids.json()) as {
    items?: {
      id: string;
      snippet: { title: string; publishedAt: string; thumbnails?: { medium?: { url?: string }; high?: { url?: string } } };
      statistics?: { viewCount?: string };
      contentDetails?: { duration?: string };
    }[];
  };
  return (vData.items ?? []).map((v) => ({
    videoId: v.id,
    title: v.snippet.title,
    thumbnailUrl: v.snippet.thumbnails?.high?.url ?? v.snippet.thumbnails?.medium?.url ?? null,
    publishedAt: v.snippet.publishedAt,
    views: parseInt(v.statistics?.viewCount ?? "0", 10),
    durationSec: isoDurationToSec(v.contentDetails?.duration ?? ""),
  }));
}

export function median(nums: number[]): number {
  const xs = [...nums].sort((a, b) => a - b);
  if (!xs.length) return 0;
  const mid = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[mid] : (xs[mid - 1] + xs[mid]) / 2;
}

/** Sandy-scale outlier score: views vs channel baseline × 100 (200 = 2× typical). */
export function outlierScore(views: number, baseline: number): number {
  if (baseline <= 0) return 0;
  return Math.round((views / baseline) * 1000) / 10;
}

/** Channel baseline = median views of uploads old enough (≥3 days) to have settled. */
export function channelBaseline(videos: YtVideo[], now = Date.now()): number {
  const settled = videos.filter((v) => now - Date.parse(v.publishedAt) >= 3 * 86400_000);
  return median((settled.length >= 5 ? settled : videos).map((v) => v.views));
}
