"""Intro captions and title logo (graphics, not font text).

Intro captions ($1B6900): six 256x24 1bpp blocks at $1D69C8 (MSB = left pixel), plotted into
the text canvas; captions use blocks 0, 1-2, 3-4, 5. Source: notes/gfx/intro_captions.png
(256x144, white = ink).

Title logo ($1B6976, table $1E66D8): 4bpp tiles at $1E6724 (VRAM $18000) and two 32x8
tilemaps at $1EDC88 (32 words per row):
  - gold screen: map 0, palette 1. 1 = black, 2..11 = top-to-bottom gold gradient,
    12 = highlight, 14 = shadow.
  - fire screen: map 1, palette 0. 1 = black, 0 = transparent (an animated flame layer shows
    through the letters), 13 = light outline, 15 = outline, 2 = drop shadow.
Both are generated from one shape, notes/gfx/title_logo.png (256x64, white = letter).
Only tiles 0..$110 (the original logo's range) are rewritten; tile 0 must stay solid 1.

  python3 tools/title_gfx.py preview OUT.png     # render both logo screens and the captions
"""
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R

GFX = os.path.join(R.NOTES, "gfx")
CAPTIONS_PNG = os.path.join(GFX, "intro_captions.png")
LOGO_PNG = os.path.join(GFX, "title_logo.png")

CAPTIONS = 0x1D69C8
CAPTION_BYTES = 6 * 24 * 32
LOGO_TILES = 0x1E6724
LOGO_MAPS = 0x1EDC88
MAX_TILES = 0x111
MAP_W, MAP_H = 32, 8


def caption_bytes():
    im = Image.open(CAPTIONS_PNG).convert("L")
    assert im.size == (256, 144), "intro_captions.png must be 256x144"
    out = bytearray()
    for y in range(144):
        for xb in range(32):
            b = 0
            for k in range(8):
                if im.getpixel((xb * 8 + k, y)) >= 128:
                    b |= 0x80 >> k
            out.append(b)
    return bytes(out)


def logo_pixels():
    m = Image.open(LOGO_PNG).convert("L")
    assert m.size == (256, 64), "title_logo.png must be 256x64"
    W, H = m.size
    ink = [[m.getpixel((x, y)) >= 128 for x in range(W)] for y in range(H)]

    def at(x, y):
        return 0 <= x < W and 0 <= y < H and ink[y][x]

    rows = [y for y in range(H) if any(ink[y])]
    top, bot = rows[0], rows[-1]
    gold = [[1] * W for _ in range(H)]
    fire = [[1] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if ink[y][x]:
                g = 2 + min(9, (y - top) * 10 // max(1, bot - top + 1))
                if not at(x, y - 1) or not at(x - 1, y):
                    g = 12
                elif not at(x, y + 1) or not at(x + 1, y):
                    g = 14
                gold[y][x] = g
                fire[y][x] = 0
            else:
                near = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if at(x + dx, y + dy)]
                if near:
                    # light from the top-left: outline pixels above/left of a letter are bright
                    fire[y][x] = 13 if any(dy > 0 or dx > 0 for dx, dy in near) else 15
                elif at(x - 2, y - 2) or at(x - 1, y - 2) or at(x - 2, y - 1):
                    fire[y][x] = 2
    return gold, fire


def build_logo():
    """-> (tile bytes list, gold map words, fire map words)"""
    gold, fire = logo_pixels()
    tiles, index = [], {}

    def tile_of(px, tx, ty):
        return tuple(tuple(px[ty * 8 + y][tx * 8 + x] for x in range(8)) for y in range(8))

    def add(t):
        variants = [(t, 0), (tuple(r[::-1] for r in t), 0x800), (t[::-1], 0x400),
                    (tuple(r[::-1] for r in t[::-1]), 0xC00)]
        for v, flip in variants:
            if v in index:
                return index[v] | flip
        index[t] = len(tiles)
        tiles.append(t)
        return index[t]

    add(tuple(tuple([1] * 8) for _ in range(8)))          # tile 0: solid black
    gmap = [0x1000 | add(tile_of(gold, tx, ty)) for ty in range(MAP_H) for tx in range(MAP_W)]
    fmap = [add(tile_of(fire, tx, ty)) for ty in range(MAP_H) for tx in range(MAP_W)]
    data = []
    for t in tiles:
        b = bytearray()
        for row in t:
            for x in range(0, 8, 2):
                b.append(row[x] << 4 | row[x + 1])
        data.append(bytes(b))
    return data, gmap, fmap


def apply(rom):
    report, problems = [], []
    if os.path.exists(CAPTIONS_PNG):
        rom[CAPTIONS:CAPTIONS + CAPTION_BYTES] = caption_bytes()
        report.append("intro captions: replaced")
    if os.path.exists(LOGO_PNG):
        data, gmap, fmap = build_logo()
        if len(data) > MAX_TILES:
            problems.append(f"title logo: {len(data)} tiles, max {MAX_TILES}")
        else:
            for i, b in enumerate(data):
                rom[LOGO_TILES + 32 * i:LOGO_TILES + 32 * i + 32] = b
            rom[LOGO_MAPS:LOGO_MAPS + 1024] = struct.pack(">512H", *(gmap + fmap))
            report.append(f"title logo: replaced ({len(data)} of {MAX_TILES} tiles)")
    return report, problems


def preview(path):
    """Gold and fire logo with the game's palettes, plus the captions."""
    gold_pal = [0x56b4, 0x0000, 0x16db, 0x1279, 0x0e38, 0x09d7, 0x0996, 0x0555, 0x04f4, 0x00b3,
                0x0072, 0x0051, 0x437f, 0x2238, 0x0911, 0x004a]
    fire_pal = [0x0000, 0x0000, 0x28c6, 0x0935, 0x057b, 0x0dbc, 0x09dd, 0x0e1d, 0x1a5f, 0x26bf,
                0x331f, 0x3f7f, 0x00b1, 0x7f39, 0x6252, 0x456b]
    rgb = lambda c: ((c & 31) * 8, (c >> 5 & 31) * 8, (c >> 10 & 31) * 8)
    gold, fire = logo_pixels()
    im = Image.new("RGB", (256, 64 * 2 + 144))
    for y in range(64):
        for x in range(256):
            im.putpixel((x, y), rgb(gold_pal[gold[y][x]]))
            f = fire[y][x]
            im.putpixel((x, 64 + y), (230, 110 + (x * 7 + y * 13) % 90, 20) if f == 0 else rgb(fire_pal[f]))
    im.paste(Image.open(CAPTIONS_PNG).convert("RGB"), (0, 128))
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(path)
    print("tiles:", len(build_logo()[0]), "of", MAX_TILES)


if __name__ == "__main__":
    if sys.argv[1] == "preview":
        preview(sys.argv[2])
