"""Visual check for animated-still b-roll cutaways."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

from cadence import build_generation_plan, clean_recording, render_plan
from cadence.ffmpeg.runner import FFmpeg
from cadence.synthesis.plan import place_broll

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
os.makedirs(OUT, exist_ok=True)
ff = FFmpeg()


def make_broll_image(path: str, color, label: str) -> None:
    img = Image.new("RGB", (900, 1100), color)
    d = ImageDraw.Draw(img)
    d.rectangle([60, 400, 840, 700], fill=(255, 255, 255))
    d.text((110, 520), label, fill=(20, 20, 20))
    for i in range(6):  # fake "chart" bars for high edge density
        d.rectangle([120 + i * 110, 780 - i * 30, 200 + i * 110, 980], fill=(255, 214, 10))
    img.save(path)


aroll = os.path.join(OUT, "_aroll.mp4")
if not os.path.isfile(aroll):
    from tests import fixtures  # type: ignore
    fixtures.make_talking_clip(ff, aroll)

b1 = os.path.join(OUT, "broll_1.png")
b2 = os.path.join(OUT, "broll_2.png")
make_broll_image(b1, (30, 60, 140), "SCREEN DEMO A")
make_broll_image(b2, (140, 30, 90), "SCREEN DEMO B")

edl = clean_recording(aroll, ff=ff)
plan = build_generation_plan(edl, broll_images=[b1, b2], pacing_mode="match")
print("output duration:", round(edl.output_duration, 2), "s")
print("b-roll inserts:", [(b.start, b.end, b.motion.value) for b in plan.broll])

out = os.path.join(OUT, "broll_final.mp4")
res = render_plan(plan, out, ff=ff, log_path=os.path.join(OUT, "broll_graph.txt"))
print(f"rendered {res.width}x{res.height}@{res.fps:.0f} {res.duration:.2f}s")

# Sample a frame INSIDE the first b-roll window and one OUTSIDE it.
if plan.broll:
    b = plan.broll[0]
    inside = (b.start + b.end) / 2
    outside = max(0.2, b.start - 0.8)
    for tag, t in [("inside_broll", inside), ("outside_broll", outside)]:
        ff.run(["-y", "-ss", f"{t:.2f}", "-i", out, "-frames:v", "1", os.path.join(OUT, f"broll_{tag}.png")], timeout=60)
        print("frame", tag, "@", round(t, 2), "s")
print("done")
