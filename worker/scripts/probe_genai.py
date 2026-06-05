"""Probe which Google image model the user's Gemini key can actually use, and save a
sample so we can judge realism + text rendering before wiring the loop."""
from __future__ import annotations

import os

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from google import genai
from google.genai import types

KEY = os.environ["GEMINI_API_KEY"]
client = genai.Client(api_key=KEY)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "output")
PROMPT = (
    "A hyperrealistic cinematic vertical 9:16 photograph of a sleek modern laptop on a clean "
    "desk, the screen clearly displaying the text 'CLAUDE SKILLS' in crisp modern UI typography. "
    "Soft natural studio lighting, shallow depth of field, premium editorial style, ultra detailed. No watermark."
)

IMAGEN = ["imagen-4.0-generate-001", "imagen-4.0-fast-generate-001", "imagen-3.0-generate-002"]
NANO = ["gemini-2.5-flash-image", "gemini-2.5-flash-image-preview", "gemini-2.0-flash-preview-image-generation"]


def try_imagen():
    for m in IMAGEN:
        try:
            r = client.models.generate_images(
                model=m, prompt=PROMPT,
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
            )
            imgs = getattr(r, "generated_images", None) or []
            if imgs:
                return m, imgs[0].image.image_bytes
        except Exception as e:
            print(f"  imagen {m}: {str(e)[:140]}")
    return None, None


def try_nano():
    for m in NANO:
        try:
            r = client.models.generate_content(
                model=m, contents=[PROMPT],
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for part in r.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    return m, part.inline_data.data
        except Exception as e:
            print(f"  nano {m}: {str(e)[:140]}")
    return None, None


print("trying Imagen 4 …")
model, data = try_imagen()
if not data:
    print("Imagen unavailable; trying Nano Banana (Gemini Flash Image) …")
    model, data = try_nano()

if data:
    path = os.path.join(OUT, "genai_test.png")
    open(path, "wb").write(data)
    print(f"\nWORKING MODEL: {model}  ({len(data)} bytes) -> {path}")
else:
    print("\nNo Google image model worked with this key.")
