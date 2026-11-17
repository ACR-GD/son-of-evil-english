"""Translate the script in plain-text batches.

  python3 tools/script_batch.py export FIRST_ID|next [COUNT]   print messages to translate
  python3 tools/script_batch.py import FILE...           merge batch files into script_en.json

Batch file format (notes/translation/script/*.txt):

  [141048]
  Let me out! Let me out!

  [1413A8]
  What do you want to know?
  ={>13}Sacred Pool
  ={>13}Poison mist
  ={>13}A solution{>182}Leave

Each text line is word-wrapped to the box width (212 px); a line starting with "=" is kept
as is (menus, deliberate breaks). Blank lines are ignored. "[id] =" keeps the Chinese.
A message that runs into the next one (chain) is padded with blank lines to its own count.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_rom as B
import soe_rom as R

EN = os.path.join(R.NOTES, "script_en.json")
ZH = os.path.join(R.NOTES, "script_zh.json")
FULL, HALF = 13, 6   # original advances: 2-byte / 1-byte glyphs


def zh_positions(line):
    """Words of an original line with their pen x (menus are laid out with spaces)."""
    out, x, cur, start = [], 0, "", 0
    for ch in line:
        if ch in " 　":
            if cur:
                out.append((start, cur))
                cur = ""
            x += HALF if ch == " " else FULL
        else:
            if not cur:
                start = x
            cur += ch
            x += HALF if ord(ch) < 0x80 else FULL
    if cur:
        out.append((start, cur))
    return out


def export(first, count):
    zh = json.load(open(ZH, encoding="utf-8"))
    en = json.load(open(EN, encoding="utf-8"))
    ids = [m["id"] for m in zh]
    # "next": start at the first untranslated message
    i = (next(k for k, m in enumerate(zh) if en[m["id"]].get("en") is None) if first == "next"
         else ids.index(first.upper()))
    for m in zh[i:i + count]:
        flags = []
        if m["portrait"]:
            flags.append(f"portrait={m['portrait']}")
        if m["chain_next"]:
            flags.append(f"CHAIN {len(m['lines'])} lines")
        if m["notice"]:
            flags.append("notice")
        done = " DONE" if en[m["id"]].get("en") is not None else ""
        print(f"[{m['id']}] {' '.join(flags)}{done}")
        for l in m["lines"]:
            if not l:
                continue
            pos = zh_positions(l)
            if len(pos) > 1 or (pos and pos[0][0]):
                print("  " + "  ".join(f"@{x}:{w}" for x, w in pos))
            else:
                print("  " + l)


def wrap(text, widths, max_px=R.DIALOGUE_MAX_PX):
    lines, cur = [], ""
    for word in text.split(" "):
        t = word if not cur else cur + " " + word
        if B.line_width(R.encode_line(t), widths) <= max_px or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def parse(path):
    msgs, cur = {}, None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        m = re.match(r"^\[([0-9A-Fa-f]{6})\]\s*(=?)\s*$", line)
        if m:
            cur = m.group(1).upper()
            msgs[cur] = None if m.group(2) else []
            continue
        if cur is None or not line.strip() or line.startswith("#"):
            continue
        msgs[cur].append(line)
    return msgs


def do_import(paths):
    zh = {m["id"]: m for m in json.load(open(ZH, encoding="utf-8"))}
    en = json.load(open(EN, encoding="utf-8"))
    _, widths = B.load_font()
    problems, n = [], 0
    for path in paths:
        for mid, src in parse(path).items():
            if mid not in zh:
                problems.append(f"{path}: unknown id {mid}")
                continue
            if src is None:
                en[mid]["en"] = None
                continue
            lines = []
            for l in src:
                lines += [l[1:]] if l.startswith("=") else wrap(l.strip(), widths)
            m = zh[mid]
            own = len(m["lines"])
            if m["chain_next"]:
                if len(lines) > own:
                    problems.append(f"{mid}: chain message, max {own} lines: {lines}")
                lines += [""] * (own - len(lines))
            elif len(lines) > R.DIALOGUE_LINES:
                problems.append(f"{mid}: {len(lines)} lines: {lines}")
            for l in lines:
                try:
                    w = B.line_width(R.encode_line(l), widths)
                except Exception as e:
                    problems.append(f"{mid}: cannot encode {l!r}: {e}")
                    continue
                if w > R.DIALOGUE_MAX_PX:
                    problems.append(f"{mid}: {w} px: {l}")
            en[mid]["en"] = lines
            n += 1
    json.dump(en, open(EN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    done = sum(1 for v in en.values() if v.get("en") is not None)
    print(f"imported {n}; translated {done}/{len(en)}")
    for p in problems:
        print("  " + p)


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 50)
    else:
        do_import(sys.argv[2:])
