"""Autonomous quality loop — iterate the AI-b-roll prompt on the user's REAL video.

Caches the cleaned transcript topics (so we transcribe once), then for each run
generates an Imagen image per topic using a prompt TEMPLATE passed in. Between runs
the operator (Claude) views the images, critiques realism/relevance/text/premium
feel, and passes a refined template — repeating until quality plateaus or the $10
ledger cap hits. Usage: quality_loop.py <iter_label> "<template with {topic}/{caption}>"
"""
from __future__ import annotations

import json
import os
import pickle
import sys

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from supabase import create_client

from cadence import clean_recording
from cadence.config import CleaningConfig
from cadence.ffmpeg.runner import FFmpeg
from cadence.imagegen.distill import GeminiDistiller
from cadence.imagegen.imagen import ImagenGenerator
from cadence.imagegen.ledger import CostLedger
from cadence.synthesis.contextual import plan_broll_windows, raw_text_for_window
from cadence.synthesis.plan import remap_words_to_output
from cadence.transcription.faster_whisper import FasterWhisperTranscriber

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "output")
LOOP = os.path.join(OUT, "loop")
CACHE = os.path.join(LOOP, "topics_raw.pkl")
REC_KEY = "REDACTED"
MAX_WINDOWS = 5  # cap images per iteration to stay cheap

ff = FFmpeg()
os.makedirs(LOOP, exist_ok=True)


def get_topics() -> list[tuple[float, float, str, str]]:
    if os.path.isfile(CACHE):
        return pickle.load(open(CACHE, "rb"))
    admin = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    rec = os.path.join(LOOP, "recording.mp4")
    if not os.path.isfile(rec):
        open(rec, "wb").write(admin.storage.from_("uploads").download(REC_KEY))
    print("transcribing the real recording (once)…", flush=True)
    tr = FasterWhisperTranscriber("base.en", device="cpu", compute_type="int8")
    edl = clean_recording(rec, transcriber=tr, cfg=CleaningConfig(), ff=ff)
    words = remap_words_to_output(edl.transcript, list(edl.kept))
    out = []
    for s, e, _m in plan_broll_windows(edl.output_duration, mode="between"):
        out.append((s, e, raw_text_for_window(words, s, e)))
    pickle.dump(out, open(CACHE, "wb"))
    return out


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "iter2"
    template = sys.argv[2] if len(sys.argv) > 2 else (
        "A hyperrealistic cinematic vertical 9:16 photograph: {scene}. Premium editorial photography, "
        "soft natural cinematic lighting, shallow depth of field, ultra detailed, modern and clean. "
        "The phrase \"{caption}\" appears cleanly on a screen, sign, or surface in the scene in crisp "
        "modern typography. Photoreal, no watermark, no garbled text."
    )
    windows = get_topics()[:MAX_WINDOWS]
    ledger = CostLedger(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_spend.json"),
                        float(os.environ.get("CADENCE_AI_BUDGET_USD", "10")))
    gen = ImagenGenerator(ledger=ledger)
    distiller = GeminiDistiller()
    itdir = os.path.join(LOOP, label)
    os.makedirs(itdir, exist_ok=True)
    print(f"\n=== {label} | model={gen.model} | spent so far ${ledger.spent():.2f}/{ledger.cap_usd:.0f} ===")
    for i, (s, e, raw) in enumerate(windows):
        scene, caption = distiller.distill(raw)
        prompt = template.format(scene=scene, caption=caption)
        try:
            res = gen.generate(prompt, aspect="9x16")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}] FAILED {str(exc)[:120]}")
            continue
        p = os.path.join(itdir, f"{i}_{caption.split()[0][:12] if caption else 'x'}.png")
        open(p, "wb").write(res.image_bytes)
        print(f"  [{i}] said={raw[:42]!r:44} -> caption={caption!r:22} scene={scene[:50]!r}")
    print(f"=== spend now ${ledger.spent():.2f} (images: {ledger._read().get('images')}) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
