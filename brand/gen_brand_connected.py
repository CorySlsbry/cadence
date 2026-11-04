"""Four-corner brand transition cards WITH a subtle corner-to-corner connection.

Imagen 4 Ultra, 9:16. Brand red/violet + teal 3D glow, sparse corners, but now the
corners are linked by a thin delicate glowing vine/line (5 different connection styles).
Still minimal — lots of empty black for text. Key from Content Engine/.env.
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

HEAD = ("Vertical 9:16 mobile video frame, pure deep-black background. Small delicate glowing flower "
        "clusters of deep crimson-red and violet luminescent flowers with glowing teal-green stems in "
        "ALL FOUR CORNERS, ")
TAIL = (" The center is empty black with lots of room for text. Soft 3D volumetric render with subsurface "
        "scattering, translucent luminous petals, gentle inner glow and soft rim light, a few faint drifting "
        "bokeh particles, shallow depth of field, cinematic, premium, ethereal bioluminescent aesthetic, "
        "ultra-high detail, minimal and restrained. No text, no letters, no words, no numbers, no UI.")
CONN = {
    "conn-1-fullvine":  "the four corners connected by a single very thin, delicate glowing teal-green vine that runs along all four edges, linking them into a faint thin botanical border frame.",
    "conn-2-topbottom": "the top two corners linked by a thin delicate glowing vine along the top edge and the bottom two corners linked by a thin vine along the bottom edge; the left and right edges stay open.",
    "conn-3-sides":     "the corners linked by a thin delicate glowing vine running down the left edge and down the right edge connecting top corners to bottom corners; the top and bottom edges stay open.",
    "conn-4-hairline":  "the four corners connected by an extremely thin, faint, single glowing hairline thread that traces a rounded-rectangle just inside the frame edges, linking all four corners delicately.",
    "conn-5-reaching":  "thin wispy glowing tendrils extending from each corner along the edges, reaching toward one another and almost meeting near the middle of each edge — a delicate, barely-touching connection.",
}
MODELS = ["imagen-4.0-ultra-generate-001", "imagen-4.0-generate-001"]

def gen(name, conn):
    prompt = HEAD + conn + TAIL
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

print(f"Generating {len(CONN)} connected-corner brand frames -> {OUT}")
ok = 0; items = list(CONN.items())
for i, (name, conn) in enumerate(items):
    if gen(name, conn): ok += 1
    if i < len(items) - 1: time.sleep(7)
print(f"DONE: {ok}/{len(items)}")
