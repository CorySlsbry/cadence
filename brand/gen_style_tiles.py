"""Generate style-picker tile candidates: 5 per scene style, one consistent subject
so styles compare honestly. Hints mirror worker/cadence_worker.py SCENE_STYLES so the
tile previews exactly what a render will look like. GEMINI_API_KEY from env."""

from __future__ import annotations

import os
import sys
import time

from google import genai
from google.genai import types

# One subject everywhere → the only variable is the style.
SUBJECT = (
    "a young creator at a desk in a cozy room, glowing laptop, small plant, "
    "warm window light, telling a story"
)

STYLES = {
    # photoreal trio (presets)
    "cinematic": "cinematic photoreal scene, shallow depth of field, anamorphic lens look, rich filmic color grade, dramatic key lighting",
    "film": "35mm film photograph, visible film grain, halation glow, warm vintage color palette, nostalgic editorial composition",
    "clean": "bright clean lifestyle photo, soft natural daylight, minimal modern interior, crisp authentic realism",
    # art styles — keep in lockstep with worker SCENE_STYLES
    "claymation": "handcrafted claymation stop-motion scene, plasticine characters with subtle fingerprint texture, miniature handmade set, warm studio lighting",
    "cartoon3d": "premium 3D animated cartoon scene, expressive stylized characters, soft global illumination, rich subsurface detail, feature-animation quality render",
    "anime": "cinematic anime scene, detailed cel shading, dramatic rim lighting, expressive characters, premium animation-studio key visual",
    "comic": "bold comic book illustration, dynamic ink linework, halftone shading, vivid saturated colors, dramatic graphic-novel panel composition",
    "watercolor": "hand-painted watercolor illustration, soft pigment washes, textured cold-press paper grain, delicate ink linework, gallery-quality",
    "cyberpunk": "neon cyberpunk scene, rain-slick reflective streets visible through the window, holographic signage glow, dramatic magenta-and-cyan lighting, cinematic sci-fi atmosphere",
    "papercraft": "layered paper-cut craft scene, dimensional cardstock collage, crisp die-cut edges, soft shadows between paper layers, handmade premium feel",
    "character": "cinematic character-driven scene starring one consistent stylized hero character with big expressive eyes, instantly recognizable mascot energy",
}

N_PER_STYLE = 5
OUT = os.path.join(os.path.dirname(__file__), "style-tiles")


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set"); return 1
    os.makedirs(OUT, exist_ok=True)
    client = genai.Client(api_key=key)
    total = 0
    for style, hint in STYLES.items():
        for i in range(1, N_PER_STYLE + 1):
            dest = os.path.join(OUT, f"{style}-{i}.png")
            if os.path.exists(dest) and os.path.getsize(dest) > 10000:
                print(f"skip {style}-{i} (exists)", flush=True)
                continue
            prompt = f"{hint}. The scene: {SUBJECT}. No text, no words, no logos."
            for attempt in range(4):
                try:
                    r = client.models.generate_images(
                        model="imagen-4.0-generate-001",
                        prompt=prompt,
                        config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
                    )
                    img = r.generated_images[0].image.image_bytes
                    with open(dest, "wb") as f:
                        f.write(img)
                    total += 1
                    print(f"OK {style}-{i} ({len(img)//1024}KB)", flush=True)
                    break
                except Exception as e:  # noqa: BLE001
                    wait = 20 * (attempt + 1)
                    print(f"retry {style}-{i} in {wait}s: {str(e)[:120]}", flush=True)
                    time.sleep(wait)
            time.sleep(7)  # throttle

    # contact sheet
    rows = []
    for style in STYLES:
        cells = "".join(
            f'<div class="cell"><img src="style-tiles/{style}-{i}.png"><span>{style}-{i}</span></div>'
            for i in range(1, N_PER_STYLE + 1)
        )
        rows.append(f'<h2>{style}</h2><div class="row">{cells}</div>')
    html = (
        "<html><head><style>body{background:#0b0c12;color:#eee;font-family:system-ui;padding:24px}"
        "h2{margin:28px 0 10px;text-transform:capitalize}.row{display:flex;gap:10px}"
        ".cell{flex:1}.cell img{width:100%;border-radius:10px;border:1px solid #333}"
        ".cell span{display:block;text-align:center;font-size:12px;color:#999;margin-top:4px}"
        "</style></head><body><h1>CloutHook style tiles — pick one per row</h1>"
        + "".join(rows) + "</body></html>"
    )
    with open(os.path.join(os.path.dirname(__file__), "style-tiles.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"DONE total={total} sheet=brand/style-tiles.html", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
