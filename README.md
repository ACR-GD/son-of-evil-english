# The Son of Evil (邪惡之子) — English translation (work in progress)

Super A'Can, Funtech 1995. These tools dump the script, rebuild the ROM with a variable-width
English font, and write an IPS patch.

Original dump: `The Son of Evil (Taiwan).bin`, 2,097,152 bytes, CRC32 `9f6119a7`
(byte-swapped, as distributed). The tools look for it in this folder, in `rom/`, or in
`../emulator/ROMs/`, or take `--rom PATH`.

No ROM is included. You need your own dump of the game; the tools rebuild everything else
from it. The tracing harness in `tools/harness/` builds against the Super A'Can emulator
checked out next to this repository (`../emulator`).

## Workflow

```bash
python3 tools/dump_script.py     # notes/script_zh.{json,txt}, notes/strings_zh.json,
                                 # and the translation templates if they don't exist yet
python3 tools/build_rom.py       # build/The Son of Evil (EN).bin + .ips + report.txt
```

- **Dialogue**: edit the batch files in `notes/translation/script/*.txt` (plain text, one
  `[id]` block per message, auto-wrapped to the 212 px box; lines starting with `=` are kept
  as is; format in `tools/script_batch.py`), then
  `python3 tools/script_batch.py import notes/translation/script/*.txt` to update
  `notes/script_en.json`. `script_batch.py export ID|next [N]` prints the Chinese with menu
  pen positions. A message marked `chain_next` in `script_zh.json` must keep at most its
  original number of lines. Glossary: `notes/translation/glossary.md`.
- **Name lists**: `notes/translation/names.txt`, applied with `python3 tools/apply_names.py`.
- **Names, items, places, enemies, skills**: `notes/strings_en.json`. Keep each entry to
  22 bytes or fewer. Empty entries are unused slots; leave them empty.
- **Codes inside text**: `{>nn}` moves the pen to nn px from the start of the line (for menu
  choices; see message `157750`). `{xx}` / `{xxxx}` insert raw bytes.
- **Menus, popups, battle commands, save/load, item descriptions, party names**:
  `notes/ui_en.json` (see its `_comment`). Menu words are drawn into fixed slots of a text
  canvas that the menu screens copy rectangles from, so each word has a pixel limit that the
  build checks; `tools/layout.py` decodes the screen layouts. Item, weapon, armour, skill and
  spell names must fit 52 px (inventory columns).
- **Font**: edit `notes/font_en.png` (8×12 cells, black = ink). The advance is the rightmost
  ink column + 2 unless set in `notes/font_en.json` (space = 4, digits = 6).

`build/report.txt` lists over-wide lines, wrong line counts and remaining space. The build
fails on line-count problems; `--strict` also fails on over-wide lines.

## Status

- **The ROM is now 3 MB**: the third megabyte is the cartridge data-ROM window at `$200000`
  (2+1 MB layout, as Sango Fighter; MAME and the repo emulator load it) and holds all the
  dialogue. The IPS patch grows the file. ~900 KB free there.
- **Script**: all 2004 messages and all name lists have a first-pass English translation
  (2026-11-17). Verified in the emulator through the opening. Needs a playthrough for
  context errors (speaker portraits 9-12 are party members whose identity was guessed from
  context) and polish.

- VWF, English font, message/name relocation and pointer rewriting work and are tested in the
  repo emulator through the opening scene.
- With nothing translated, the rebuilt ROM shows the same Chinese text as the original; the
  only visible change is proportional ASCII punctuation.
- UI: every code-referenced string is translated (main menu and sub-screens, item
  descriptions, popups, save/load, battle commands, shop words, item-use messages), party
  names are variable-width, popup boxes are sized in pixels. Tested in the emulator: main
  menu, items, skills, equipment, status, formation, save, item popup. Not yet seen in the
  emulator: battle, shops/inn, load screen, level-up and other popups.
- Ending: story cutscenes and the staff roll are in English (`notes/translation/ending.txt`,
  `tools/ending.py`), tested in the emulator; the reviewer page (shown only if the player
  earned it at Funtech) is untested. The 24×24 printer is dead code.
- Intro captions and title logo are English (`notes/gfx/intro_captions.png`,
  `notes/gfx/title_logo.png`, applied by `tools/title_gfx.py`; `tools/make_title_art.py`
  redraws them from macOS fonts, `tools/title_gfx.py preview OUT.png` shows both logo
  screens). The Funtech boot logo is left as is. See `notes/engine.md`.

## Tools

- `tools/ui.py` the UI layer of the build; `tools/find_ui_strings.py` inventory of
  code-referenced text; `tools/layout.py` menu layout decoder
- `tools/soe_rom.py` ROM layout, script structure, text codec
- `tools/dump_script.py`, `tools/build_rom.py`
- `tools/harness/` tracing build of the repo emulator (memory-access logging with PC,
  screenshots, RAM/VRAM dumps, save states), used to reverse-engineer the text engine
- `tools/glyph_ocr/` how `notes/glyph_table.json` was made (OCR + Zhuyin-order check +
  manual review)
