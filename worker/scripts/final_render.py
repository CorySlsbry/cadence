"""Produce the finished premium video from the user's REAL recording, end-to-end:
clean + transcribe -> Imagen contextual b-roll (Gemini-distilled topics) -> render.
"""
from __future__ import annotations

import os

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)

from supabase import create_client

from cadence import build_generation_plan, clean_recording, render_plan
from cadence.config import CleaningConfig
from cadence.ffmpeg.runner import FFmpeg
from cadence.imagegen.distill import GeminiDistiller
from cadence.imagegen.imagen import ImagenGenerator
from cadence.imagegen.ledger import CostLedger
from cadence.synthesis.contextual import build_ai_broll
from cadence.synthesis.plan import remap_words_to_output
from cadence.transcription.faster_whisper import FasterWhisperTranscriber

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine", "output")
LOOP = os.path.join(OUT, "loop")
REC = os.path.join(LOOP, "recording.mp4")
REC_KEY = "a9b77d5f-d9fd-4f1b-89b3-d39549ffd43b/471d9850-8a6f-47c5-8608-0f0dc486e1da/recording-1780625376347.mp4"
ff = FFmpeg()


def main() -> int:
    if not os.path.isfile(REC):
        admin = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
        os.makedirs(LOOP, exist_ok=True)
        open(REC, "wb").write(admin.storage.from_("uploads").download(REC_KEY))

    print("transcribing…", flush=True)
    tr = FasterWhisperTranscriber("base.en", device="cpu", compute_type="int8")
    edl = clean_recording(REC, transcriber=tr, cfg=CleaningConfig(), ff=ff)
    print(f"cleaned: {edl.source_duration:.1f}s -> {edl.output_duration:.1f}s", flush=True)

    ledger = CostLedger(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_spend.json"),
                        float(os.environ.get("CADENCE_AI_BUDGET_USD", "10")))
    gen = ImagenGenerator(ledger=ledger)
    distiller = GeminiDistiller()
    words = remap_words_to_output(edl.transcript, list(edl.kept))
    broll_dir = os.path.join(LOOP, "final_broll")
    os.makedirs(broll_dir, exist_ok=True)
    print(f"generating AI b-roll (Imagen, spent ${ledger.spent():.2f}/{ledger.cap_usd:.0f})…", flush=True)
    broll = build_ai_broll(words, edl.output_duration, gen, out_dir=broll_dir, mode="between", distiller=distiller)
    print(f"b-roll cutaways: {len(broll)}; spend now ${ledger.spent():.2f}", flush=True)

    plan = build_generation_plan(edl)
    plan.broll = broll
    out = os.path.join(OUT, "final_real.mp4")
    print("rendering full video…", flush=True)
    res = render_plan(plan, out, ff=ff)
    print(f"RENDERED -> {out}  {res.width}x{res.height}@{res.fps:.0f} {res.duration:.1f}s", flush=True)

    for b in broll[:3]:
        t = (b.start + b.end) / 2
        thumb = os.path.join(OUT, f"final_frame_{int(t)}.png")
        ff.run(["-y", "-ss", f"{t:.2f}", "-i", out, "-frames:v", "1", thumb], timeout=60)
        print(f"  frame @ {t:.1f}s -> {os.path.relpath(thumb, OUT)}", flush=True)
    print(f"\nFINAL RENDER DONE. Total AI spend ${ledger.spent():.2f} of ${ledger.cap_usd:.0f}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
