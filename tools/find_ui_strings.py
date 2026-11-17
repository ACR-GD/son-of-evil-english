"""Inventory of text referenced directly by code (menus, popups, item-use messages...).

Scans every instruction operand that can hold an address (lea / movea.l # / move.l # / pea)
for pointers to valid text that isn't part of the script or the name lists, and prints
the address, the referencing instructions and the text.

  python3 tools/find_ui_strings.py            # table
  python3 tools/find_ui_strings.py --json     # notes/ui_strings_zh.json
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R

# 68000 opcodes whose 32-bit operand follows the opcode word (masked by 0xF1FF / exact)
OPS = {0x41F9: "lea", 0x207C: "movea.l #", 0x203C: "move.l #", 0x4879: "pea"}
EXACT = {0x23FC: "move.l #,abs"}


def scan(rom):
    msgs, _ = R.message_layout(rom)
    covered = set()
    for m in msgs:
        covered.update(range(m["addr"], m["end"]))
    for s, e, _ in R.string_lists(rom):
        covered.update(range(s, e))
    found = {}
    for o in range(0x2000, 0x1C0000, 2):
        op = R.u16(rom, o)
        kind = EXACT.get(op) or OPS.get(op & 0xF1FF)
        if not kind:
            continue
        v = R.u32(rom, o + 2)
        if not (0x2000 <= v < R.ROM_SIZE) or v in covered:
            continue
        j = v
        while j < R.ROM_SIZE and rom[j] and j - v < 64:
            j += 2 if rom[j] >= 0x80 else 1
        b = bytes(rom[v:j])
        if rom[j] != 0 or not b or not R.valid_line(b):
            continue
        dbcs = sum(1 for i in range(len(b)) if b[i] >= 0x80) // 2
        if dbcs < 1:
            continue
        found.setdefault(v, []).append((o, kind))
    return found


def main():
    rom = R.load_rom()
    table = R.load_glyph_table()
    found = scan(rom)
    out = []
    for v in sorted(found):
        j = v
        while rom[j]:
            j += 2 if rom[j] >= 0x80 else 1
        out.append({"id": "%06X" % v, "zh": R.decode_line(rom[v:j], table),
                    "refs": ["%06X %s" % r for r in found[v]]})
    if "--json" in sys.argv:
        with open(os.path.join(R.NOTES, "ui_strings_zh.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    for e in out:
        print(f"{e['id']}  {', '.join(e['refs']):40}  {e['zh']}")
    print(f"{len(out)} strings")


if __name__ == "__main__":
    main()
