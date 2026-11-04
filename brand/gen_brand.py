"""Brand-palette transition cards, SPARSE — reduced corner botanicals, max room for text.

Imagen 4 Ultra, 9:16. Deep crimson-red + violet glowing flowers with teal stems,
3D bioluminescent, but minimal: small delicate corner accents, the vast majority of
the frame empty black for text. 4 layout variations. Key from Content Engine/.env.
"""
from __future__ import annotations
import os, sys, time, pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "generated"; OUT.mkdir(exist_ok=True)

def load_key() -> str:
    for p in (r"C:\Users\you\Downloads\Content Engine\.env",
              str(HERE.parent / "worker" / ".env"), str(HERE.parent / ".env")):
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
    print("ERROR: no GEMINI_API_KEY"); sys.exit(1)

from google import genai
from google.genai import types
client = genai.Client(api_key=KEY)

STYLE = (
    "Deep crimson-red and violet luminescent flowers with glowing teal-green stems and leaves, "
    "soft 3D volumetric render with subsurface scattering, translucent luminous petals, gentle inner "
    "glow and soft rim light, a few faint drifting bokeh light particles, shallow depth of field, "
    "cinematic, premium, ethereal bioluminescent aesthetic, ultra-high detail. "
    "MINIMAL and restrained — the vast majority of the frame is EMPTY black negative space with plenty "
    "of room for text; the center and middle are completely empty black. Small, delicate, sparse accents "
    "only, trailing just a few thin wispy glowing tendrils that quickly fade into the black. "
    "No text, no letters, no words, no numbers, no UI."
)
PLACE = {
    "brand-a-corners":  "Vertical 9:16 mobile video frame, pure deep-black background. Small delicate glowing flower accents tucked only into the FOUR CORNERS, symmetric and restrained, each corner just a tiny cluster.",
    "brand-b-diagonal": "Vertical 9:16 mobile video frame, pure deep-black background. Small delicate glowing flower accents tucked only into the TOP-LEFT and BOTTOM-RIGHT corners; the rest of the frame is empty black.",
    "brand-c-topbottom":"Vertical 9:16 mobile video frame, pure deep-black background. A small delicate glowing flower accent at the TOP edge and a small one at the BOTTOM edge; the entire center is empty black for text.",
    "brand-d-bottom":   "Vertical 9:16 mobile video frame, pure deep-black background. A small low glowing flower accent only along the BOTTOM corners; the top two-thirds is completely empty black.",
}
MODELS = ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001"]

def gen(name, place):
    prompt = f"{place} {STYLE}"
    cfg = types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16")
    for model in MODELS:
        for attempt in range(4):
            try:
                resp = client.models.generate_images(model=model, prompt=prompt, config=cfg)
                imgs = getattr(resp, "generated_images", None) or []
                if not imgs:
                    print(f"  {name}: no image on {model}"); break
                (OUT / f"{name}.png").write_bytes(imgs[0].image.image_bytes)
                print(f"  OK {name}  [{model}]"); return True
            except Exception as exc:
                m = str(exc)
                if "429" in m or "RESOURCE_EXHAUSTED" in m or "exhausted" in m.lower():
                    print(f"  {name}: rate-limited, backoff {12*(attempt+1)}s"); time.sleep(12*(attempt+1)); continue
                if "404" in m or "not found" in m.lower():
                    print(f"  {name}: {model} unavailable -> fallback"); break
                print(f"  {name}: ERROR {m[:150]}"); return False
    return False

print(f"Generating {len(PLACE)} sparse brand frames -> {OUT}")
ok = 0
items = list(PLACE.items())
for i, (name, place) in enumerate(items):
    if gen(name, place): ok += 1
    if i < len(items) - 1: time.sleep(7)
print(f"DONE: {ok}/{len(items)}")
