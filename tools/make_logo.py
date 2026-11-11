"""Generates the original Easy Rewards icon (soft amber squircle with a sparkle).

Run:  python tools/make_logo.py      -> writes assets/logo_*.png and assets/icon.ico
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "assets"
S = 1024  # work size, downsampled for crisp edges


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        col = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            # slight diagonal warmth
            k = x / (size - 1) * 0.18
            px[x, y] = tuple(min(255, round(c + (255 - c) * 0 + k * (bottom[i] - top[i]) * 0.4)) for i, c in enumerate(col))
    return img


def sparkle(cx, cy, radius, power=3.0, n=240):
    """Four-point star from an astroid curve (concave sides)."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        x = math.copysign(abs(c) ** power, c)
        y = math.copysign(abs(s) ** power, s)
        pts.append((cx + radius * x, cy + radius * y))
    return pts


def build() -> Image.Image:
    base = gradient(S, (255, 218, 140), (255, 150, 120)).convert("RGBA")

    # squircle mask
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.24), fill=255)

    # soft top-left light
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-S * 0.2, -S * 0.35, S * 0.85, S * 0.55), fill=(255, 255, 255, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.08))
    base = Image.alpha_composite(base, glow)

    # star shadow
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    d.polygon(sparkle(S * 0.47, S * 0.53, S * 0.30), fill=(190, 80, 50, 110))
    d.polygon(sparkle(S * 0.74, S * 0.27, S * 0.10), fill=(190, 80, 50, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.02))
    base = Image.alpha_composite(base, shadow)

    # stars
    stars = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(stars)
    d.polygon(sparkle(S * 0.47, S * 0.49, S * 0.30), fill=(255, 255, 255, 255))
    d.polygon(sparkle(S * 0.74, S * 0.24, S * 0.10), fill=(255, 255, 255, 235))
    d.polygon(sparkle(S * 0.25, S * 0.76, S * 0.06), fill=(255, 255, 255, 200))
    base = Image.alpha_composite(base, stars)

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    big = build()
    for size in (256, 88, 44):
        big.resize((size, size), Image.LANCZOS).save(OUT / f"logo_{size}.png")
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico",
                                               sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("written to", OUT)
