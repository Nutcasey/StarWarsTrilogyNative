"""Star Wars Trilogy: high-resolution HUD labels (SCORE, SHIELD, LIGHT Lv.)
as 2D replacements (src/video/pack2d.h), made from a capture of the
foreground (F12 in the game, in space or on the ground with the HUD up).

Usage:
  python tools/make_swt_labels.py out/2d/capture_N [--preview out/2d/labels_preview.png]

For each label the capsule around it is the original picture made smooth at
8x, and the letters are drawn again with a vector font, coloured from the
original letters (their gradient). The level digit of LIGHT Lv. is left to
the game (it changes). Writes textures/2d/swt_<label>.txt and .png.
Needs Pillow and numpy.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "third_party/fonts/Orbitron[wght].ttf"
WEIGHT = 700
S = 8   # picture pixels per original pixel

# name, cells (x, y, w, h), letters' box in pixels (x0, y0, x1, y1 inclusive),
# text, cells left to the game (x, y, w, h) or None
LABELS = [
    ("score", (27, 2, 11, 3), (227, 20, 291, 30), "SCORE", None),
    ("shield", (32, 37, 12, 3), (265, 305, 337, 315), "SHIELD", None),
    ("light", (40, 1, 18, 4), (353, 19, 445, 29), "LIGHT Lv.", (55, 2, 2, 2)),
]

args = sys.argv[1:]
preview = None
if "--preview" in args:
    k = args.index("--preview")
    preview = args[k + 1]
    del args[k:k + 2]
if len(args) != 1:
    sys.exit(__doc__)
base = args[0]
capture = np.asarray(Image.open(base + ".png").convert("RGBA")).astype(np.float32)
cells = [line.split() for line in open(base + ".cells")]


def is_letter(px):
    return px[..., 3] > 0 & (px[..., 1] > 150)


def smooth_up(img):
    """Pixel art to S times its size with smooth edges: each channel
    resampled, the edges of the opaque part made sharp again"""
    h, w = img.shape[:2]
    a0 = img[..., 3:4] / 255.0
    pre = np.concatenate([img[..., :3] * a0, img[..., 3:4]], -1)   # premultiplied
    big = Image.fromarray(pre.clip(0, 255).astype(np.uint8), "RGBA").resize((w * S, h * S), Image.NEAREST)
    big = np.asarray(big.filter(ImageFilter.GaussianBlur(S * 0.35))).astype(np.float32)
    a = big[..., 3:4] / 255.0
    rgb = big[..., :3] / np.maximum(a, 1e-3)
    a = np.clip((a - 0.5) * 4.0 + 0.5, 0.0, 1.0)   # edges sharp again, now smooth
    # Colours: the stair steps blurred away, then a little contrast back
    return np.concatenate([rgb, a * 255.0], -1)


def font_for(cap_px):
    probe = ImageFont.truetype(FONT, 1000)
    probe.set_variation_by_axes([WEIGHT])
    top = -probe.getbbox("H", anchor="ls")[1]
    f = ImageFont.truetype(FONT, max(1, int(round(cap_px * 1000.0 / top))))
    f.set_variation_by_axes([WEIGHT])
    return f


os.makedirs("textures/2d", exist_ok=True)
previews = []
for name, (cx, cy, cw, ch), (lx0, ly0, lx1, ly1), text, keep in LABELS:
    x0, y0 = cx * 8, cy * 8
    crop = capture[y0:y0 + ch * 8, x0:x0 + cw * 8].copy()
    # The letters: bright green to yellow inside their box
    box = np.zeros(crop.shape[:2], bool)
    box[ly0 - y0:ly1 - y0 + 1, lx0 - x0:lx1 - x0 + 1] = True
    letters = box & (crop[..., 3] > 0) & (crop[..., 1] > 150)
    # Their colours spread around them (nearest letter pixel), for the new ones
    colour = crop.copy()
    filled = letters.copy()
    for _ in range(6):
        grow = filled.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh = np.roll(np.roll(filled, dy, 0), dx, 1)
            src = np.roll(np.roll(colour, dy, 0), dx, 1)
            take = sh & ~grow
            colour[take] = src[take]
            grow |= take
        filled = grow
    # The capsule without them: the dark inside where they were
    inside = box & ~letters & (crop[..., 3] > 0)
    dark = np.median(crop[inside], axis=0) if inside.any() else np.array([0, 0, 0, 255.0])
    plain = crop.copy()
    plain[box] = dark
    hd = smooth_up(plain)
    # The new letters, as tall as the old ones and as wide as their box
    font = font_for((ly1 - ly0 + 1) * S)
    bb = font.getbbox(text, anchor="ls")
    layer = Image.new("L", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), 0)
    ImageDraw.Draw(layer).text((4 - bb[0], 4 - bb[1]), text, font=font, fill=255, anchor="ls")
    layer = layer.crop(layer.getbbox())
    tw, th = (lx1 - lx0 + 1) * S, (ly1 - ly0 + 1) * S
    layer = layer.resize((tw, th), Image.LANCZOS)
    cover = np.zeros(hd.shape[:2], np.float32)
    ox, oy = (lx0 - x0) * S, (ly0 - y0) * S
    cover[oy:oy + th, ox:ox + tw] = np.asarray(layer, np.float32) / 255.0
    tint = Image.fromarray(colour.clip(0, 255).astype(np.uint8), "RGBA").resize(
        (cw * 8 * S, ch * 8 * S), Image.NEAREST).filter(ImageFilter.GaussianBlur(S))
    tint = np.asarray(tint).astype(np.float32)
    a = cover[..., None]
    hd[..., :3] = hd[..., :3] * (1 - a) + tint[..., :3] * a
    hd[..., 3] = np.maximum(hd[..., 3], cover * 255.0)
    Image.fromarray(hd.clip(0, 255).astype(np.uint8), "RGBA").save(f"textures/2d/swt_{name}.png")
    with open(f"textures/2d/swt_{name}.txt", "w") as f:
        f.write(f"# Star Wars Trilogy HUD label, made from {base} (tools/make_swt_labels.py)\n")
        f.write(f"rect {cx} {cy} {cw} {ch}\n")
        for yy in range(cy, cy + ch):
            for xx in range(cx, cx + cw):
                kept = keep and keep[0] <= xx < keep[0] + keep[2] and keep[1] <= yy < keep[1] + keep[3]
                f.write(("0" if kept else cells[yy][xx]) + "\n")
    print(f"textures/2d/swt_{name}.png: {cw * 8 * S}x{ch * 8 * S}")
    previews.append(hd)

if preview:
    w = max(p.shape[1] for p in previews)
    sheet = np.vstack([np.pad(p, ((8, 8), (0, w - p.shape[1]), (0, 0))) for p in previews])
    bg = np.zeros_like(sheet) + np.array([40, 40, 90, 255], np.float32)
    a = sheet[..., 3:4] / 255.0
    out = bg[..., :3] * (1 - a) + sheet[..., :3] * a
    Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB").save(preview)
    print("Preview:", preview)
