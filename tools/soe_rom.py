"""Shared helpers for The Son of Evil (Super A'Can, Taiwan) translation tools.

All addresses are 68000 addresses (the cartridge is mapped at $000000). The dump on disk is
byte-swapped (16-bit little-endian); `load_rom()` returns it in 68000 (big-endian) order and
`save_rom()` swaps it back.

Text engine summary (see notes/engine.md):
  - Script: scene table at SCENE_TABLE (264 longs); each scene block has, at +$14, a pointer
    to a table of 32-bit message pointers.
  - Message: optional portrait byte $01-$1F, then lines terminated by $00. The dialogue box
    prints 4 lines; shorter messages run on into the following bytes (see "chains").
  - Characters: $01-$7F = 1 byte (6x12 font at SB_FONT); $80-$FF = lead byte of a 2-byte
    code, glyph index = 127*(hi-$80) + (lo-$80) into the 12x12 font at DB_FONT.
"""
import json
import os
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # son-of-evil/
REPO = os.path.dirname(ROOT)
NOTES = os.path.join(ROOT, "notes")
BUILD = os.path.join(ROOT, "build")

ROM_NAME = "The Son of Evil (Taiwan).bin"
ROM_SIZE = 0x200000
ROM_CRC32 = 0x9f6119a7  # byte-swapped dump as distributed

SCENE_TABLE = 0x140B54
SCENE_COUNT = 264
SCENE_MSG_TABLE_OFS = 0x14

SB_FONT = 0x196D36      # 128 glyphs x 12 bytes (1 byte per row, MSB = leftmost pixel)
DB_FONT = 0x197336      # 2196 glyphs x 18 bytes (12x12, row-major bitstream)
DB_GLYPHS = 2196

# Name/term lists: null-terminated strings, entry n found by skipping n terminators from a
# base address. Two regions (binary data sits between them at $1A33D2).
STRING_REGIONS = [(0x1A2D44, 0x1A33D2), (0x1A34E2, 0x1A39C2)]
# Address of each `lea $xxxxxx.l,An` operand that points into the lists (operand -> list name)
STRING_LIST_NAMES = {0x1A2D44: "misc", 0x1A2D54: "characters", 0x1A2D88: "items",
                     0x1A2F66: "weapons", 0x1A306C: "armour", 0x1A319A: "skills",
                     0x1A32E8: "spells", 0x1A34E2: "enemies", 0x1A36A0: "places"}
STRING_REFS = [0x087E38, 0x08F31A, 0x08F32A, 0x08F33A, 0x08F34A, 0x08F35A, 0x08F36A,
               0x08F382, 0x08F3D6, 0x08F3E4, 0x08F400, 0x090818, 0x090826, 0x090842,
               0x09A810, 0x09A820, 0x09A830, 0x09A840, 0x09A850, 0x09A86A, 0x09A882,
               0x09A99A, 0x0A2250, 0x0B11A6, 0x0B11B6, 0x0B11C6, 0x0B11D6, 0x0B11E6]

DIALOGUE_LINES = 4
DIALOGUE_MAX_PX = 212   # text starts at x=8 inside a 224 px box


def find_rom(path=None):
    cands = [path] if path else []
    cands += [os.path.join(ROOT, ROM_NAME),
              os.path.join(ROOT, "rom", ROM_NAME),
              os.path.join(REPO, "emulator", "ROMs", ROM_NAME)]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    raise SystemExit(f"ROM not found; put '{ROM_NAME}' in {ROOT} or pass --rom")


def swap16(b):
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


def load_rom(path=None):
    raw = open(find_rom(path), "rb").read()
    if len(raw) != ROM_SIZE:
        raise SystemExit(f"unexpected ROM size {len(raw):#x}")
    rom = swap16(raw)
    if rom[0:4] != b"\x00\xff\xff\xe0":
        raise SystemExit("ROM does not look like the byte-swapped Son of Evil dump")
    return bytearray(rom)


def save_rom(rom, path):
    open(path, "wb").write(swap16(bytes(rom)))


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def glyph_index(code):
    return 127 * ((code >> 8) - 0x80) + ((code & 0xFF) - 0x80)


