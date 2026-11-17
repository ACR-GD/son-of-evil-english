#!/bin/bash
# Builds a tracing copy of the repo's emulator core (run `make app` in emulator/ first so the
# core objects exist). Usage examples:
#   ./harness ROM 7000 press 3100:3110:start shot 6999:out.ppm
#   ./harness ROM 6100 load s.sta wrange FF0000:FF4000 rrange 157500:157800 trace 6035:6065:t.txt
# "trace" logs CPU writes inside wrange (default video regs/VRAM) and reads inside rrange,
# with the PC, one line per access. "dump f:prefix" writes .wram/.vram/.pal/.regs files.
set -e
cd "$(dirname "$0")"
E=../../../emulator
F="-O2 -std=c++17 -I$E/src -I$E/deps/musashi -mmacosx-version-min=12.0"
OUT=${OUT:-/tmp/soe-harness}
mkdir -p "$OUT"
# Same core as the emulator, with memory-access hooks added to the Musashi callbacks.
sed -e 's/^unsigned int m68k_read_memory_8(unsigned int address) {/& if(g_hook_r) g_hook_r(address,1);/' \
    -e 's/^unsigned int m68k_read_memory_16(unsigned int address) {/& if(g_hook_r) g_hook_r(address,2);/' \
    -e 's/^unsigned int m68k_read_memory_32(unsigned int address) {/& if(g_hook_r) g_hook_r(address,4);/' \
    -e 's/^void m68k_write_memory_8(unsigned int address, unsigned int value) {/& if(g_hook_w) g_hook_w(address,value,1);/' \
    -e 's/^void m68k_write_memory_16(unsigned int address, unsigned int value) {/& if(g_hook_w) g_hook_w(address,value,2);/' \
    -e 's/^void m68k_write_memory_32(unsigned int address, unsigned int value) {/& if(g_hook_w) g_hook_w(address,value,4);/' \
    -e 's/^#include "m68k.h"/#include "m68k.h"\nvoid (*g_hook_r)(unsigned,int)=0; void (*g_hook_w)(unsigned,unsigned,int)=0;/' \
    $E/src/emu.cpp > "$OUT/emu_hook.cpp"
clang++ $F -I$E/src -c "$OUT/emu_hook.cpp" -o "$OUT/emu_hook.o"
clang++ $F -c harness.cpp -o "$OUT/harness.o"
clang++ "$OUT/harness.o" "$OUT/emu_hook.o" $E/build_obj/core/src/bus/bus.o $E/build_obj/core/src/video/ppu.o \
    $E/build_obj/core/src/sound/apu.o $E/build_obj/core/src/savestate.o \
    $E/build_obj/deps/musashi/m68kcpu.o $E/build_obj/deps/musashi/m68kops.o \
    $(find $E/build_obj/deps/musashi/softfloat -name '*.o') -o harness
echo "built $(pwd)/harness"
