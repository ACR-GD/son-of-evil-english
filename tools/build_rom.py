"""Build the English Son of Evil ROM and IPS patch.

  python3 tools/build_rom.py [--rom PATH] [--strict]

Inputs
  notes/script_en.json   {id: {"zh": [...], "en": [...] or null}}; null keeps the original bytes
  notes/font_en.png      editable 1-byte font (16x8 grid of 8x12 cells); created on first run
  notes/font_en.json     per-character advance overrides (created on first run)

Outputs (build/)
  The Son of Evil (EN).bin   patched ROM, same byte-swapped format as the original dump
  The Son of Evil (EN).ips   patch against the original dump
  report.txt                 space usage, lines that are too wide, untranslated count

What the patch does
  1. VWF: the 1-byte printer advance (fixed 6 px from $FF9C3E) becomes a per-character width
     table; 1-byte glyphs are drawn 8 px wide; the digit special case is removed.
  2. Pen-position control code {>nn}: 2-byte code $FF nn moves the pen to nn px from the start
     of the line (used to line up menu choices whose cursor positions are fixed).
  3. Every message is re-packed (translated or not) into the space the script used to occupy
     plus the free block at $97D66, and every message-table pointer is rewritten.
"""
import argparse
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R
import ending
import script_batch
import title_gfx
import ui
from PIL import Image

# --- patch locations (68000 addresses) -------------------------------------------------------
HOOK_SB_ADVANCE = 0x08B672   # move.w $FFFF9C3E.l,d7 (6 bytes) -> jsr VWF_WIDTH
HOOK_DB_DRAW = 0x08B694      # jsr $0008B7AC.l        (6 bytes) -> jsr DB_WRAPPER
SB_COLUMNS = 0x08B750        # move.w #5,d0 -> move.w #7,d0
SB_DIGIT_BRANCH = 0x08B73E   # bge.b (digits drawn with 10 rows) -> nop
CODE_AREA = (0x097D66, 0x099168)   # zero-filled, never read by the game (traced)
# The ROM is extended to 3 MB: the third megabyte is the cartridge data-ROM window at $200000
# (the 2+1 MB layout of Sango Fighter; MAME and the repo emulator map a 3 MB file the same way).
# It holds the text that no longer fits in the original 2 MB.
EXT_ROM = (0x200000, 0x300000)
EXTRA_FREE = []

# The "got <item>" popup sizes its box from the byte count and gives up past 28 half-width
# columns ("got " prefix included), so names are kept short. Menus may be tighter: to verify.
STRING_MAX_BYTES = 22
# Inventory/equipment/skill lists draw names in 56 px columns (4 Chinese characters).
LIST_NAME_PX = {"items": 52, "weapons": 52, "armour": 52, "skills": 52, "spells": 52}

FONT_PNG = os.path.join(R.NOTES, "font_en.png")
FONT_JSON = os.path.join(R.NOTES, "font_en.json")
CELL_W, CELL_H = 9, 13   # 8x12 glyph + 1 px grid line


# --- font -------------------------------------------------------------------------------------

