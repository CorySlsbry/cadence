"""Generate CloutHook favicon + app icons (gradient squircle + white CH monogram).

Geometric CH (font-independent) drawn to match brand/logo/icon.svg, rendered at high
res then downscaled for crisp small sizes. Outputs to brand/icons/.
"""
import pathlib
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent / "icons"; OUT.mkdir(exist_ok=True)
C1 = (0x5C, 0x8C, 0xFF)   # blue
C2 = (0xA0, 0x6B, 0xFF)   # purple

def lerp(a, b, t): return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

def gradient(S):
    g = Image.new("RGB", (S, S)); px = g.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = lerp(C1, C2, (x + y) / (2 * (S - 1)))
    return g

def draw_ch(img, S, pad_frac=0.0, color=(255, 255, 255, 255)):
    d = ImageDraw.Draw(img)
    inset = S * pad_frac; span = S - 2 * inset; sc = span / 100.0
    X = lambda v: inset + v * sc
    wc = 10 * sc; wh = 9 * sc
    cx, cy, r = X(30), X(50), 19 * sc
    d.arc([cx - r, cy - r, cx + r, cy + r], start=48, end=312, fill=color, width=max(2, round(wc)))
    # round the C ends
    for ex, ey in ((42.7, 64.1), (42.7, 35.9)):
        rr = wc / 2; d.ellipse([X(ex) - rr, X(ey) - rr, X(ex) + rr, X(ey) + rr], fill=color)
    d.rounded_rectangle([X(56), X(31), X(65), X(69)], radius=wh / 2, fill=color)
    d.rounded_rectangle([X(80), X(31), X(89), X(69)], radius=wh / 2, fill=color)
    d.rounded_rectangle([X(56), X(45), X(89), X(54)], radius=wh / 2, fill=color)

def squircle(S, maskable=False):
    if maskable:
        img = Image.new("RGBA", (S, S)); img.paste(gradient(S), (0, 0))
        draw_ch(img, S, pad_frac=0.20)
        return img
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img.paste(gradient(S), (0, 0), mask)
    draw_ch(img, S)
    return img

def at(S, maskable=False):
    return squircle(512, maskable).resize((S, S), Image.LANCZOS)

SIZES = {"favicon-16.png": 16, "favicon-32.png": 32, "favicon-48.png": 48,
         "apple-touch-icon.png": 180, "icon-192.png": 192, "icon-512.png": 512}
for name, S in SIZES.items():
    at(S).save(OUT / name)
at(512, maskable=True).save(OUT / "icon-512-maskable.png")
at(64).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("icons ->", OUT, sorted(p.name for p in OUT.glob('*')))
