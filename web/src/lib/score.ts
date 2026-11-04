import { geminiJson } from "@/lib/gemini";

// The canonical Viral Score engine. ONE rubric, called by /api/score (the lead-magnet page +
// homepage demo) and — over HTTP — by the public MCP `score_video` tool and the in-page WebMCP.
// Scores from a link's metadata + an optional transcript + what the creator tells us; no GPU.

export type ScoreDimensionKey = "hook" | "pacing" | "captions" | "visuals" | "format" | "length";

export type ScoreDimension = {
  key: ScoreDimensionKey;
  label: string;
  score: number; // 0-10
  verdict: string; // one-line assessment
  fix: string; // one concrete improvement (gated behind email on the web funnel)
};

export type ScoreResult = {
  score: number; // 0-10 weighted overall, 1 decimal
  grade: string; // Viral-ready / Strong / Promising / Needs work / Rough
  summary: string;
  dimensions: ScoreDimension[];
  topFixes: string[]; // up to 3, most important first
};

export type ScoreInput = {
  platform?: string;
  title?: string;
  topic?: string;
  hook?: string;
  transcript?: string;
  thumbnailUrl?: string;
};

const WEIGHTS: Record<ScoreDimensionKey, number> = {
  hook: 0.3,
  pacing: 0.2,
  captions: 0.15,
  visuals: 0.15,
  format: 0.1,
  length: 0.1,
};
const LABELS: Record<ScoreDimensionKey, string> = {
  hook: "Hook (first 3 seconds)",
  pacing: "Pacing & retention",
  captions: "Captions",
  visuals: "Visual variety / b-roll",
  format: "Format & framing",
  length: "Length",
};
const ORDER: ScoreDimensionKey[] = ["hook", "pacing", "captions", "visuals", "format", "length"];

type RawDim = { key: ScoreDimensionKey; score: number; verdict: string; fix: string };
type RawOut = { dimensions: RawDim[]; summary: string; topFixes: string[] };

function gradeFor(s: number): string {
  if (s >= 8.5) return "Viral-ready";
  if (s >= 7) return "Strong";
  if (s >= 5.5) return "Promising";
  if (s >= 4) return "Needs work";
  return "Rough";
}

export async function scoreVideo(input: ScoreInput): Promise<ScoreResult> {
  const ctx = [
    input.platform ? `Platform: ${input.platform}` : "",
    input.title ? `Title/caption: ${input.title}` : "",
    input.hook ? `Stated hook / first line: ${input.hook}` : "",
    input.topic ? `What it's about: ${input.topic}` : "",
    input.transcript ? `Transcript:\n${input.transcript.slice(0, 6000)}` : "",
    input.thumbnailUrl ? "A thumbnail/cover image is attached." : "",
  ]
    .filter(Boolean)
    .join("\n");

  const prompt = `You are a brutally honest short-form video growth analyst (TikTok, Reels, YouTube Shorts).
Score the video below on six dimensions, 0-10 each. CALIBRATE HONESTLY — most real videos land 4-7; reserve 9-10 for genuinely exceptional, and use low scores when warranted. Judge only on the evidence given; if a dimension truly can't be assessed from the input, score it 5 and say what you'd need to see.

For each dimension give the score (0-10), a one-line verdict, and one specific, actionable fix.
Use these exact keys:
- hook: does the first 3 seconds stop the scroll? (the single biggest driver of reach)
- pacing: cuts, energy, dead air, retention shape
- captions: are on-screen captions present, readable, well-timed?
- visuals: b-roll / visual variety vs a static talking head
- format: vertical 9:16, framing, platform-safe zones
- length: is the duration right for this platform and idea?

${ctx}

Return STRICT JSON:
{
  "summary": "1-2 sentences naming the single most important thing helping or hurting this video",
  "topFixes": ["the 3 highest-leverage fixes, most important first"],
  "dimensions": [
    {"key":"hook","score":0,"verdict":"...","fix":"..."},
    {"key":"pacing","score":0,"verdict":"...","fix":"..."},
    {"key":"captions","score":0,"verdict":"...","fix":"..."},
    {"key":"visuals","score":0,"verdict":"...","fix":"..."},
    {"key":"format","score":0,"verdict":"...","fix":"..."},
    {"key":"length","score":0,"verdict":"...","fix":"..."}
  ]
}`;

  const raw = await geminiJson<RawOut>({
    model: "gemini-2.5-flash",
    temperature: 0.4,
    prompt,
    imageUrl: input.thumbnailUrl,
  });

  const byKey = new Map((raw.dimensions ?? []).map((d) => [d.key, d]));
  const dimensions: ScoreDimension[] = ORDER.map((key) => {
    const d = byKey.get(key);
    const n = Number(d?.score);
    const score = Number.isFinite(n) ? Math.max(0, Math.min(10, n)) : 5; // guard NaN from "8/10"/"N/A"
    return {
      key,
      label: LABELS[key],
      score: Math.round(score * 10) / 10,
      verdict: (d?.verdict ?? "Not enough signal to assess this one.").trim(),
      fix: (d?.fix ?? "").trim(),
    };
  });
  const overall = dimensions.reduce((sum, d) => sum + d.score * WEIGHTS[d.key], 0);
  const score = Number.isFinite(overall) ? Math.round(overall * 10) / 10 : 0;
  return {
    score,
    grade: gradeFor(score),
    summary: (raw.summary ?? "").trim(),
    dimensions,
    topFixes: (raw.topFixes ?? []).slice(0, 3).map((s) => String(s).trim()).filter(Boolean),
  };
}

