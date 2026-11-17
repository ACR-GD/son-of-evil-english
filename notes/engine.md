# The Son of Evil — text engine notes

All addresses are 68000 addresses. The dump (`The Son of Evil (Taiwan).bin`, 2 MB,
CRC32 `9f6119a7`) is byte-swapped; `tools/soe_rom.py` swaps it on load and save.

## Rendering

- Text is drawn pixel by pixel into a 4bpp bitmap canvas in work RAM at `$FF0000`
  (32×16 tiles = 256×128 px). Pixel plot: `$08B91A` (colour in `$FF9C2A/2B`).
  Dirty tile rows (`$FF9924` bitmask) are DMA'd to VRAM by `$08BA96`.
- Glyphs are transparent: only lit pixels are written. Nothing has to be shifted or OR-ed
  for a VWF; only the pen advance matters.
- Box frame: `$08B86C`. Dialogue box set-up: `$08A946` (box 224×72 at 0,0; text at 8,8).

## Printer `$08B612`

| RAM | Meaning | Dialogue |
|---|---|---|
| `$FF9C22` | text pointer (`$FF9C32` = cursor) | |
| `$FF9C1E`/`$FF9C20` | start x / y | 8 / 8 |
| `$FF9C28` | lines to print | 4 |
| `$FF9C3A` | line height | 14 |
| `$FF9C3C` / `$FF9C3E` | advance for 2-byte / 1-byte glyphs | 13 / 6 |
| `$FF9C26` | glyphs per frame | 1 |
| `$FF9C2C` | current character code | |
| `$FF9C2E`/`$FF9C30` | pen x / y | |

Byte stream: `$00` end of line · `$01`–`$7F` one-byte glyph (`$08B6FA`, 6×12 font at
`$196D36`, 12 bytes/glyph, digits drawn with only rows 2–11) · `$80`–`$FF` lead byte of a
two-byte glyph (`$08B7AC`).

Two-byte glyph index = `127*(hi-$80) + (lo-$80)` into the 12×12 font at `$197336`
(18 bytes/glyph, 2196 glyphs, ends `$1A12EE`). Order: punctuation, full-width digits and
Latin, then every character sorted by Zhuyin (each initial starts with its Zhuyin letter).
Not Big5. Table: `notes/glyph_table.json`.

A second printer at `$1B6B68` draws 2-byte glyphs from a 24×24 font at `$1D5E40`
(72 bytes/glyph). It is dead code: nothing calls it, and the font is referenced only by it.

## Ending, cutscenes and staff roll (handled by tools/ending.py)

- Story cutscenes: table at `$1B7CF2` indexed by `$FFAEDE`, run by `$1B7A54` (d2 = index).
  Entries 13–15 and 17 print text with `lea text,a4 / jsr $1B8344` (normal 224×72 box,
  4 lines). Text at `$1B8732`… sits between code, so English copies go to free space.
- Ending entry `$1A39C2` (dragon flight, staff roll, "THE END", which is a graphic). Staff
  roll: init `$1B5E20` prints a sheet into the canvas (4 lines at y=2, 16 px lines;
  "AIDA" at y=66 and the reviewer name from `$FF802C` at x=48), per-frame `$1B5B62`. Page
  table `$1B5C90` (16 pointers; pages 1–12 used, 12 = reviewer, skipped if `$FF802C` is 0);
  each page is 4 × (canvas tile, tilemap byte offset, count). Canvas tile 0 must stay blank
  (empty cells use it).
- Test trick: patch `$08F446` (first scene opcode) with `jmp $1A39C2` to see the ending, or
  `moveq #n,d2 / jsr $1B7A54` to play cutscene n.

## Script

- Scene table `$140B54`: 264 pointers to scene blocks. Scene block `+$14` → table of
  32-bit message pointers (107 distinct tables, 2004 messages, ~107.5 KB).
- Message: optional portrait byte `$01`–`$1F` (drawn by `$0B21F8` at 8,80), then lines.
  The opcode handler is at `$08F446`.
- **Chains**: 108 short messages (lists, notices) are followed directly by another message,
  so the 4-line box shows the next message's bytes as its later lines. They must stay
  contiguous and keep their own line count.
- **Notices**: ~20 one-line messages sit just before non-text data. Only their text lines
  are claimed, so relocation never touches the data after them.
