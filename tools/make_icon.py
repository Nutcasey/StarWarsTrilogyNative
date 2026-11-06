"""Builds res/app.ico: a placeholder icon (a bright four-pointed star on a
dark round field), drawn from scratch so it carries no artwork from the game
or the film. Replace it with a final design before the public release.
Usage: python tools/make_icon.py
"""
import math
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "res", "app.ico")


def draw(size, ss=4):
    s = size * ss
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, s - 1, s - 1], fill=(12, 14, 26, 255), outline=(230, 190, 60, 255), width=max(ss, s // 24))
    c, r_out, r_in = s / 2, s * 0.40, s * 0.08
    pts = []
    for k in range(8):
        a = math.pi / 4 * k - math.pi / 2
        r = r_out if k % 2 == 0 else r_in
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    d.polygon(pts, fill=(255, 236, 170, 255))
    return im.resize((size, size), Image.LANCZOS)


def main():
    sizes = [256, 64, 48, 32, 24, 16]
    big = draw(256)
    big.save(DST, sizes=[(n, n) for n in sizes], append_images=[draw(n) for n in sizes[1:]])
    print(f"{DST}: {', '.join(map(str, sizes))}")


if __name__ == "__main__":
    main()
