"""Builds the high-resolution text glyphs (src/video/text_hd.h): the game's
pixel-art letters and digits are redrawn with free (SIL OFL) vector fonts.

Usage:
  python tools/make_text_atlas.py [snapshot.bin] [--preview out/text_preview.png]

The snapshot (F9 in the game, out/snap/*.bin) provides the tile patterns of
the fonts, which the game loads at boot and never moves. Each glyph listed
below is drawn with its font at 8x, fitted to the box of the original pixel
art, and cut into the game's 8x8 tiles. Writes:
  textures/text/atlas.png   per tile: R = letter, G = outline/shadow,
                            B = top-to-bottom position for the gradient
  textures/text/glyphs.txt  pattern, hash of its pixels, atlas slot and the
                            palette entries (nibbles) of the three colours
The colours are not stored: the game picks them from its palette at run time,
so fades and highlighted menu lines still work. Needs Pillow and numpy.
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import lwhash  # tools/ is on sys.path when run as `python tools/<script>.py`

FONTS = "third_party/fonts"
OUT = "textures/text"
SCALE = 8          # atlas pixels per original pixel
SS = 4             # supersampling of the font rasteriser
PAD = 1            # original pixels of margin around each tile in the atlas
SLOT = (8 + 2 * PAD) * SCALE
COLS = 16          # slots per atlas row (shader: ATLAS_COLS)
VRAM_SIZE = 0x190000

args = sys.argv[1:]
preview = None
if "--preview" in args:
    k = args.index("--preview")
    preview = args[k + 1]
    del args[k:k + 2]
snap = args[0] if args else "out/snap/snap_2806.bin"
vram = open(snap, "rb").read()[-VRAM_SIZE:]


def pattern(p):
    """8x8 nibbles (4 bpp) of tile pattern p"""
    rows = []
    for y in range(8):
        w = struct.unpack_from("<I", vram, p * 32 + y * 4)[0]
        rows.append([(w >> ((7 - x) * 4)) & 15 for x in range(8)])
    return np.array(rows)


def pattern_hash(p):
    return lwhash.fnv1a_bytes(vram[p * 32:p * 32 + 32])


def entry_base(p):
    """Palette base of a 4 bpp tile: name table entries hold the pattern number
    shifted right by one (its low bit in bit 15), and their bits 4-14 select
    the colours"""
    return (p >> 1) & 0x7FF0


def palette_luma(base, n):
    c = struct.unpack_from("<I", vram, 0x100000 + (base | n) * 4)[0]
    r, g, b = (c & 31), (c >> 5) & 31, (c >> 10) & 31
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---- Glyphs ----------------------------------------------------------------
# A glyph is a character and its grid of tile patterns (rows of columns).
# Sets share a font, a size and an edge style:
#   flat     one colour (menu font)
#   shadow   drop shadow below and to the right (yellow captions)
#   outline  dark outline all around (score digits)

def grid(*rows):
    return [list(r) for r in rows]


# Star Wars Trilogy: the score and shield digits are 3x3 tiles (24x24 pixels)
# built from shared pieces (name table entries 0x8B0-0x8D3, the unlit leading
# zero 0x8D4-0x8D9); pattern = entry * 2. A piece is drawn differently in each
# digit, so these are groups: the runtime finds the whole 3x3 block on screen
# (TextHD::groups) and gives each of its cells the digit's own tile.
def digit(*entries):
    e = [0x800 | v for v in entries]
    return grid([2 * v for v in e[0:3]], [2 * v for v in e[3:6]], [2 * v for v in e[6:9]])


digits = [
    ("0", digit(0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB3, 0xB5, 0xB1, 0xB6)),
    ("1", digit(0xB7, 0xB8, 0xB4, 0xB9, 0xBA, 0xB4, 0xBB, 0xBC, 0xB4)),
    ("2", digit(0xBD, 0xB1, 0xB2, 0xB0, 0xB1, 0xB6, 0xBE, 0xB1, 0xBF)),
    ("3", digit(0xBD, 0xB1, 0xB2, 0xC0, 0xB1, 0xC1, 0xBD, 0xB1, 0xB6)),
    ("4", digit(0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA)),
    ("5", digit(0xB0, 0xB1, 0xBF, 0xB5, 0xB1, 0xB2, 0xBD, 0xB1, 0xB6)),   # not seen yet: a guess
    ("6", digit(0xB0, 0xB1, 0xBF, 0xCC, 0xB1, 0xB2, 0xB5, 0xB1, 0xB6)),
    ("7", digit(0xBD, 0xB1, 0xB2, 0xB4, 0xCD, 0xCE, 0xCF, 0xD0, 0xD1)),
    ("8", digit(0xB0, 0xB1, 0xB2, 0xD2, 0xB1, 0xC1, 0xB5, 0xB1, 0xB6)),
    ("9", digit(0xB0, 0xB1, 0xB2, 0xB5, 0xB1, 0xD3, 0xBD, 0xB1, 0xB6)),
    ("0", digit(0xD4, 0xD5, 0xD6, 0xD7, 0xB4, 0xD7, 0xD8, 0xD5, 0xD9)),   # unlit leading zero
]

SETS = [
    {"name": "digits", "font": "Exo2[wght].ttf", "weight": 800, "edge": "outline", "glyphs": digits, "same_roles": True,
     "group": True},
]
for s in SETS:
    s["font"] = os.environ.get("LW_FONT_" + s["name"].upper(), s["font"])


# ---- Analysis of the original pixel art ------------------------------------

def original(glyph):
    """Nibbles of the whole glyph and the palette base of its first tile"""
    tiles = glyph[1]
    img = np.vstack([np.hstack([pattern(p) for p in row]) for row in tiles])
    return img, entry_base(tiles[0][0])


def roles(img, base, edge_style):
    """Palette nibbles of the gradient's top and bottom and of the edge"""
    used = [n for n in range(1, 16) if (img == n).any()]
    counts = {n: int((img == n).sum()) for n in used}
    edge = 0
    if edge_style != "flat" and len(used) > 1:
        edge = min(used, key=lambda n: palette_luma(base, n))
    body = [n for n in used if n != edge]
    total = sum(counts[n] for n in body)
    bottom = max(body, key=lambda n: counts[n])
    top = max((n for n in body if counts[n] * 8 >= total), key=lambda n: palette_luma(base, n))
    return top, bottom, edge


