"""UI layer of the build: text referenced directly by code (menus, popups, battle commands,
save/load, item descriptions, party names). Called by build_rom.py.

Everything here is relocated: new text goes into free space and the instructions that
pointed at the old text are rewritten (see find_ui_strings.py for how they are found). The
original bytes are left in place.

Code patches:
  - party names: the 8-byte fixed-width name records ($0AE27A) become null-terminated names
    from a pointer table. $0AE268 / $0A212A (copy one record) jump to COPY_NAME; the menu
    lines that hold two names ($0AE230, $0AE252) call NAMES2, which puts a pen code between
    them so the second name stays in its 48 px slot.
  - popup boxes ($087CB8 and $0A1786): the box width was counted in bytes (1 per 1-byte
    character, 2 per 2-byte one) and popups over 28 columns were dropped. POPW measures the
    real width with the VWF table (2-byte glyphs: 16 px, the popup advance), so the box fits
    the text and the limit becomes 224 px.
  - skills list ($09B4BA) no longer drops the last two bytes of each name.
  - number padding ($0B0784, $0A2186) uses the blank 6 px "figure space" $7F instead of an
    ASCII space, so right-aligned numbers stay aligned with proportional spaces.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R
import find_ui_strings

UI_JSON = os.path.join(R.NOTES, "ui_en.json")
FIGURE_SPACE = 0x7F

NAME_RECORDS = 0x0AE27A
NAME_COUNT = 9
NAME_MAX_PX = 48
DESC_TABLE = 0x0B08F0          # 256 word offsets from DESC_BASE (read pc-relative, stays put)
DESC_BASE = 0x0B0AF0
DESC_BASE_REF = 0x0B08AC       # lea DESC_BASE,a4
DESC_MAX_PX = 144
POPUP_LOOPS = {0x087CB8: 0x087DAA, 0x0A1786: 0x0A184C}   # loop start -> "too long" target
POPUP_LOOP_BYTES = "42441E1C67126A041E1C524452440C44001C6200"


def _tw(b, widths):
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


def zh_width(s, adv):
    return sum(adv[0] if ord(ch) > 0x7F else adv[1] for ch in s)


def encode_entry(key, e, widths, problems):
    """Return the bytes of one UI string (all lines, each $00-terminated)."""
    out = bytearray()
    zh = e["zh"]
    if len(e["en"]) != len(zh):
        problems.append(f"ui {key}: {len(e['en'])} lines, the original has {len(zh)}")
    for line in e["en"]:
        if isinstance(line, str):
            b = R.encode_line(line)
            if "max_px" in e and _tw(b, widths) - 1 > e["max_px"]:
                problems.append(f"ui {key}: {_tw(b, widths) - 1} px > {e['max_px']}: {line}")
            out += b + b"\0"
            continue
        adv = e["adv"]
        x = 0
        pos = []
        for seg in line:
            sx = seg[3] if len(seg) > 3 else x
            pos.append(sx)
            x = sx + zh_width(seg[0], adv)
        b = bytearray()
        for k, seg in enumerate(line):
            zh_seg, en_seg = seg[0], seg[1]
            if not en_seg:
                continue
            nxt = next((pos[j] for j in range(k + 1, len(line))
                        if line[j][0].strip() or line[j][1]), None)
            slot = seg[2] if len(seg) > 2 else (nxt - pos[k] if nxt is not None
                                                else zh_width(zh_seg, adv))
            eb = R.encode_line(en_seg)
            if _tw(eb, widths) - 1 > slot:
                problems.append(f"ui {key}: '{en_seg}' is {_tw(eb, widths) - 1} px, "
                                f"slot of '{zh_seg}' is {slot}")
            if pos[k] or b:
                b += bytes([0xFF, pos[k]])
            b += eb
        out += b + b"\0"
    return bytes(out)


def assemble_names_code(base, table_addr):
    copy = bytes.fromhex("3C1CDC46DC46" "4DF9") + struct.pack(">I", table_addr) + \
        bytes.fromhex("2C766000" "16DE66FC" "538B" "4E75")
    copy_at = base
    names2_at = base + len(copy)
    names2 = (bytes.fromhex("4EB9") + struct.pack(">I", copy_at) +
              bytes.fromhex("16FC00FF" "16FC0030" "4EB9") + struct.pack(">I", copy_at) +
              bytes.fromhex("421B4E75"))
    return copy + names2, copy_at, names2_at


def assemble_popw(widths_addr):
    return (bytes.fromhex("2F08" "41F9") + struct.pack(">I", widths_addr) +
            bytes.fromhex("7800"            # moveq #0,d4
                          "7E00"            # L: moveq #0,d7
                          "1E1C"            # move.b (a4)+,d7
                          "6712"            # beq.s done
                          "6B08"            # bmi.s dbcs
                          "1E307000"        # move.b (0,a0,d7.w),d7
                          "D847"            # add.w d7,d4
                          "60F0"            # bra.s L
                          "528C"            # dbcs: addq.l #1,a4
                          "06440010"        # addi.w #16,d4
                          "60E8"            # bra.s L
                          "5E44"            # done: addq.w #7,d4
                          "E64C"            # lsr.w #3,d4   (pixels -> tiles, rounded up)
                          "205F"            # movea.l (sp)+,a0
                          "4E75"))


def apply(orig, rom, space, widths, widths_addr, patch):
    """Patch the UI. Returns (report lines, problems)."""
    if not os.path.exists(UI_JSON):
        return ["ui: notes/ui_en.json missing, UI untouched"], []
    ui = json.load(open(UI_JSON, encoding="utf-8"))
    problems, report = [], []

    def put(data, align=2):
        a = space.alloc(len(data), align)
        if a is None:
            raise SystemExit("out of ROM space for UI text")
        rom[a:a + len(data)] = data
        return a

    # 1. Strings referenced by code.
    refs = find_ui_strings.scan(orig)
    done = 0
    for key, e in ui["strings"].items():
        if e.get("en") is None:
            continue
        a = int(key, 16)
        if a not in refs:
            problems.append(f"ui {key}: no code reference found")
            continue
        new = put(encode_entry(key, e, widths, problems), 1)
        for op_at, _ in refs[a]:
            struct.pack_into(">I", rom, op_at + 2, new)
        done += 1
    report.append(f"ui strings: {done} of {len(ui['strings'])} translated")

    # 2. Layout script edits (menu rectangles).
    fields = {"x": 1, "y": 2, "w": 3, "h": 4, "sx": 5, "sy": 6}
    for p in ui.get("layout", []):
        at = int(p["at"], 16)
        if orig[at] != 0x0E:
            raise SystemExit(f"layout patch at {at:06X} is not a text-copy opcode")
        for k, v in p.items():
            if k in fields:
                rom[at + fields[k]] = v

    # 3. Party names.
    names = ui.get("names", [])
    if names and any(n["en"] for n in names):
        if len(names) != NAME_COUNT:
            problems.append(f"ui names: need {NAME_COUNT} entries")
        ptrs = []
        for i, n in enumerate(names):
            b = R.encode_line(n["en"] or "")
            if _tw(b, widths) - 1 > NAME_MAX_PX:
                problems.append(f"ui name {n['en']}: wider than {NAME_MAX_PX} px")
            ptrs.append(put(b + b"\0", 1))
        table = put(b"".join(struct.pack(">I", p) for p in ptrs), 2)
        code_len = len(assemble_names_code(0, 0)[0])
        base = space.alloc(code_len, 2)
        code, copy_at, names2_at = assemble_names_code(base, table)
        rom[base:base + len(code)] = code
        jmp = "4EF9%08X" % copy_at
        patch(0x0AE268, "4DF9000AE27A", jmp)
        patch(0x0A212A, "4DF9000AE27A", jmp)
        patch(0x0AE230, "61366134421B", "4EB9%08X" % names2_at)
        patch(0x0AE252, "61146112421B", "4EB9%08X" % names2_at)
        report.append("ui names: replaced")

    # 4. Item descriptions.
    descs = ui.get("descriptions", {})
    if any(d["en"] is not None for d in descs.values()):
        blob = bytearray()
        new_off = {}
        for key, d in sorted(descs.items()):
            old = int(key, 16) - DESC_BASE
            if d["en"] is None:
                j = int(key, 16)
                while orig[j]:
                    j += 2 if orig[j] >= 0x80 else 1
                b = bytes(orig[int(key, 16):j])
            else:
                b = R.encode_line(d["en"])
                if _tw(b, widths) - 1 > DESC_MAX_PX:
                    problems.append(f"ui description {key}: {_tw(b, widths) - 1} px > "
                                    f"{DESC_MAX_PX}: {d['en']}")
            new_off[old] = len(blob)
            blob += b + b"\0\0"
        base = put(bytes(blob), 2)
        for i in range(256):
            o = R.u16(orig, DESC_TABLE + 2 * i)
            struct.pack_into(">H", rom, DESC_TABLE + 2 * i, new_off[o])
        patch(DESC_BASE_REF, "49F9%08X" % DESC_BASE, "49F9%08X" % base)
        report.append("ui descriptions: replaced")

    # 5. Popup box width in pixels.
    popw = put(assemble_popw(widths_addr), 2)
    for loop, too_long in POPUP_LOOPS.items():
        disp = too_long - (loop + 10 + 2)
        new = "4EB9%08X" % popw + "0C44001C" + "6200%04X" % (disp & 0xFFFF) + "4E71" * 5
        patch(loop, POPUP_LOOP_BYTES + "%04X" % (R.u16(orig, loop + 20)), new)

    # 6. The skills list cut the last 2 bytes off each name (拳譜 -> 拳); keep English whole.
    patch(0x09B4BA, "574E4216", "534E4216")

    # 7. Figure space for number padding.
    patch(0x0B0784, "1ABC0020", "1ABC%04X" % FIGURE_SPACE)
    patch(0x0A2186, "1E3C00F0", "1E3C%04X" % (FIGURE_SPACE - 0x30))
    return report, problems