def glyph_code(index):
    return ((0x80 + index // 127) << 8) | (0x80 + index % 127)


def load_glyph_table():
    d = json.load(open(os.path.join(NOTES, "glyph_table.json"), encoding="utf-8"))
    return {int(k): v for k, v in d["glyphs"].items()}


# ---------------------------------------------------------------------------------------------
# Script structure
# ---------------------------------------------------------------------------------------------

def message_tables(rom):
    """Return {table_addr: [message_addr, ...]} in scene order (tables shared by scenes once)."""
    tables = {}
    for si in range(SCENE_COUNT):
        scene = u32(rom, SCENE_TABLE + 4 * si)
        t = u32(rom, scene + SCENE_MSG_TABLE_OFS)
        if t in tables or not (0x100000 <= t < ROM_SIZE):
            continue
        ptrs = []
        while True:
            p = u32(rom, t + 4 * len(ptrs))
            if not (0x100000 <= p < ROM_SIZE) or (ptrs and t + 4 * len(ptrs) >= min(ptrs)):
                break
            ptrs.append(p)
        tables[t] = ptrs
    return tables


def split_lines(rom, start, end):
    """Split rom[start:end] into (portrait, [line bytes...]) where each line ended in $00.
    Returns None for the line list if the region doesn't end on a terminator."""
    o = start
    portrait = None
    if 1 <= rom[o] <= 0x1F:
        portrait = rom[o]
        o += 1
    lines = []
    cur = bytearray()
    while o < end:
        c = rom[o]
        if c == 0:
            lines.append(bytes(cur))
            cur = bytearray()
            o += 1
        elif c >= 0x80:
            cur += rom[o:o + 2]
            o += 2
        else:
            cur.append(c)
            o += 1
    if cur or o != end:
        return portrait, None
    return portrait, lines


def scan_message(rom, start, nlines=DIALOGUE_LINES):
    """Byte length of a message printed with `nlines` lines (portrait byte included)."""
    o = start
    if 1 <= rom[o] <= 0x1F:
        o += 1
    for _ in range(nlines):
        while rom[o] != 0:
            o += 2 if rom[o] >= 0x80 else 1
        o += 1
    return o - start


def message_layout(rom):
    """Work out every message's own byte segment.

    Messages are packed back to back. A message whose 4-line print runs past the start of the
    next message is part of a *chain*: the dialogue box shows its own lines followed by the
    next message's bytes. Chains must stay contiguous when text is relocated.

    Returns a list of dicts sorted by address:
      addr, end (exclusive end of this message's own bytes), portrait, lines (list of bytes),
      chain_next (addr of the message it runs into, or None), refs [(table, index)].
    """
    tables = message_tables(rom)
    refs = {}
    for t, ptrs in tables.items():
        for i, p in enumerate(ptrs):
            refs.setdefault(p, []).append((t, i))
    addrs = sorted(refs)
    out = []
    for k, a in enumerate(addrs):
        full = a + scan_message(rom, a)
        nxt = addrs[k + 1] if k + 1 < len(addrs) else None
        truncated = False
        if nxt is not None and full >= nxt:
            end, chain = nxt, (nxt if full > nxt else None)
            portrait, lines = split_lines(rom, a, end)
        else:
            chain = None
            portrait, lines = split_lines(rom, a, full)
            if not all(valid_line(l) for l in lines):
                # Short notice (e.g. "got item X") followed by non-text data: claim only the
                # lines that are clearly text, and none of the trailing empty ones.
                keep = []
                for l in lines:
                    if not valid_line(l):
                        break
                    keep.append(l)
                while keep and not keep[-1]:
                    keep.pop()
                lines = keep
                truncated = True
            end = a + (1 if portrait else 0) + sum(len(l) + 1 for l in lines)
        if lines is None:
            raise ValueError(f"message {a:06x} does not end on a line terminator")
        out.append(dict(addr=a, end=end, portrait=portrait, lines=lines,
                        chain_next=chain, truncated=truncated, refs=refs[a]))
    return out, tables


def valid_line(b):
    i = 0
    while i < len(b):
        c = b[i]
        if c >= 0x80:
            if i + 1 >= len(b) or b[i + 1] < 0x80:
                return False
            if glyph_index((c << 8) | b[i + 1]) >= DB_GLYPHS:
                return False
            i += 2
        elif 0x20 <= c < 0x7F:
            i += 1
        else:
            return False
    return True


def string_lists(rom):
    """[(region_start, region_end, [(addr, bytes), ...])] for the name/term lists."""
    out = []
    for s, e in STRING_REGIONS:
        items = []
        o = s
        while o < e:
            j = o
            while rom[j] != 0:
                j += 2 if rom[j] >= 0x80 else 1
            items.append((o, bytes(rom[o:j])))
            o = j + 1
        if o != e:
            raise ValueError(f"string region {s:06x}-{e:06x} does not end on a terminator")
        out.append((s, e, items))
    for r in STRING_REFS:
        if u16(rom, r - 2) & 0xF1FF != 0x41F9 or u32(rom, r) not in STRING_LIST_NAMES:
            raise ValueError(f"unexpected instruction at {r - 2:06x}")
    return out


# ---------------------------------------------------------------------------------------------
# Text codec
# ---------------------------------------------------------------------------------------------

def decode_line(b, table):
    """Bytes -> display string. Unknown/special bytes become {xx} / {xxxx}."""
    s = []
    i = 0
    while i < len(b):
        c = b[i]
        if c >= 0x80:
            code = (c << 8) | b[i + 1]
            g = glyph_index(code)
            ch = table.get(g) if 0 <= g < DB_GLYPHS else None
            s.append(ch if ch and ch not in "{}" else "{%04X}" % code)
            i += 2
        elif 0x20 <= c < 0x7F and c not in (0x7B, 0x7D):
            s.append(chr(c))
            i += 1
        else:
            s.append("{%02X}" % c)
            i += 1
    return "".join(s)


def encode_line(text):
    """English string -> bytes. ASCII is 1 byte per char; {xx} / {xxxx} insert raw codes;
    {>nn} moves the pen to nn pixels from the start of the line (patched control code)."""
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            j = text.index("}", i)
            h = text[i + 1:j]
            if h.startswith(">"):            # {>nn}: move the pen to nn px from line start
                out += bytes([0xFF, int(h[1:])])
            else:
                out += bytes.fromhex(h)
            i = j + 1
            continue
        o = ord(ch)
        if not (0x20 <= o < 0x7F):
            raise ValueError(f"character {ch!r} is not in the 1-byte font: {text!r}")
        out.append(o)
        i += 1
    if 0 in out:
        raise ValueError(f"line contains a $00 byte: {text!r}")
    return bytes(out)
