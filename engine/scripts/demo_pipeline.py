"""End-to-end demo + visual verification.

Generates fixtures, runs the whole pipeline (analyze -> clean -> plan -> render),
writes a real final.mp4 + frame thumbnails into engine/output/ so the composited
captions / watermark / grade can be eyeballed.
"""

from __future__ import annotations

import json
import os

from cadence import analyze_reference, build_generation_plan, clean_recording, render_plan
from cadence.brandboard.store import BrandBoardStore
from cadence.ffmpeg.runner import FFmpeg
from cadence.models import Anchor, AssetKind, RGBColor, Transcript, Word
from tests import fixtures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)
ff = FFmpeg()

ref = os.path.join(OUT, "_reference.mp4")
aroll = os.path.join(OUT, "_aroll.mp4")
logo = os.path.join(OUT, "_logo.png")
fixtures.make_reference_video(ff, ref, tmp_dir=OUT)
fixtures.make_talking_clip(ff, aroll)
fixtures.make_logo_png(logo, size=96)
print("fixtures generated")

analysis = analyze_reference(ref, ff=ff)
print("ANALYSIS:")
print("  palette:", [s.color.hex for s in analysis.color_profile.palette])
print("  exposure:", analysis.color_profile.exposure.label.value, round(analysis.color_profile.exposure.mean_luma, 1))
print("  transitions:", [(t.timestamp, t.type.value) for t in analysis.transitions])
print("  text overlays:", [(round(o.start, 2), round(o.end, 2), o.zone.value) for o in analysis.text_overlays])
print("  pacing:", analysis.pacing.to_dict())

transcript = Transcript(words=tuple(
    Word(t, s, e) for t, s, e in [
        ("welcome", 0.2, 0.6), ("to", 0.6, 0.8), ("cadence", 0.8, 1.4),
        ("this", 2.0, 2.3), ("is", 2.3, 2.5), ("premium", 2.5, 3.0),
        ("vertical", 4.0, 4.5), ("video", 4.5, 5.0),
    ]
))
edl = clean_recording(aroll, transcript=transcript, ff=ff)
print("\nCLEAN: source=%.2fs output=%.2fs removed=%.2fs" % (
    edl.source_duration, edl.output_duration, edl.removed_duration))
for r in edl.removed:
    print("  removed", round(r.range.start, 2), "->", round(r.range.end, 2), r.reason.value, r.detail)

store = BrandBoardStore(os.path.join(OUT, "brand.db"))
try:
    board = store.create_board("Cadence Demo")
    store.add_asset(board.id, kind=AssetKind.WATERMARK, name="logo", path=logo,
                    opacity=0.75, anchor=Anchor.BOTTOM_RIGHT, scale=0.16)
    store.set_caption_style(board.id, primary=RGBColor(255, 235, 59), outline=RGBColor(10, 10, 10))
    brand = store.get_board(board.id)
finally:
    store.close()

plan = build_generation_plan(edl, analysis=analysis, brand=brand)
with open(os.path.join(OUT, "generation_plan.json"), "w", encoding="utf-8") as fh:
    fh.write(plan.to_json())
print("\nPLAN: clips=%d captions=%d grade=%s watermark=%s" % (
    len(plan.clips), len(plan.captions), plan.color_grade.to_dict(), bool(plan.watermark)))

final = os.path.join(OUT, "final.mp4")
result = render_plan(plan, final, ff=ff, log_path=os.path.join(OUT, "filtergraph.txt"))
print("\nRENDER:", json.dumps(result.to_dict() | {"command": "<omitted>"}, default=str)[:300])
print("  encoder=%s hardware=%s %dx%d @ %.2ffps  %.2fs" % (
    result.encoder, result.used_hardware, result.width, result.height, result.fps, result.duration))

# Extract thumbnails where captions should be visible.
for label, t in [("early", 0.5), ("mid", result.duration / 2), ("late", max(0.0, result.duration - 0.8))]:
    thumb = os.path.join(OUT, f"frame_{label}.png")
    ff.run(["-y", "-ss", f"{t:.2f}", "-i", final, "-frames:v", "1", thumb], timeout=60)
    print("  thumbnail:", thumb)
print("\nDONE ->", OUT)
