One-off scripts used to build `notes/glyph_table.json` (kept for provenance; the table itself
is the source of truth now). They expect the 68000-order ROM as `soe.bin` in the working
directory and the Vision OCR helper built by the Super Dragon Force tools (`build/ocr_vision`).

1. `ocr_table.py`   OCR each glyph in a 「X」 carrier at two scales -> votes_carrier.json
2. `ocr_corpus.py`  OCR every run of 3+ glyphs from the dialogue, aligned 1:1 -> votes_corpus.json
3. (combine votes)  -> combined.json
4. `zhuyin_check.py` the font is sorted by Zhuyin; guesses that break the order are flagged
   (needs `pypinyin`)
5. `review_sheets.py` renders the flagged glyphs; they were read by eye and corrected in
   `notes/glyph_review_fixes.json`.
