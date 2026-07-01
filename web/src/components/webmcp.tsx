"use client";

import { useEffect } from "react";

// Read-only WebMCP tools so AI browsers (the agentic web; Chrome's modelContext origin trial) can
// query CloutHook directly instead of scraping the DOM. Feature-detected + graceful no-op anywhere
// the API is absent (every browser today, until the trial ships). Standing rule: a WebMCP tool is a
// CLIENT declaration, so ONLY read-only public facts are exposed here — any gated/write action would
// have to be re-authorized server-side and none are exposed.

type McResult = { content: { type: "text"; text: string }[] };
type McTool = {
  name: string;
  description: string;
  inputSchema: { type: "object"; properties: Record<string, never> };
  annotations: { readOnlyHint: true; title: string };
  execute: () => Promise<McResult>;
};
type ModelContext = { registerTool?: (tool: McTool) => void };

const OVERVIEW =
  "CloutHook is a premium AI short-form video studio. Record one raw take and it auto-edits a " +
  "studio-grade 1080x1920 (9:16) short — cleanup, captions, AI b-roll, stitching. It also makes " +
  "faceless videos (script -> voice -> AI scenes -> karaoke captions), a photoreal clone-yourself AI " +
  "avatar, auto-reframes 16:9 -> 9:16, auto-clips long videos into ranked shorts, and posts directly " +
  "to X, Instagram, Facebook, LinkedIn, YouTube, and TikTok. Token-based pricing, no per-seat fees. " +
  "An app by Neuron HQ (neuron-hq.com).";

const PRICING =
  "Plans (USD/month): Free $0 — 25 tokens; Base $30 — 200 tokens; Creator $79 — 560 tokens (unlocks " +
  "photoreal avatars). 1 token = 1 AI scene; an animated scene = 3 tokens; a photoreal avatar video = " +
  "8 tokens (Creator plan, up to 20/month). Editing your own footage costs no tokens. No per-seat " +
  "fees. Full details: https://clouthook.com/pricing";

const FEATURES =
  "- Record once -> auto-edited studio short (cleanup, captions, b-roll, stitching)\n" +
  "- Faceless videos: script -> TTS voice -> AI scenes -> karaoke captions\n" +
  "- Photoreal clone-yourself AI avatar (record on phone via a QR hand-off)\n" +
  "- Auto-reframe 16:9 -> 9:16 with face/subject tracking\n" +
  "- Auto-clip a long video into ranked shorts\n" +
  "- Direct posting to X, Instagram, Facebook, LinkedIn, YouTube, TikTok\n" +
  "- Bring-your-own ElevenLabs voice + voice cloning\n" +
  "- Output 1080x1920, up to 60fps";

export function WebMcp() {
  useEffect(() => {
    const mc = (document as unknown as { modelContext?: ModelContext }).modelContext;
    if (!mc || typeof mc.registerTool !== "function") return; // no agentic-web host — no-op

    const tool = (name: string, description: string, text: string) => {
      try {
        mc.registerTool!({
          name,
          description,
          inputSchema: { type: "object", properties: {} },
          annotations: { readOnlyHint: true, title: description },
          execute: async () => ({ content: [{ type: "text", text }] }),
        });
      } catch {
        /* host API shape mismatch — ignore */
      }
    };

    tool("clouthook_overview", "What CloutHook is and does", OVERVIEW);
    tool("clouthook_pricing", "CloutHook plans and token pricing", PRICING);
    tool("clouthook_features", "CloutHook feature list", FEATURES);
  }, []);

  return null;
}
