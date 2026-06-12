"""Generate the 10 preset recording frames (1080x1920 RGBA, transparent centers).

Design rules: decoration lives at edges/corners; the center and the caption zone
(lower-middle band) stay clear so karaoke captions remain readable under any frame.
Output: scripts/frames-out/{key}.png — uploaded to public assets/frames/.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames-out")
os.makedirs(OUT, exist_ok=True)

ACCENT = (122, 108, 255)
ACCENT2 = (92, 140, 255)
PINK = (246, 145, 179)
GOLD = (212, 175, 55)
CYAN = (94, 234, 212)


def canvas() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def rounded_ring(img: Image.Image, inset: int, radius: int, width: int, color, alpha=255):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([inset, inset, W - inset, H - inset], radius=radius,
                        outline=(*color, alpha), width=width)


def save(img: Image.Image, key: str):
    img.save(os.path.join(OUT, f"{key}.png"))
    print("wrote", key)


# 1 · neon — soft glowing gradient ring
img = canvas()
glow = canvas()
for i, (col, w_, a) in enumerate([(ACCENT, 26, 110), (ACCENT2, 16, 160), ((180, 170, 255), 7, 255)]):
    rounded_ring(glow, 40, 56, w_, col, a)
glow = glow.filter(ImageFilter.GaussianBlur(9))
sharp = canvas()
rounded_ring(sharp, 40, 56, 6, (205, 198, 255), 255)
img = Image.alpha_composite(glow, sharp)
save(img, "neon")

# 2 · film — sprocket strips down the SIDES (caption zone untouched)
img = canvas()
d = ImageDraw.Draw(img)
strip = 92
d.rectangle([0, 0, strip, H], fill=(12, 12, 14, 235))
d.rectangle([W - strip, 0, W, H], fill=(12, 12, 14, 235))
hole_w, hole_h, gap = 40, 56, 46
y = gap
while y + hole_h < H - gap:
    for x0 in (26, W - strip + 26):
        d.rounded_rectangle([x0, y, x0 + hole_w, y + hole_h], radius=10, fill=(0, 0, 0, 0))
    y += hole_h + gap
save(img, "film")

# 3 · polaroid — white border, classic thicker bottom (still under caption line)
img = canvas()
d = ImageDraw.Draw(img)
side, top, bottom = 44, 44, 150
d.rectangle([0, 0, W, top], fill=(248, 246, 240, 255))
d.rectangle([0, H - bottom, W, H], fill=(248, 246, 240, 255))
d.rectangle([0, 0, side, H], fill=(248, 246, 240, 255))
d.rectangle([W - side, 0, W, H], fill=(248, 246, 240, 255))
save(img, "polaroid")

# 4 · goldluxe — thin double gold border + corner ticks
img = canvas()
rounded_ring(img, 36, 24, 5, GOLD)
rounded_ring(img, 58, 16, 2, (230, 200, 110))
d = ImageDraw.Draw(img)
L = 120
for (x, y, dx, dy) in [(36, 36, 1, 1), (W - 36, 36, -1, 1), (36, H - 36, 1, -1), (W - 36, H - 36, -1, -1)]:
    d.line([x, y, x + dx * L, y], fill=(*GOLD, 255), width=10)
    d.line([x, y, x, y + dy * L], fill=(*GOLD, 255), width=10)
save(img, "goldluxe")

# 5 · tape — clean white border with washi-tape corners
img = canvas()
rounded_ring(img, 34, 10, 22, (250, 250, 250), 235)
tape = Image.new("RGBA", (260, 86), (255, 209, 102, 215))
for (cx, cy, ang) in [(60, 60, 45), (W - 60, 60, -45), (60, H - 60, -45), (W - 60, H - 60, 45)]:
    t = tape.rotate(ang, expand=True)
    img.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
save(img, "tape")

# 6 · hud — tactical cyan corners + side rules
img = canvas()
d = ImageDraw.Draw(img)
L, w_ = 170, 8
for (x, y, dx, dy) in [(28, 28, 1, 1), (W - 28, 28, -1, 1), (28, H - 28, 1, -1), (W - 28, H - 28, -1, -1)]:
    d.line([x, y, x + dx * L, y], fill=(*CYAN, 255), width=w_)
    d.line([x, y, x, y + dy * L], fill=(*CYAN, 255), width=w_)
for yy in (int(H * 0.32), int(H * 0.5)):
    d.line([28, yy, 88, yy], fill=(*CYAN, 170), width=4)
    d.line([W - 88, yy, W - 28, yy], fill=(*CYAN, 170), width=4)
save(img, "hud")

# 7 · softround — single soft white rounded border
img = canvas()
rounded_ring(img, 42, 64, 14, (255, 255, 255), 210)
save(img, "softround")

# 8 · blackmat — matte gallery border
img = canvas()
d = ImageDraw.Draw(img)
m = 56
d.rectangle([0, 0, W, m], fill=(16, 16, 18, 255))
d.rectangle([0, H - m, W, H], fill=(16, 16, 18, 255))
d.rectangle([0, 0, m, H], fill=(16, 16, 18, 255))
d.rectangle([W - m, 0, W, H], fill=(16, 16, 18, 255))
rounded_ring(img, m + 6, 4, 2, (200, 200, 200), 120)
save(img, "blackmat")

# 9 · grad — bold brand gradient border
img = canvas()
grad = Image.new("RGBA", (W, H))
gd = ImageDraw.Draw(grad)
for y in range(H):
    t = y / H
    r = int(ACCENT2[0] * (1 - t) + PINK[0] * t)
    g = int(ACCENT2[1] * (1 - t) + PINK[1] * t)
    b = int(ACCENT2[2] * (1 - t) + PINK[2] * t)
    gd.line([(0, y), (W, y)], fill=(r, g, b, 255))
mask = Image.new("L", (W, H), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([24, 24, W - 24, H - 24], radius=48, fill=255)
md.rounded_rectangle([72, 72, W - 72, H - 72], radius=28, fill=0)
img = Image.composite(grad, canvas(), mask)
save(img, "grad")

# 10 · spotlight — soft dark vignette, fully open center
img = canvas()
vin = Image.new("L", (W, H), 0)
vd = ImageDraw.Draw(vin)
vd.rectangle([0, 0, W, H], fill=200)
vd.rounded_rectangle([90, 90, W - 90, H - 90], radius=220, fill=0)
vin = vin.filter(ImageFilter.GaussianBlur(80))
black = Image.new("RGBA", (W, H), (5, 5, 10, 255))
img = Image.composite(black, canvas(), vin)
save(img, "spotlight")

print("done:", len(os.listdir(OUT)), "frames in", OUT)
