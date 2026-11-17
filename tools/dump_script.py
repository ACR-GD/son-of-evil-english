"""Dump every dialogue/script message of The Son of Evil.

Writes:
  notes/script_zh.json   one entry per message (id = ROM address), decoded with the glyph table
  notes/script_zh.txt    the same, human-readable
  notes/script_en.json   translation template (only created if it doesn't exist yet)

Usage: python3 tools/dump_script.py [--rom PATH]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom")
    args = ap.parse_args()

    rom = R.load_rom(args.rom)
    table = R.load_glyph_table()
    msgs, tables = R.message_layout(rom)
    by_addr = {m["addr"]: m for m in msgs}

    entries = []
    for m in msgs:
        # What the 4-line dialogue box actually shows (own lines + chained messages' bytes).
        shown = R.split_lines(rom, m["addr"], m["addr"] + R.scan_message(rom, m["addr"]))[1]
        entries.append({
            "id": "%06X" % m["addr"],
            "portrait": m["portrait"],
            "lines": [R.decode_line(l, table) for l in m["lines"]],
            "chain_next": ("%06X" % m["chain_next"]) if m["chain_next"] else None,
            "notice": m["truncated"] or None,
            "shown": [R.decode_line(l, table) for l in shown] if m["chain_next"] else None,
            "refs": ["%06X[%d]" % r for r in m["refs"]],
        })

    os.makedirs(R.NOTES, exist_ok=True)
    with open(os.path.join(R.NOTES, "script_zh.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)

    with open(os.path.join(R.NOTES, "script_zh.txt"), "w", encoding="utf-8") as f:
        for e in entries:
            head = f"[{e['id']}]"
            if e["portrait"]:
                head += f" portrait={e['portrait']}"
            if e["chain_next"]:
                head += f" -> runs into {e['chain_next']}"
            f.write(head + "\n")
            for l in e["lines"]:
                f.write("  " + l + "\n")
            f.write("\n")

    en_path = os.path.join(R.NOTES, "script_en.json")
    if not os.path.exists(en_path):
        tmpl = {e["id"]: {"zh": e["lines"], "en": None} for e in entries}
        with open(en_path, "w", encoding="utf-8") as f:
            json.dump(tmpl, f, ensure_ascii=False, indent=1)
        print(f"created translation template {en_path}")

    # Name/term lists (items, characters, places...). Empty entries are unused slots but still
    # count for indexing, so they must stay.
    bases = sorted(R.STRING_LIST_NAMES)
    strings = []
    for s, e, items in R.string_lists(rom):
        for addr, b in items:
            name = R.STRING_LIST_NAMES[max(x for x in bases if x <= addr)]
            strings.append({"id": "%06X" % addr, "list": name, "zh": R.decode_line(b, table)})
    with open(os.path.join(R.NOTES, "strings_zh.json"), "w", encoding="utf-8") as f:
        json.dump(strings, f, ensure_ascii=False, indent=1)
    sen_path = os.path.join(R.NOTES, "strings_en.json")
    if not os.path.exists(sen_path):
        tmpl = {x["id"]: {"list": x["list"], "zh": x["zh"], "en": None} for x in strings}
        with open(sen_path, "w", encoding="utf-8") as f:
            json.dump(tmpl, f, ensure_ascii=False, indent=1)
        print(f"created translation template {sen_path}")
    print(f"{len(strings)} list strings ({sum(1 for x in strings if x['zh'])} non-empty)")

    total = sum(m["end"] - m["addr"] for m in msgs)
    chains = sum(1 for m in msgs if m["chain_next"])
    unknown = sum(l.count("{") for e in entries for l in e["lines"])
    print(f"{len(tables)} message tables, {len(msgs)} messages, {total} bytes of text, "
          f"{chains} chained, {unknown} undecoded codes")


if __name__ == "__main__":
    main()
