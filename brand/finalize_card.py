"""Finalize the locked transition card -> lossless 1080x1920 PNG in Downloads."""
import pathlib
from PIL import Image

SRC = pathlib.Path(__file__).resolve().parent / "generated" / "conn-1-fullvine.png"
DST = pathlib.Path(r"C:\Users\Cory\Downloads\CloutHook-transition-card-1080x1920.png")

im = Image.open(SRC).convert("RGB")
print("source size:", im.size)
resample = Image.LANCZOS
out = im.resize((1080, 1920), resample)
out.save(DST, "PNG", optimize=True)
print("saved:", DST, out.size)
