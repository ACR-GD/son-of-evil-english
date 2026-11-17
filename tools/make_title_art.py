"""Draw notes/gfx/intro_captions.png and notes/gfx/title_logo.png from macOS system fonts.

Run once (or after changing the wording); the build only reads the PNGs, which can also be
touched up by hand.   python3 tools/make_title_art.py [LOGO_FONT]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import title_gfx as T

FONTS = "/System/Library/Fonts/Supplemental/"
CAPTION_FONT = FONTS + "Apple Chancery.ttf"
CAPTION_LINES = [
    "As the five woes fill the sky,",       # block 0 (caption 1)
    "the Son of Evil, master of",           # blocks 1-2 (caption 2)
    "boundless darkness, is born.",
    "He will burn the world to ash,",       # blocks 3-4 (caption 3)
    "and none can stop him.",
    "Thus begins the Age of Evil.",         # block 5 (caption 4)
]
# The fire screen's mask covers map x ~75-180 with its horns (gap ~97-160), so "SON" ends
# before the left horn, "of" sits between the horns and "EVIL" starts after the right one.
LOGO_SLOTS = [("SON", 4, 74, "right"), ("of", 100, 156, "center"), ("EVIL", 182, 252, "left")]
LOGO_TOP, LOGO_BOTTOM = 6, 58


def captions():
    f = ImageFont.truetype(CAPTION_FONT, 19)
    im = Image.new("L", (256, 144), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    for i, t in enumerate(CAPTION_LINES):
        w = d.textlength(t, font=f)
        assert w <= 254, t
        d.text(((256 - w) // 2, i * 24 + 18), t, font=f, fill=255, anchor="ls")
    im.point(lambda v: 255 if v >= 128 else 0).save(T.CAPTIONS_PNG)


def logo(font_file):
    k = 4                                    # draw 4x larger, then shrink: smoother edges

    def word(t, size):
        f = ImageFont.truetype(font_file, size * k)
        im = Image.new("L", (60 * k * 6, 64 * k), 0)          # same baseline for every word
        ImageDraw.Draw(im).text((size * k, 48 * k), t, font=f, fill=255, anchor="ls")
        return im, f

    def fits(size):
        for t, x0, x1, _ in LOGO_SLOTS:
            s_ = size if t != "of" else int(size * 0.7)
            im, _f = word(t, s_)
            l, tp, r, bt = im.getbbox()
            if (r - l) / k > x1 - x0 - 2:
                return False
        return True

    size = next(s_ for s_ in range(60, 10, -1) if fits(s_))
    # common baseline: render each word on the same baseline, then place horizontally
    out = Image.new("L", (256 * k, 64 * k), 0)
    for t, x0, x1, align in LOGO_SLOTS:
        s_ = size if t != "of" else int(size * 0.7)
        im, f = word(t, s_)
        l, tp, r, bt = im.getbbox()
        w = r - l
        x = {"right": x1 * k - w, "left": x0 * k, "center": (x0 + x1) * k // 2 - w // 2}[align]
        out.paste(im.crop((l, 0, r, im.height)), (x, 0), im.crop((l, 0, r, im.height)))
    l, tp, r, bt = out.getbbox()
    h = bt - tp
    band = out.crop((0, tp, out.width, bt))
    canvas = Image.new("L", (256 * k, 64 * k), 0)
    canvas.paste(band, (0, ((LOGO_TOP + LOGO_BOTTOM) * k - h) // 2))
    im = canvas.resize((256, 64), Image.LANCZOS).point(lambda v: 255 if v >= 110 else 0)
    im = im.filter(ImageFilter.MaxFilter(3))  # thicken strokes so the flames show
    im.point(lambda v: 255 if v >= 128 else 0).save(T.LOGO_PNG)
    print(f"logo: {font_file}, size {size}, height {h // k} px")


if __name__ == "__main__":
    os.makedirs(T.GFX, exist_ok=True)
    captions()
    logo(FONTS + (sys.argv[1] if len(sys.argv) > 1 else "Luminari.ttf"))