def body_box(img, edge):
    ys, xs = np.nonzero((img != 0) & (img != edge))
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


# ---- Drawing ---------------------------------------------------------------

def dilate(mask, r):
    """Round dilation of a coverage mask by r pixels"""
    if r <= 0:
        return mask
    out = mask.copy()
    ir = int(np.ceil(r))
    for dy in range(-ir, ir + 1):
        for dx in range(-ir, ir + 1):
            d = np.hypot(dx, dy)
            if d > r + 0.5:
                continue
            w = min(1.0, r + 0.5 - d)
            out = np.maximum(out, w * np.roll(np.roll(mask, dy, 0), dx, 1))
    return out


def shift(mask, dx, dy):
    return np.roll(np.roll(mask, dy, 0), dx, 1)


def render_set(s):
    font_path = os.path.join(FONTS, s["font"])
    analysed = []
    shared = None   # sets with "same_roles": the colours of the first glyph for all of the same palette
    for g in s["glyphs"]:
        img, base = original(g)
        top, bottom, edge = roles(img, base, s["edge"])
        if s.get("same_roles"):
            if shared and shared[0] == base:
                top, bottom, edge = shared[1]
            elif not shared:
                shared = (base, (top, bottom, edge))
        analysed.append((g, img, base, (top, bottom, edge), body_box(img, edge)))
    # One size for the whole set: capitals and digits as tall as the original's
    caps = [a for a in analysed if a[0][0].isupper() or a[0][0].isdigit()]
    cap_top = min(a[4][1] for a in caps)
    baseline = max(a[4][3] for a in caps)
    cap_h = baseline - cap_top
    probe = ImageFont.truetype(font_path, 1000)
    if s.get("weight"):
        probe.set_variation_by_axes([s["weight"]])
    ref = probe.getbbox("H", anchor="ls")   # ref[1]: top of the capitals, negative
    size = cap_h * SCALE * SS * 1000.0 / -ref[1]
    font = ImageFont.truetype(font_path, max(1, int(round(size))))
    if s.get("weight"):
        font.set_variation_by_axes([s["weight"]])

    out = []
    for g, img, base, rl, box in analysed:
        ch = g[0]
        th, tw = img.shape
        k = SCALE * SS
        W, H = (tw + 2 * PAD) * k, (th + 2 * PAD) * k
        # Letter drawn alone, then placed: same baseline for the set, centred
        # on the original letter and narrowed if it is wider than it
        bb = font.getbbox(ch, anchor="ls")
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        layer = Image.new("L", (gw + 4 * k, gh + 4 * k), 0)
        ImageDraw.Draw(layer).text((2 * k - bb[0], 2 * k - bb[1]), ch, font=font, fill=255, anchor="ls")
        glyph = np.asarray(layer, dtype=np.float32) / 255.0
        ox, oy = 2 * k, 2 * k   # where the glyph's bbox starts inside `layer`
        orig_w = (box[2] - box[0]) * k
        sx = 1.0
        if gw > orig_w * 1.04:
            sx = orig_w * 1.04 / gw
        if sx != 1.0:
            nw = max(1, int(round(layer.width * sx)))
            glyph = np.asarray(layer.resize((nw, layer.height), Image.LANCZOS), dtype=np.float32) / 255.0
            ox *= sx
            gw *= sx
        canvas = np.zeros((H, W), np.float32)
        cx = (PAD + (box[0] + box[2]) / 2.0) * k
        by = (PAD + baseline) * k
        x0 = int(round(cx - gw / 2.0 - ox))
        y0 = int(round(by + bb[1] - oy))
        gh_, gw_ = glyph.shape
        ys0, xs0 = max(0, -y0), max(0, -x0)
        ys1, xs1 = min(gh_, H - y0), min(gw_, W - x0)
        canvas[y0 + ys0:y0 + ys1, x0 + xs0:x0 + xs1] = glyph[ys0:ys1, xs0:xs1]
        # Down to atlas resolution, then the edge around it
        W, H = W // SS, H // SS
        letter = canvas.reshape(H, SS, W, SS).mean(axis=(1, 3))
        if s["edge"] == "outline":
            edge = dilate(letter, 0.85 * SCALE)
        elif s["edge"] == "shadow":
            edge = shift(dilate(letter, 0.3 * SCALE), int(0.7 * SCALE), int(0.9 * SCALE))
        else:
            edge = np.zeros_like(letter)
        # Gradient position: 0 at the top of the capitals, 1 at the baseline
        ys = ((np.arange(H, dtype=np.float32) + 0.5) / SCALE - PAD - cap_top) / max(cap_h, 1)
        grad = np.repeat(np.clip(ys, 0, 1)[:, None], W, 1)
        rgb = np.dstack([letter, edge, grad])
        out.append((g, rl, (rgb * 255 + 0.5).astype(np.uint8)))
    return out