// The teaser is what the public funnel shows BEFORE email: scores + verdicts + one fix.
// The remaining fixes + the emailed report unlock with an email (jaredrhod: value first, capture at the value moment).
export type ScoreTeaser = {
  score: number;
  grade: string;
  summary: string;
  dimensions: { key: ScoreDimensionKey; label: string; score: number; verdict: string }[];
  topFix: string | null;
  lockedFixes: number;
};

export function toTeaser(r: ScoreResult): ScoreTeaser {
  return {
    score: r.score,
    grade: r.grade,
    summary: r.summary,
    dimensions: r.dimensions.map(({ key, label, score, verdict }) => ({ key, label, score, verdict })),
    topFix: r.topFixes[0] ?? r.dimensions[0]?.fix ?? null,
    lockedFixes: Math.max(0, r.dimensions.filter((d) => d.fix).length + Math.max(0, r.topFixes.length - 1)),
  };
}

// SSRF-safe metadata: we only ever call a fixed provider oEmbed endpoint (passing the user URL as a
// query param), never fetch the user's URL directly. Unknown hosts get no metadata, not a fetch.
export type VideoMeta = { platform?: string; title?: string; thumbnailUrl?: string };

const OEMBED: { test: RegExp; platform: string; endpoint: ((u: string) => string) | null }[] = [
  { test: /(?:youtube\.com|youtu\.be)/i, platform: "YouTube", endpoint: (u) => `https://www.youtube.com/oembed?format=json&url=${encodeURIComponent(u)}` },
  { test: /tiktok\.com/i, platform: "TikTok", endpoint: (u) => `https://www.tiktok.com/oembed?url=${encodeURIComponent(u)}` },
  { test: /vimeo\.com/i, platform: "Vimeo", endpoint: (u) => `https://vimeo.com/api/oembed.json?url=${encodeURIComponent(u)}` },
  { test: /(?:twitter\.com|x\.com)/i, platform: "X", endpoint: (u) => `https://publish.twitter.com/oembed?url=${encodeURIComponent(u)}` },
  { test: /instagram\.com/i, platform: "Instagram", endpoint: null }, // no token-free oEmbed; score from description
];

export async function resolveVideoMeta(rawUrl: string): Promise<VideoMeta> {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return {};
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return {};
  const match = OEMBED.find((o) => o.test.test(url.hostname));
  if (!match) return {};
  if (!match.endpoint) return { platform: match.platform };
  try {
    const res = await fetch(match.endpoint(rawUrl), { signal: AbortSignal.timeout(6000) });
    if (!res.ok) return { platform: match.platform };
    const j = (await res.json()) as { title?: string; thumbnail_url?: string };
    return { platform: match.platform, title: j.title, thumbnailUrl: j.thumbnail_url };
  } catch {
    return { platform: match.platform };
  }
}
