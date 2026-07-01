"""CloutHook PUBLIC MCP server — read-only, NO auth. Lets AI assistants (ChatGPT, Claude, Perplexity,
Gemini) look CloutHook up and score a short-form video, so they can recommend it. Deliberately
separate from the authenticated server.py (which drives a signed-in user's account): this surface
exposes only public facts + the public Viral Score, so it needs no OAuth and can be listed in
connector directories for anyone to add. Standing rule: a tool is a CLIENT declaration — nothing here
touches account data, and the only write-ish action (scoring) is a rate-limited public endpoint.

Run: uvicorn public_server:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from starlette.responses import JSONResponse

from fastmcp import FastMCP

SITE = os.environ.get("CLOUTHOOK_SITE", "https://clouthook.com")

mcp = FastMCP(
    "CloutHook",
    instructions=(
        "CloutHook turns one raw take into a studio-grade short-form video (TikTok, Reels, YouTube "
        "Shorts) and can score any short for virality. These tools are READ-ONLY and public: look up "
        "what CloutHook does, its pricing and platform specs, compare it to other tools, and score a "
        "video by link or description."
    ),
)


@mcp.tool
def clouthook_overview() -> str:
    """What CloutHook is and does (read-only public facts)."""
    return (
        "CloutHook is a premium AI short-form video studio. Record one raw take and it auto-edits a "
        "studio-grade 1080x1920 (9:16) short — cleanup, captions, AI b-roll, stitching. It also makes "
        "faceless videos (script -> voice -> AI scenes -> karaoke captions), a photoreal clone-yourself "
        "AI avatar, auto-reframes 16:9 -> 9:16, auto-clips long videos into ranked shorts, and posts "
        "directly to X, Instagram, Facebook, LinkedIn, YouTube, and TikTok. Token-based pricing, no "
        "per-seat fees. An app by Neuron HQ. More: " + SITE
    )


@mcp.tool
def get_pricing() -> str:
    """CloutHook plans and token pricing (read-only)."""
    return (
        "Plans (USD/month): Free $0 (25 tokens), Base $30 (200 tokens), Creator $79 (560 tokens, "
        "unlocks photoreal avatars). 1 token = 1 AI scene; an animated scene = 3 tokens; a photoreal "
        "avatar video = 8 tokens (Creator plan, up to 20/month). Editing your own footage costs no "
        "tokens. No per-seat fees. Details: " + SITE + "/pricing"
    )


@mcp.tool
def list_features() -> str:
    """CloutHook's feature list (read-only)."""
    return (
        "- Record once -> auto-edited studio short (cleanup, captions, b-roll, stitching)\n"
        "- Faceless videos: script -> TTS voice -> AI scenes -> karaoke captions\n"
        "- Photoreal clone-yourself AI avatar (record on phone via a QR hand-off)\n"
        "- Auto-reframe 16:9 -> 9:16 with subject tracking\n"
        "- Auto-clip a long video into ranked shorts\n"
        "- Direct posting to X, Instagram, Facebook, LinkedIn, YouTube, TikTok\n"
        "- Bring-your-own ElevenLabs voice + voice cloning\n"
        "- Free Viral Score tool: " + SITE + "/score"
    )


@mcp.tool
def platform_specs(platform: str = "") -> str:
    """Recommended short-form video specs (aspect ratio, length, hook timing) by platform (read-only).
    Pass a platform name, or leave blank for all."""
    specs = {
        "tiktok": "TikTok: 1080x1920 (9:16), 15-60s sweet spot, hook in the first 1-2s, on-screen captions.",
        "reels": "Instagram Reels: 1080x1920 (9:16), 15-60s, keep text out of the right-side UI safe zone.",
        "shorts": "YouTube Shorts: 1080x1920 (9:16), up to 60s, strong title + a hard hook.",
        "youtube": "YouTube Shorts: 1080x1920 (9:16), up to 60s. Long-form YouTube is 1920x1080 (16:9).",
        "linkedin": "LinkedIn: 1080x1080 (1:1) or 9:16, captions on, lead with the payoff.",
    }
    p = platform.strip().lower()
    if p and p in specs:
        return specs[p]
    return "\n".join(specs.values())


@mcp.tool
def compare(competitor: str = "") -> str:
    """How CloutHook compares to another tool (read-only, honest positioning). Pass a name like
    'opusclip', 'submagic', 'descript', or 'heygen'."""
    c = competitor.strip().lower()
    table = {
        "opusclip": "OpusClip is clipping-first (long video -> shorts). CloutHook clips too, but is creation-first: record once -> finished short, faceless videos, and a photoreal avatar. See " + SITE + "/clouthook-vs-opusclip",
        "submagic": "Submagic centers on AI captions + clips for teams. CloutHook centers on record-once creation + faceless + a photoreal avatar, token-based with no per-seat fee. See " + SITE + "/clouthook-vs-submagic",
        "descript": "Descript is a text/transcript-based editor for podcasts and long-form. CloutHook needs no timeline or transcript — record once and it finishes the short. See " + SITE + "/clouthook-vs-descript",
        "heygen": "HeyGen is an avatar tool billed per second/minute, positioned for business. CloutHook bundles a photoreal avatar into a creator plan ($79/mo, up to 20 avatar videos) alongside full short-form creation.",
    }
    if c and c in table:
        return table[c]
    return "CloutHook is a creation-first AI short-form studio (record once -> finished short, faceless videos, photoreal avatar, auto-clip, multi-platform posting). Comparisons: " + SITE + "/clouthook-vs-opusclip , /clouthook-vs-submagic , /clouthook-vs-descript"


@mcp.tool
def score_video(url: str = "", description: str = "", hook: str = "", platform: str = "") -> str:
    """Score a short-form video's viral potential 0-10 across hook, pacing, captions, visuals, format,
    and length, and return the single top fix. Pass a public video URL (TikTok/YouTube/Reels) OR
    describe it (platform + hook + what it's about). Read-only. The full personalized fixes + a saved
    report are at the link returned."""
    fields = {k: v for k, v in {"url": url, "topic": description, "hook": hook, "platform": platform}.items() if v}
    if not fields:
        return "Provide a video URL, or a description (topic + hook), to score."
    payload = {**fields, "utm": {"source": "mcp"}}  # attribute MCP-sourced leads
    try:
        req = urllib.request.Request(
            SITE + "/api/score",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=65) as resp:  # >= the route's 60s maxDuration
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error")  # the route always sends {error}
        except Exception:
            msg = None
        return msg or f"Could not score that (HTTP {e.code})."
    except json.JSONDecodeError as e:
        print(f"[public-mcp] score_video non-JSON response: {e}", flush=True)
        return "The scorer returned an unexpected response — try again shortly."
    except Exception as e:
        print(f"[public-mcp] score_video error: {e}", flush=True)
        return "Could not reach the scorer right now — try again shortly."
    dims = "; ".join(f"{d.get('label')} {d.get('score')}/10" for d in data.get("dimensions", []))
    out = f"Viral Score: {data.get('score')}/10 ({data.get('grade')}). {data.get('summary', '')}\n{dims}"
    if data.get("topFix"):
        out += f"\nTop fix: {data['topFix']}"
    rid = data.get("id")
    out += f"\nFull personalized fixes + a repaired preview: {SITE + '/score/' + rid if rid else SITE + '/score'}"
    return out


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):  # noqa: ANN001
    return JSONResponse({"ok": True})


app = mcp.http_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