# ---- Atlas -------------------------------------------------------------------

entries = {}   # pattern -> (hash, tile image, roles)
groups = []    # (grid of patterns, roles, tiles)
for s in SETS:
    for g, rl, big in render_set(s):
        tiles = []
        for ty, row in enumerate(g[1]):
            for tx, p in enumerate(row):
                x, y = tx * 8 * SCALE, ty * 8 * SCALE
                tiles.append(big[y:y + SLOT, x:x + SLOT])
                if not s.get("group") and p not in entries:
                    entries[p] = (pattern_hash(p), tiles[-1], rl)
        if s.get("group"):
            groups.append((g[1], rl, tiles))

rows = (len(entries) + sum(len(t) for _, _, t in groups) + COLS - 1) // COLS
atlas = np.zeros((rows * SLOT, COLS * SLOT, 4), np.uint8)
atlas[..., 3] = 255
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "glyphs.txt"), "w") as f:
    f.write(f"# High-resolution text glyphs made from {snap}\n")
    f.write("# pattern hash slot top bottom edge\n")
    for slot, (p, (h, tile, rl)) in enumerate(sorted(entries.items())):
        sy, sx = divmod(slot, COLS)
        atlas[sy * SLOT:(sy + 1) * SLOT, sx * SLOT:(sx + 1) * SLOT, :3] = tile
        f.write(f"{p:04x} {h:016x} {slot} {rl[0]:x} {rl[1]:x} {rl[2]:x}\n")
    # Groups: G width height top bottom edge, then per cell pattern:hash:slot
    slot = len(entries)
    for g, rl, tiles in groups:
        cells = []
        for k, p in enumerate([p for row in g for p in row]):
            sy, sx = divmod(slot, COLS)
            atlas[sy * SLOT:(sy + 1) * SLOT, sx * SLOT:(sx + 1) * SLOT, :3] = tiles[k]
            cells.append(f"{p:04x}:{pattern_hash(p):016x}:{slot}")
            slot += 1
        f.write(f"G {len(g[0])} {len(g)} {rl[0]:x} {rl[1]:x} {rl[2]:x} " + " ".join(cells) + "\n")
Image.fromarray(atlas, "RGBA").save(os.path.join(OUT, "atlas.png"))
print(f"{OUT}/atlas.png: {len(entries)} patterns, {len(groups)} groups, {COLS * SLOT}x{rows * SLOT}")

if preview:
    # Every set as the game would show it, coloured with the snapshot's palette
    def colour(base, n):
        c = struct.unpack_from("<I", vram, 0x100000 + (base | n) * 4)[0]
        return np.array([(c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31, ((c >> 10) & 31) * 255 // 31],
                        np.float32)
    lines = []
    for s in SETS:
        rendered = render_set(s)
        width = sum(len(g[1][0]) * 8 * SCALE for g, _, _ in rendered)
        height = max(len(g[1]) * 8 * SCALE for g, _, _ in rendered)
        line = np.zeros((height, width, 3), np.float32) + np.array([30, 34, 70], np.float32)
        x = 0
        for g, rl, big in rendered:
            base = entry_base(g[1][0][0])
            th, tw = len(g[1]) * 8 * SCALE, len(g[1][0]) * 8 * SCALE
            px = big[PAD * SCALE:PAD * SCALE + th, PAD * SCALE:PAD * SCALE + tw].astype(np.float32) / 255.0
            top, bottom, edge = (colour(base, n) for n in rl)
            fill = top * (1 - px[..., 2:3]) + bottom * px[..., 2:3]
            region = line[:th, x:x + tw]
            if rl[2]:
                region[:] = region * (1 - px[..., 1:2]) + edge * px[..., 1:2]
            region[:] = region * (1 - px[..., 0:1]) + fill * px[..., 0:1]
            x += tw
        lines.append(line)
    width = max(l.shape[1] for l in lines)
    sheet = np.vstack([np.pad(l, ((4, 4), (0, width - l.shape[1]), (0, 0))) for l in lines])
    Image.fromarray(sheet.clip(0, 255).astype(np.uint8), "RGB").save(preview)
    print("Preview:", preview)
