"""Generate 3D bioluminescent botanical TRANSITION-CARD frames with Imagen 4.

Matches the reference: a vertical 9:16 frame, near-black, glowing translucent 3D
flowers anchored in the corners + edges, wispy glowing vines trailing inward and
fading, empty dark center (for use as a video transition / overlay). 6 flower
options. Key loaded from Content Engine/.env (never printed).
"""
from __future__ import annotations
import os, sys, time, pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "generated"
OUT.mkdir(exist_ok=True)

# --- load GEMINI_API_KEY from Content Engine/.env without echoing it ---
def load_key() -> str:
    for p in (r"C:\Users\Cory\Downloads\Content Engine\.env",
              str(HERE.parent / "worker" / ".env"),
              str(HERE.parent / ".env")):
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                    if line.startswith(name + "="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v and "demo" not in v.lower():
                            return v
        except FileNotFoundError:
            continue
    return os.environ.get("GEMINI_API_KEY", "")

KEY = load_key()
if not KEY:
    print("ERROR: no GEMINI_API_KEY found"); sys.exit(1)

from google import genai
from google.genai import types
client = genai.Client(api_key=KEY)

BASE = (
    "Vertical 9:16 mobile video frame. Pure deep-black background; the entire CENTER is empty, "
    "dark, negative space. Bioluminescent glowing botanical decoration clustered ONLY in the "
    "corners and along the top and bottom edges, trailing inward as delicate wispy glowing vines "
    "and tendrils that fade softly into the black before reaching the middle. Rendered as a soft "
    "3D scene with subsurface scattering and translucent, luminous, glowing petals, gentle "
    "volumetric inner light, teal-cyan and violet-magenta bioluminescence with soft rim light, "
    "faint drifting bokeh light particles and glowing spores, shallow depth of field, cinematic, "
    "premium, ethereal dark-fantasy bioluminescent aesthetic, ultra-high detail, photoreal 3D "
    "render. Absolutely no text, no letters, no words, no numbers, no UI; the center stays empty black."
)
FLOWERS = {
    "01-roses": "Glowing translucent luminescent roses with softly curled layered petals",
    "02-lilies": "Glowing translucent luminescent lilies with luminous glowing stamens and long pointed petals",
    "03-lotus": "Glowing translucent luminescent lotus water-lily blossoms with layered pointed petals",
    "04-poppies": "Glowing translucent luminescent poppies with broad delicate papery petals and dark glowing centers",
    "05-wildflowers": "Lush mixed glowing wildflowers, small luminous ferns and glowing buds, slightly denser foliage",
    "06-brand": "Glowing luminescent flowers in deep crimson-red and violet with glowing teal-green stems and leaves",
}
MODELS = ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001"]

def gen(name: str, desc: str) -> bool:
    prompt = f"{desc}. {BASE}"
    cfg = types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16")
    for model in MODELS:
        for attempt in range(4):
            try:
                resp = client.models.generate_images(model=model, prompt=prompt, config=cfg)
                imgs = getattr(resp, "generated_images", None) or []
                if not imgs:
                    print(f"  {name}: no image (safety block?) on {model}"); break
                (OUT / f"{name}.png").write_bytes(imgs[0].image.image_bytes)
                print(f"  OK {name}  [{model}]")
                return True
            except Exception as exc:
                m = str(exc)
                if "429" in m or "RESOURCE_EXHAUSTED" in m or "exhausted" in m.lower():
                    print(f"  {name}: rate-limited, backoff {12*(attempt+1)}s")
                    time.sleep(12 * (attempt + 1)); continue
                if "404" in m or "not found" in m.lower() or "NOT_FOUND" in m:
                    print(f"  {name}: {model} unavailable -> fallback"); break
                print(f"  {name}: ERROR {m[:160]}"); return False
    return False

print(f"Generating {len(FLOWERS)} transition frames -> {OUT}")
ok = 0
for i, (name, desc) in enumerate(FLOWERS.items()):
    if gen(name, desc):
        ok += 1
    if i < len(FLOWERS) - 1:
        time.sleep(7)  # throttle for the per-minute Imagen limit
print(f"DONE: {ok}/{len(FLOWERS)} generated in {OUT}")
