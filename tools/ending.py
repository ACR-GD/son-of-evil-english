"""Text outside the script tables: story cutscenes and the staff roll (notes/translation/ending.txt).

Cutscenes ($1B7CD0 table): `lea text,a4 / jsr $1B8344` prints a 4-line message in the normal
dialogue box. The English copy is placed in free space and the lea operand repointed.

Staff roll ($1B5E20 init, $1B5B62 per frame): the init prints two strings into the text
canvas with the 12x12 printer (a 4-line sheet at y=2 with 16 px lines, and "AIDA" at y=66
with the reviewer's name at x=48), then each of 16 pages copies four strips of canvas tiles
to the screen. A page record is 4 x (canvas tile, tilemap byte offset, tile count): label top
and bottom rows, name top and bottom rows. The English build lays the labels and names out
on the sheet itself and rewrites the records to match.
"""
import math
import os
import re
import struct

import soe_rom as R

SRC = os.path.join(R.NOTES, "translation", "ending.txt")

CUTSCENE_REFS = {0x1B8732: 0x1B86E8, 0x1B8754: 0x1B86FE, 0x1B876E: 0x1B8714,
                 0x1B884A: 0x1B8804, 0x1B88A6: 0x1B882C, 0x1B89A8: 0x1B895E,
                 0x1B8A02: 0x1B8974, 0x1B8A68: 0x1B898A, 0x1B8AEE: 0x1B8AD0}

SHEET_REF = 0x1B5EAC        # move.l #$1B5F03,$FF9C22 (4-line sheet at y=2)
AIDA_REF = 0x1B5E7C         # move.l #$1B5EFA,$FF9C22 (one line at y=66)
PAGE_TABLE = 0x1B5C90       # 16 page pointers
PAGES = 12                  # pages 1..12 carry credits (0 and 13-15 are blank)
SHEET_LINES, LINE_TILE_ROWS, CANVAS_COLS = 4, 2, 32
AIDA_ROW, PLAYER_TILE, PLAYER_TILES = 8, 0x106, 22
LABEL_OFS, NAME_OFS = 6, 0x0A      # tilemap byte offsets (x = 24 and 40 px)


def parse():
    msgs, credits, cur = {}, [], None
    for raw in open(SRC, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        m = re.match(r"^\[([0-9A-Fa-f]{6}|credits)\]\s*$", line)
        if m:
            cur = m.group(1).upper()
            if cur != "CREDITS":
                msgs[int(cur, 16)] = []
            continue
        if cur == "CREDITS":
            label, name = line.lstrip("=").split("|")
            credits.append((label, name))
        else:
            msgs[int(cur, 16)].append(line)
    return msgs, credits


def apply(orig, rom, space, widths, patch, line_width, wrap):
    report, problems = [], []
    msgs, credits = parse()

    def put(data):
        a = space.alloc(len(data))
        if a is None:
            raise SystemExit("ending: out of ROM space")
        rom[a:a + len(data)] = data
        return a

    # --- cutscenes ---
    for addr, src in msgs.items():
        lines = []
        for l in src:
            lines += [l[1:]] if l.startswith("=") else wrap(l.strip(), widths)
        if len(lines) > R.DIALOGUE_LINES:
            problems.append(f"ending {addr:06X}: {len(lines)} lines")
        for l in lines:
            if line_width(R.encode_line(l), widths) > R.DIALOGUE_MAX_PX:
                problems.append(f"ending {addr:06X}: too wide: {l}")
        lines += [""] * (R.DIALOGUE_LINES - len(lines))
        a = put(b"".join(R.encode_line(l) + b"\0" for l in lines))
        ref = CUTSCENE_REFS[addr]
        patch(ref, "49F9%08X" % addr, "49F9%08X" % a)

    # --- staff roll ---
    if len(credits) != PAGES:
        problems.append(f"ending: {len(credits)} credit pages, need {PAGES}")
        return report, problems
    items = []                          # unique texts to lay out on the sheet, in order
    for label, name in credits:
        for t in (label, name):
            if t not in ("AIDA", "@player") and t not in items:
                items.append(t)
    tiles = {t: math.ceil((line_width(R.encode_line(t), widths) + 1) / 8) for t in items}
    # text -> (canvas row, col, tiles); first fit, widest first. Canvas tile 0 stays blank:
    # empty screen cells point at it.
    place, used = {}, [1] + [0] * (SHEET_LINES - 1)
    for t in sorted(items, key=lambda t: -tiles[t]):
        line = next((i for i in range(SHEET_LINES) if used[i] + tiles[t] <= CANVAS_COLS), None)
        if line is None:
            problems.append(f"ending: staff names do not fit the sheet (at {t!r})")
            return report, problems
        place[t] = (line * LINE_TILE_ROWS, used[line], tiles[t])
        used[line] += tiles[t]
    place["AIDA"] = (AIDA_ROW, 0, math.ceil((line_width(R.encode_line("AIDA"), widths) + 1) / 8))
    sheet = []
    for ln in range(SHEET_LINES):
        row = sorted((c, t) for t, (r, c, n) in place.items()
                     if t != "AIDA" and r == ln * LINE_TILE_ROWS)
        s = "".join(("{>%d}" % (c * 8) if c else "") + t for c, t in row)   # {>0} would be $FF00
        sheet.append(R.encode_line(s) + b"\0")
    sheet_at = put(b"".join(sheet))
    aida_at = put(R.encode_line("AIDA") + b"\0")
    patch(SHEET_REF + 2, "001B5F03", "%08X" % sheet_at)
    patch(AIDA_REF + 2, "001B5EFA", "%08X" % aida_at)

    for p, (label, name) in enumerate(credits, start=1):
        rec = R.u32(orig, PAGE_TABLE + 4 * p)
        r, c, n = place[label]
        out = struct.pack(">3H", r * 32 + c, LABEL_OFS, n) + struct.pack(">3H", (r + 1) * 32 + c, LABEL_OFS, n)
        if name == "@player":
            out += struct.pack(">3H", PLAYER_TILE, NAME_OFS, PLAYER_TILES)
            out += struct.pack(">3H", PLAYER_TILE + 32, NAME_OFS, PLAYER_TILES)
        else:
            r, c, n = place[name]
            out += struct.pack(">3H", r * 32 + c, NAME_OFS, n) + struct.pack(">3H", (r + 1) * 32 + c, NAME_OFS, n)
        rom[rec:rec + 24] = out
    report.append(f"ending: {len(msgs)} cutscene messages, {PAGES} staff pages "
                  f"(sheet tiles used per line: {used})")
    return report, problems