def export_font(rom):
    """Write notes/font_en.png from the ROM's 6x12 font, glyphs moved to the left edge."""
    img = Image.new("RGB", (16 * CELL_W + 1, 8 * CELL_H + 1), (200, 200, 255))
    px = img.load()
    for c in range(128):
        g = rom[R.SB_FONT + 12 * c:R.SB_FONT + 12 * c + 12]
        m = 0
        for row in g:
            m |= row
        left = next((x for x in range(8) if m & (0x80 >> x)), 0)
        x0, y0 = (c % 16) * CELL_W + 1, (c // 16) * CELL_H + 1
        for y in range(12):
            for x in range(8):
                on = 0 <= x + left < 8 and (g[y] << left) & (0x80 >> x)
                px[x0 + x, y0 + y] = (0, 0, 0) if on else (255, 255, 255)
    img.save(FONT_PNG)
    json.dump({"_comment": "advance in pixels per character; characters not listed use "
                           "(rightmost lit column + 2). Digits are fixed so numbers line up.",
               " ": 4, **{str(d): 6 for d in range(10)}},
              open(FONT_JSON, "w"), indent=1)
    print(f"wrote {FONT_PNG} and {FONT_JSON} (edit them to restyle the English font)")


def load_font():
    img = Image.open(FONT_PNG).convert("RGB")
    over = json.load(open(FONT_JSON))
    glyphs, widths = [], []
    for c in range(128):
        x0, y0 = (c % 16) * CELL_W + 1, (c // 16) * CELL_H + 1
        rows = []
        right = -1
        for y in range(12):
            b = 0
            for x in range(8):
                r, g, bl = img.getpixel((x0 + x, y0 + y))
                if r + g + bl < 384:
                    b |= 0x80 >> x
                    right = max(right, x)
            rows.append(b)
        glyphs.append(bytes(rows))
        w = over.get(chr(c), right + 2 if right >= 0 else 4)
        widths.append(w)
    # $7F is the blank "figure space" used to pad numbers (same width as a digit).
    glyphs[0x7F] = bytes(12)
    widths[0x7F] = widths[ord("0")]
    return glyphs, widths


def line_width(b, widths):
    w = 0
    i = 0
    while i < len(b):
        c = b[i]
        if c == 0xFF:
            w = b[i + 1]
            i += 2
        elif c >= 0x80:
            w += 13
            i += 2
        else:
            w += widths[c]
            i += 1
    return w


# --- 68000 code -------------------------------------------------------------------------------

def vwf_code(base):
    """Return (bytes, width_table_addr, vwf_addr, db_wrapper_addr) for code placed at `base`.
    Only d7 is used (the printer reloads it), so no registers need saving."""
    code = bytearray()
    # VWF_WIDTH (base): d7 = WIDTHS[char]; the caller then does add.w d7,$FFFF9C2E
    code += bytes.fromhex("7E00")                    # +0  moveq  #0,d7
    code += bytes.fromhex("1E39FFFF9C2D")            # +2  move.b $FFFF9C2D.l,d7  (char code)
    code += bytes.fromhex("1E3B7004")                # +8  move.b (4,pc,d7.w),d7 -> base+14+d7
    code += bytes.fromhex("4E75")                    # +12 rts
    widths_at = base + len(code)                     # +14 128-byte width table
    code += bytes(128)
    # DB_WRAPPER: code $FF nn moves the pen to line start + nn; anything else draws a glyph
    dbw = base + len(code)
    code += bytes.fromhex("0C3900FFFFFF9C2C")        # cmpi.b #$FF,$FFFF9C2C.l
    code += bytes.fromhex("6706")                    # beq.s  pen
    code += bytes.fromhex("4EF90008B7AC")            # jmp    $8B7AC (draw 2-byte glyph)
    code += bytes.fromhex("7E00")                    # pen: moveq #0,d7
    code += bytes.fromhex("1E39FFFF9C2D")            # move.b $FFFF9C2D.l,d7
    code += bytes.fromhex("DE79FFFF9C1E")            # add.w  $FFFF9C1E.l,d7   (line start x)
    code += bytes.fromhex("9E79FFFF9C3C")            # sub.w  $FFFF9C3C.l,d7   (caller adds it)
    code += bytes.fromhex("33C7FFFF9C2E")            # move.w d7,$FFFF9C2E.l
    code += bytes.fromhex("4E75")                    # rts
    return bytes(code), widths_at, base, dbw


# --- packing ----------------------------------------------------------------------------------

class Space:
    def __init__(self, regions):
        self.free = sorted([list(r) for r in regions if r[1] > r[0]])

    def alloc(self, n, align=1):
        best = None
        for r in self.free:       # best fit keeps big holes for big blocks
            start = (r[0] + align - 1) & ~(align - 1)
            if r[1] - start >= n and (best is None or r[1] - r[0] < best[1] - best[0]):
                best = r
        if best is None:
            return None
        a = (best[0] + align - 1) & ~(align - 1)
        if a != best[0]:
            self.free.append([best[0], a])
        best[0] = a + n
        return a

    def total(self):
        return sum(e - s for s, e in self.free)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom")
    ap.add_argument("--strict", action="store_true", help="fail on lines that are too wide")
    args = ap.parse_args()

    orig = R.load_rom(args.rom)
    rom = bytearray(orig) + bytes(EXT_ROM[1] - EXT_ROM[0])
    if not os.path.exists(FONT_PNG):
        export_font(orig)
    glyphs, widths = load_font()

    msgs, tables = R.message_layout(orig)
    en = json.load(open(os.path.join(R.NOTES, "script_en.json"), encoding="utf-8"))
    sen_path = os.path.join(R.NOTES, "strings_en.json")
    sen = json.load(open(sen_path, encoding="utf-8")) if os.path.exists(sen_path) else {}
    lists = R.string_lists(orig)

    problems, wide = [], []
    translated = 0

    def message_bytes(m):
        """Own bytes of a message after translation (portrait + lines, each $00-terminated)."""
        nonlocal translated
        key = "%06X" % m["addr"]
        e = en.get(key, {}).get("en")
        if e is None:
            body = bytes(orig[m["addr"]:m["end"]])
            if m["truncated"]:   # we only claimed its text lines; restore the box's 4 lines
                body += b"\0" * (R.DIALOGUE_LINES - len(m["lines"]))
            return body
        translated += 1
        lines = [R.encode_line(t) for t in e]
        own = len(m["lines"])
        if m["chain_next"] and len(lines) != own:
            problems.append(f"{key}: runs into {m['chain_next']:06X}, needs exactly {own} lines")
        elif not m["chain_next"] and len(lines) > R.DIALOGUE_LINES:
            problems.append(f"{key}: {len(lines)} lines (max {R.DIALOGUE_LINES})")
        if not m["chain_next"]:
            lines += [b""] * (R.DIALOGUE_LINES - len(lines))
        for t, b in zip(e, lines):
            w = line_width(b, widths)
            if w > R.DIALOGUE_MAX_PX:
                wide.append(f"{key}: {w} px > {R.DIALOGUE_MAX_PX}: {t}")
        out = bytes([m["portrait"]]) if m["portrait"] else b""
        return out + b"".join(l + b"\0" for l in lines)

    # Group chains into contiguous blocks.
    blocks, cur = [], []
    for m in msgs:
        cur.append(m)
        if not m["chain_next"]:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)

    # Free space: every message's own bytes, plus the free block after the patch code.
    regions = []
    for m in msgs:
        if regions and regions[-1][1] == m["addr"]:
            regions[-1][1] = m["end"]
        else:
            regions.append([m["addr"], m["end"]])
    for s, e, _ in lists:
        regions.append([s, e])
    for s, e in regions:
        rom[s:e] = b"\0" * (e - s)

    # Patch code + width table + font.
    code, widths_at, vwf_at, dbw_at = vwf_code(CODE_AREA[0])
    rom[CODE_AREA[0]:CODE_AREA[0] + len(code)] = code
    rom[widths_at:widths_at + 128] = bytes(widths)
    free_start = (CODE_AREA[0] + len(code) + 1) & ~1
    for c in range(128):
        rom[R.SB_FONT + 12 * c:R.SB_FONT + 12 * c + 12] = glyphs[c]

    def patch(addr, old, new):
        if bytes(orig[addr:addr + len(old) // 2]) != bytes.fromhex(old):
            raise SystemExit(f"unexpected bytes at {addr:06X} (wrong ROM?)")
        rom[addr:addr + len(new) // 2] = bytes.fromhex(new)

    patch(HOOK_SB_ADVANCE, "3E39FFFF9C3E", "4EB9" + "%08X" % vwf_at)
    patch(HOOK_DB_DRAW, "4EB90008B7AC", "4EB9" + "%08X" % dbw_at)
    patch(SB_COLUMNS, "303C0005", "303C0007")
    patch(SB_DIGIT_BRANCH, "6C34", "4E71")

    space = Space([tuple(r) for r in regions] + [(free_start, CODE_AREA[1])] + EXTRA_FREE)
    space_total = space.total()

    ui_report, ui_problems = ui.apply(orig, rom, space, widths, widths_at, patch)
    problems += ui_problems
    end_report, end_problems = ending.apply(orig, rom, space, widths, patch, line_width,
                                            script_batch.wrap)
    ui_report += end_report
    problems += end_problems
    gfx_report, gfx_problems = title_gfx.apply(rom)
    ui_report += gfx_report
    problems += gfx_problems

    # Name/term lists: rebuilt as one blob per region (same entry count and order), then every
    # `lea list,An` operand is pointed at its entry in the new blob.
    str_new = {}
    strings_translated = 0
    long_names = []
    for s, e, items in lists:
        blob = bytearray()
        offs = []
        for addr, b in items:
            t = sen.get("%06X" % addr, {}).get("en")
            if t is not None:
                b = R.encode_line(t)
                strings_translated += 1
                lst = sen["%06X" % addr]["list"]
                if lst in LIST_NAME_PX:
                    if line_width(b, widths) - 1 > LIST_NAME_PX[lst]:
                        long_names.append(f"{addr:06X} ({lst}): {line_width(b, widths) - 1} px > "
                                          f"{LIST_NAME_PX[lst]}: {t}")
                elif len(b) > STRING_MAX_BYTES and lst != "misc":
                    long_names.append(f"{addr:06X} ({lst}): {len(b)} bytes > {STRING_MAX_BYTES}: {t}")
            offs.append((addr, len(blob)))
            blob += b + b"\0"
        a = space.alloc(len(blob))
        if a is None:
            raise SystemExit("out of ROM space for the name lists")
        rom[a:a + len(blob)] = blob
        for addr, o in offs:
            str_new[addr] = a + o
    for r in R.STRING_REFS:
        struct.pack_into(">I", rom, r, str_new[R.u32(orig, r)])

    # Messages go to the extension ROM, biggest blocks first; the original area keeps the
    # UI text and name lists.
    old_free = space.total()
    space = Space([EXT_ROM])
    space_total += space.total()
    built = [(b, [message_bytes(m) for m in b]) for b in blocks]
    built.sort(key=lambda x: -sum(len(p) for p in x[1]))
    new_addr = {}
    overflow = 0
    for b, parts in built:
        n = sum(len(p) for p in parts)
        a = space.alloc(n)
        if a is None:
            overflow += n
            continue
        for m, p in zip(b, parts):
            new_addr[m["addr"]] = a
            rom[a:a + len(p)] = p
            a += len(p)
    if overflow:
        raise SystemExit(f"out of ROM space: {overflow} bytes did not fit "
                         f"(free {space.total()} of {space_total})")

    for t, ptrs in tables.items():
        for i, p in enumerate(ptrs):
            struct.pack_into(">I", rom, t + 4 * i, new_addr[p])

    # Outputs.
    os.makedirs(R.BUILD, exist_ok=True)
    out_bin = os.path.join(R.BUILD, "The Son of Evil (EN).bin")
    out_ips = os.path.join(R.BUILD, "The Son of Evil (EN).ips")
    R.save_rom(rom, out_bin)
    write_ips(R.swap16(bytes(orig)), R.swap16(bytes(rom)), out_ips)

    used = space_total - space.total() - old_free
    report = [
        f"messages: {len(msgs)}, translated: {translated}",
        f"list strings: {sum(len(i) for _, _, i in lists)}, translated: {strings_translated}",
        f"text space: {used} / {space_total} bytes used; free: {space.total()} at $200000, "
        f"{old_free} in the original 2 MB",
        f"output CRC32: {zlib.crc32(R.swap16(bytes(rom))):08x}",
        *ui_report,
        "", f"problems ({len(problems)}):", *problems,
        "", f"lines wider than the box ({len(wide)}):", *wide,
        "", f"names too long for their menus ({len(long_names)}):", *long_names,
    ]
    open(os.path.join(R.BUILD, "report.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n".join(report[:4 + len(ui_report)]))
    if problems or wide:
        print(f"{len(problems)} problems, {len(wide)} over-wide lines: see build/report.txt")
        if problems or args.strict:
            sys.exit(1)


def write_ips(a, b, path):
    """IPS from a to b; b may be longer (the patcher grows the file to the last record)."""
    out = bytearray(b"PATCH")
    grow = len(b) > len(a)
    a = bytes(a) + bytes(len(b) - len(a))
    i, n = 0, len(a)
    while i < n:
        if a[i] == b[i]:
            i += 1
            continue
        j = i
        while j < n and j - i < 0xFFFF and (a[j] != b[j] or (j + 1 < n and a[j + 1] != b[j + 1])):
            j += 1
        if i == 0x454F46:   # offset "EOF" would end the patch early
            i -= 1
        out += struct.pack(">I", i)[1:] + struct.pack(">H", j - i) + b[i:j]
        i = j
    if grow and a[-1] == b[-1]:   # make sure some record reaches the new end of file
        out += struct.pack(">I", n - 1)[1:] + struct.pack(">H", 1) + b[-1:]
    out += b"EOF"
    open(path, "wb").write(out)
    # self-check
    t = bytearray(a)
    p = 5
    while out[p:p + 3] != b"EOF":
        o = int.from_bytes(out[p:p + 3], "big")
        s = int.from_bytes(out[p + 3:p + 5], "big")
        t[o:o + s] = out[p + 5:p + 5 + s]
        p += 5 + s
    assert bytes(t) == b, "IPS does not reproduce the ROM"


if __name__ == "__main__":
    main()
