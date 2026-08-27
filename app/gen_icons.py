"""Generate PWA icons (192, 512, maskable, apple-touch) and favicon.

Run: python -m app.gen_icons
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

STATIC = Path(__file__).resolve().parent / "static"


def _gradient(size: int) -> Image.Image:
    """A diagonal blue->purple->pink gradient fill, matching the chat logo."""
    img = Image.new("RGB", (size, size), (0, 0, 0))
    px = img.load()
    # stops: blue #4f8cff -> indigo #6366f1 -> pink #ec4899
    stops = [(79, 140, 255), (99, 102, 241), (236, 72, 153)]
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * max(size - 1, 1))
            t = min(max(t, 0.0), 1.0)
            seg = t * (len(stops) - 1)
            i = int(seg)
            f = seg - i
            if i >= len(stops) - 1:
                r, g, b = stops[-1]
            else:
                a = stops[i]
                bb = stops[i + 1]
                r = int(a[0] + (bb[0] - a[0]) * f)
                g = int(a[1] + (bb[1] - a[1]) * f)
                b = int(a[2] + (bb[2] - a[2]) * f)
            px[x, y] = (r, g, b)
    return img


def _draw_glyph(img: Image.Image) -> Image.Image:
    """Draw a centered chat-bubble glyph with a white fill."""
    size = img.width
    d = ImageDraw.Draw(img)
    m = size * 0.22  # margin
    body = (m, m, size - m, size - m)
    d.rounded_rectangle(body, radius=size * 0.28, fill=(255, 255, 255, 255))
    # tail (triangle pointing down-left)
    tail = [
        (size * 0.34, size * 0.70),
        (size * 0.34, size * 0.86),
        (size * 0.52, size * 0.70),
    ]
    d.polygon(tail, fill=(255, 255, 255, 255))
    # three dots
    r = max(2, int(size * 0.045))
    cy = size * 0.50
    spacing = size * 0.18
    for dx in (-spacing, 0, spacing):
        d.ellipse((size * 0.5 + dx - r, cy - r, size * 0.5 + dx + r, cy + r), fill=(99, 102, 241))
    return img


def _icon(size: int, maskable: bool = False) -> Image.Image:
    base = _gradient(size)
    if maskable:
        # full-bleed gradient background, glyph smaller + centered within safe zone (~80%)
        base = _gradient(size).convert("RGBA")
        gsize = int(size * 0.55)
        glyph_small = Image.new("RGBA", (gsize, gsize), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph_small)
        gm = gsize * 0.18
        gd.rounded_rectangle((gm, gm, gsize - gm, gsize - gm), radius=gsize * 0.28, fill=(255, 255, 255, 255))
        gd.polygon(
            [(gsize * 0.34, gsize * 0.70), (gsize * 0.34, gsize * 0.86), (gsize * 0.52, gsize * 0.70)],
            fill=(255, 255, 255, 255),
        )
        r = max(2, int(gsize * 0.045))
        cy = gsize * 0.50
        sp = gsize * 0.18
        for dx in (-sp, 0, sp):
            gd.ellipse((gsize * 0.5 + dx - r, cy - r, gsize * 0.5 + dx + r, cy + r), fill=(99, 102, 241))
        base.alpha_composite(glyph_small, ((size - gsize) // 2, (size - gsize) // 2))
        return base

    return _draw_glyph(base).convert("RGBA")


def main() -> None:
    icons = {
        "icon-192.png": _icon(192),
        "icon-512.png": _icon(512),
        "icon-maskable-192.png": _icon(192, maskable=True),
        "icon-maskable-512.png": _icon(512, maskable=True),
        "apple-touch-icon.png": _icon(180),
    }
    for name, im in icons.items():
        im.save(STATIC / name, "PNG")
        print("wrote", name, im.size)
    # favicon (32px)
    fav = _icon(32).convert("RGBA")
    fav.save(STATIC / "favicon.png", "PNG")
    print("wrote favicon.png", fav.size)


if __name__ == "__main__":
    main()