- Messages are only referenced through the tables (checked over the whole ROM).
- Choice menus are laid out with full-width spaces. The cursor positions are fixed, so
  English uses the `{>nn}` pen code to place options.

## Name/term lists

Null-terminated strings, entry n found by skipping n terminators from a base. Two regions:
`$1A2D44`–`$1A33D2` (misc, characters, items, weapons, armour, skills, spells) and
`$1A34E2`–`$1A39C2` (enemies, places). `$1A33D2` is binary data. 28 `lea $xxxxxx.l,An`
operands point at list bases (`soe_rom.STRING_REFS`). Copied into `$FF4000` by `$08B388`
and shown by the popup printer `$087CA6`, which sizes its box from the byte count and takes
the other path (`$087DAA`) past 28 half-width columns.

## UI text (handled by tools/ui.py)

- Menus draw word "sheets" into the canvas once (`$FF8723` bit 7 = already drawn) with a
  12/4 px advance and 16 px lines, then build each screen with a layout bytecode
  (`$0AD7B4`, decoder in `tools/layout.py`). Opcode `$0E` copies a w×h block of canvas tiles
  to the screen, so every word owns a fixed canvas rectangle (24 px for 2-character words).
  English words are placed in the same rectangles with `{>nn}`, and a few rectangles were
  widened (shop Buy/Sell, load/save titles, Yes/No).
- Main sheet `$0B1618` at canvas (112,4); equipment slots `$0B1688` at (208,68); shop sheet
  `$0B169A` (112,2) and `$0B16C4` (112,52); load/save sheets `$0B1DE0`/`$0B1EDE` at (3,3) with
  16/8 px advance; battle commands `$0A16FC` at (4,66) with 13/6 px advance.
- Party names: 8-byte records at `$0AE27A`, copied by `$0AE268` (menu, two per line, 48 px
  slots) and `$0A212A` (battle). Replaced by null-terminated names (pointer table).
- Popups (`$087CA6`, battle messages `$0A177A`) sized the box by byte count and dropped
  anything over 28 columns; now measured in pixels.
- Item descriptions: 256 word offsets at `$0B08F0` from base `$0B0AF0` (lea at `$0B08AC`), one
  144 px line at canvas (112,114). Inventory names: 2 columns of 56 px (`$09B7B4`); the skills
  list (`$09B46C`) used to cut the last character.
- Number formatters `$0B0766` and `$0A2142` pad with a blank 6 px glyph `$7F` (figure space).
- `tools/find_ui_strings.py` lists all code-referenced strings; the ending ones
  (`$1B5EFA`, `$1B5F03`, `$1B8732`…) are handled by `tools/ending.py`.

## Intro and title graphics (handled by tools/title_gfx.py)

- Intro captions: `$1B6900` plots 1bpp bitmaps into the text canvas (`$8B91A`). Six blocks of
  256×24 px (32 bytes/row) at `$1D69C8`; caption n uses rows `$1B696E[n]` (24/48/48/24) from
  block `$1B6972[n]` (0/1/3/5).
- Title logo: loader `$1B6976`, table `$1E66D8` (palette `$1E66E4`, tiles `$1E6724` → VRAM
  `$18000`, maps `$1EDC84`+4). Layer 0, 4bpp, 32×32 map at VRAM `$1F800`; the logo is 32×8
  tiles at map row 8. Map 0 (palette 1) is the gold screen; map 1 (palette 0) the fire screen,
  where index 0 inside the letters lets the animated flame layer (layer 1) show through and
  index 1 is opaque black. Tile 0 is solid index 1. The mask on the fire screen
  (`$1B614E`, table `$1D7BC8`) covers map x ~75–180 with its horns.
- Boot logo (Funtech) and "PUSH START / ©1995 FUNTECH" are left as they are.

## Free space

`$97D66`–`$99167` (4.9 KB of zeros, never read in a 2-minute trace). The VWF code and
width table use the first ~190 bytes. The rest is text space. Once the whole game is in
English, the 12×12 Chinese font (`$197336`–`$1A12EE`, 39.5 KB) can be freed, if nothing
else still uses it.

## Emulator note

The game runs in the 256 px mode (`$F00008` bit 8 clear). The repo emulator used to always
draw 320 px (the extra 64 columns showed the layers wrapping round); it now crops to the
active width and stretches it to 4:3.
