import { ImageResponse } from "next/og";
import { createAdminClient } from "@/lib/supabase/admin";
import type { ScoreResult } from "@/lib/score";

export const runtime = "nodejs";
export const alt = "CloutHook Viral Score";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Dynamic share badge — "8.2/10" — so a shared score link previews the number (the viral loop).
export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let r: ScoreResult | null = null;
  try {
    if (/^[0-9a-f-]{36}$/i.test(id)) {
      const admin = createAdminClient();
      const { data } = await admin.from("score_results").select("result").eq("id", id).maybeSingle();
      r = (data?.result as ScoreResult | undefined) ?? null;
    }
  } catch {
    r = null;
  }

  const score = r ? `${r.score}` : "?";
  const grade = r?.grade ?? "Viral Score";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#0b0a14",
          color: "#f6f5fb",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ fontSize: 34, color: "#a6a3c0", letterSpacing: 2 }}>CLOUTHOOK · VIRAL SCORE</div>
        <div style={{ display: "flex", alignItems: "flex-end", marginTop: 16 }}>
          <div style={{ fontSize: 240, fontWeight: 800, lineHeight: 1, color: "#6e7bff" }}>{score}</div>
          <div style={{ fontSize: 64, fontWeight: 700, color: "#a6a3c0", marginBottom: 34 }}>/10</div>
        </div>
        <div style={{ fontSize: 44, fontWeight: 700, marginTop: 8 }}>{grade}</div>
        <div style={{ fontSize: 28, color: "#a6a3c0", marginTop: 28 }}>Score your short-form video free at clouthook.com/score</div>
      </div>
    ),
    { ...size },
  );
}
