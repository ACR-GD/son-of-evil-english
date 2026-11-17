"""Decoder for the menu layout bytecode run by $0AD7B4 (a3 = script, builds the tilemap at
$FF7000 that is uploaded to VRAM $6000). Usage: python3 tools/layout.py [ADDR ...]

Opcodes (x, y, w, h in 8 px tiles; tile map is 32 x 32):
  00              end
  01 x y t        one tile (t + $280)
  02 x y t.. 00   row of tiles; 03 / 04 = same, continuing 1 / 2 rows below the last
  05 x y w h      window frame
  06-0A x y [align] ptr16   number / value from RAM $FF8000+ptr (digits)
  0B [align] ptr32          call native code
  0C x y w h      frame outline only
  0D x y w h tile16         fill
  0E x y w h sx sy          copy a w x h block of canvas tiles starting at canvas tile (sx, sy)
                            (the text canvas at $FF0000 is 32 x 16 tiles = 256 x 128 px)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soe_rom as R

SCRIPTS = [0x0AD4B6, 0x0AD5DE, 0x0AD5F2, 0x0AD77A, 0x0AE098, 0x0AE3AE, 0x0AE464, 0x0AE46C,
           0x0AEA26, 0x0AEA32, 0x0AEA3A, 0x0AEA4A, 0x0AEBCE, 0x0AEF32, 0x0AEFB8, 0x0AF148,
           0x0AF158, 0x0AF774, 0x0AF784, 0x0AF790, 0x0B199E, 0x0B1C22, 0x0B1CAA, 0x0B1E5E]


def decode(rom, a):
    """Yield (offset, opcode, args) until the end opcode."""
    while True:
        o = a
        op = rom[a]
        a += 1
        if op == 0:
            yield o, op, ()
            return
        if op == 1:
            yield o, op, tuple(rom[a:a + 3]); a += 3
        elif op in (2, 3, 4):
            n = 2 if op == 2 else 0
            args = list(rom[a:a + n]); a += n
            while rom[a]:
                args.append(rom[a]); a += 1
            a += 1
            yield o, op, tuple(args)
        elif op in (5, 12):
            yield o, op, tuple(rom[a:a + 4]); a += 4
        elif op in (6, 7, 8, 9, 10):
            x, y = rom[a], rom[a + 1]
            a = (a + 2 + 1) & ~1
            yield o, op, (x, y, R.u16(rom, a)); a += 2
        elif op == 11:
            a = (a + 1) & ~1
            yield o, op, (R.u32(rom, a),); a += 4
        elif op == 13:
            yield o, op, tuple(rom[a:a + 4]) + (R.u16(rom, a + 4),); a += 6
        elif op == 14:
            yield o, op, tuple(rom[a:a + 6]); a += 6
        else:
            raise ValueError(f"unknown opcode {op:02x} at {o:06x}")


NAMES = {1: "tile", 2: "tiles", 3: "tiles+1", 4: "tiles+2", 5: "frame", 6: "num1", 7: "num2",
         8: "num3", 9: "num5", 10: "char", 11: "call", 12: "outline", 13: "fill", 14: "text"}

if __name__ == "__main__":
    rom = R.load_rom()
    for a in [int(x, 16) for x in sys.argv[1:]] or SCRIPTS:
        print(f"== {a:06X}")
        for o, op, args in decode(rom, a):
            if op == 14:
                x, y, w, h, sx, sy = args
                print(f"  {o:06X} text   screen ({x},{y}) {w}x{h} <- canvas px ({sx*8},{sy*8})-({(sx+w)*8},{(sy+h)*8})")
            elif op:
                print(f"  {o:06X} {NAMES[op]:6} " + " ".join(f"{v:X}" for v in args))
