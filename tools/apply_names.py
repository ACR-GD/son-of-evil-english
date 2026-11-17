"""Apply notes/translation/names.txt (list|zh|en lines) to notes/strings_en.json."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R

src = os.path.join(R.NOTES, "translation", "names.txt")
dst = os.path.join(R.NOTES, "strings_en.json")
names = {}
for line in open(src, encoding="utf-8"):
    line = line.rstrip("\n")
    if line and not line.startswith("#"):
        lst, zh, en = line.split("|")
        names[(lst, zh)] = en
s = json.load(open(dst, encoding="utf-8"))
n = 0
for v in s.values():
    en = names.get((v["list"], v["zh"]))
    if en is not None:
        v["en"] = en
        n += 1
json.dump(s, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [f"{v['list']}|{v['zh']}" for v in s.values() if v["zh"] and v.get("en") is None]
print(f"{n} entries set; untranslated: {missing}")
