# Toolchain, project layout and the C compiler

## Contents
- Project layout
- Makefile
- data.asm: putting assets in the ROM
- Asset converters
- Writing C for 816-tcc
- Calling assembly from C

## Project layout

```
Makefile          PVSnesLib's snes_rules + asset rules
data.asm          includes converted graphics and sounds in ROM sections
src/main.c        the game (snes_rules compiles every .c and .asm in src/)
src/*.asm         hand-written hot paths, only if measurements demand them
assets/           source art (PNG, the font BMP)
tools/            setup.sh, snes.py, mktitle.py, your mkgfx.py / mksfx.py generators
tests/smoke.py    gameplay and budget tests on the real ROM
gfx/ sfx/         generated, gitignored
```

`.gitignore`: `.tools/ gfx/ sfx/ *.sfc *.sym *.symfull *.obj *.log *.ps linkfile hdr.asm src/main.asm __pycache__/`
(snes_rules generates `hdr.asm`, the ROM header, from the Makefile variables).

## Makefile

From the reference game, trimmed:

```make
ifeq ($(strip $(PVSNESLIB_HOME)),)
export PVSNESLIB_HOME := $(CURDIR)/.tools/pvsneslib
endif

export ROMNAME := mygame
export ROMTITLE := MYGAME        # header title, uppercase, at most 21 characters
export SRC := src
export FASTROM := 1              # LoROM FastROM

include ${PVSNESLIB_HOME}/devkitsnes/snes_rules

.PHONY: all gfx test
all: gfx $(ROMNAME).sfc

# generated PNGs -> SNES tiles + palettes
gfx/.stamp: tools/mkgfx.py $(wildcard assets/*.png)
	python3 tools/mkgfx.py assets gfx
	touch $@
gfx/tiles.pic: gfx/.stamp
	$(GFXCONV) -s 8 -o 16 -u 16 -p -i gfx/tiles.png       # 8x8 tiles, 16 colors
gfx/font.pic: gfx/.stamp
	$(GFXCONV) -s 8 -o 4 -u 4 -p -i gfx/font.png          # 2bpp font for BG3
gfx/p%.pic: gfx/.stamp
	$(GFXCONV) -s 32 -o 16 -u 16 -p -i gfx/p$*.png        # 32x32 sprite frames
gfx/title.pic: tools/mktitle.py assets/title_bg.png assets/title_logo.png
	python3 tools/mktitle.py assets gfx

# generated WAVs -> BRR samples
sfx/.stamp: tools/mksfx.py
	python3 tools/mksfx.py sfx
	touch $@
sfx/%.wav: sfx/.stamp ;
sfx/%.brr: sfx/%.wav
	$(BRCONV) -e $< $@

ASSETS := gfx/tiles.pic gfx/font.pic gfx/p1.pic gfx/title.pic sfx/boom.brr   # everything data.asm includes
gfx: $(ASSETS)
data.obj: $(ASSETS)          # reassemble data.asm when an asset changes

test: all
	python3 tests/smoke.py
```

The build also writes `mygame.sym`: label addresses that the tests use to read variables by name.

## data.asm: putting assets in the ROM

```asm
.include "hdr.asm"

.section ".rodata1" superfree
tiles_til:
.incbin "gfx/tiles.pic"
tiles_tilend:
tiles_pal:
.incbin "gfx/tiles.pal"
.ends

.section ".rodata2" superfree     ; a section must fit in one 32 KB LoROM bank: split big assets
title_til:
.incbin "gfx/title.pic"
title_tilend:
.ends
```

In C: `extern char tiles_til, tiles_tilend, tiles_pal;` and pass `&tiles_til`, with
`&tiles_tilend - &tiles_til` as the size.

## Asset converters

- **gfx4snes** (`$(GFXCONV)`) converts an indexed PNG into tiles (`.pic`), palette (`.pal`) and optionally a map.
  Index 0 is transparent. Generate the indexed PNGs with a Python script (Pillow) in `tools/mkgfx.py`: it is
  easier to control palettes there than in an image editor.
  - **gfx4snes matches pixels by RGB, not by palette index.** If two palette entries have the same color, pixels
    can land on the wrong index, with no error. A common way to hit it: padding the palette with black while
    index 0 or a used color is also black (a dry run filled the whole screen with a font color this way). Make
    index 0 a key color used nowhere else (magenta), and never pad with a color the image uses.
  - With `-s 32` the `.pic` is padded to whole rows of 4 frames (2048 bytes): a single 32x32 sprite gives 2048
    bytes, a 15-frame vertical sheet 8192. Frame `n` of a vertical sheet is `oamframeid = n`.

  A converter that follows these rules (from the reference game's `tools/mkgfx.py`):

  ```python
  from PIL import Image
  KEY = (255, 0, 255)  # index 0, transparent, used nowhere else

  def to_indexed(rgba, ncolors=15):
      """Hard alpha, quantize opaque pixels to ncolors, index 0 = transparent."""
      alpha = rgba.getchannel('A').point(lambda v: 255 if v > 110 else 0)
      q = rgba.convert('RGB').quantize(ncolors, method=Image.MEDIANCUT)
      out = Image.new('P', rgba.size, 0)
      out.putpalette(list(KEY) + q.getpalette()[:ncolors * 3])   # no padding
      src, a, dst = q.load(), alpha.load(), out.load()
      for y in range(rgba.height):
          for x in range(rgba.width):
              if a[x, y]:
                  dst[x, y] = src[x, y] + 1
      return out

  def font_with_shadow(bmp):
      """1-bit font (one 8 px row of glyphs) -> 2bpp PNG: 1 = glyph, 2 = shadow down-right."""
      s, out = bmp.load(), Image.new('P', bmp.size, 0)
      o = out.load()
      for y in range(bmp.height):
          for x in range(bmp.width):
              if s[x, y]:
                  o[x, y] = 1
      for y in range(bmp.height):
          for x in range(bmp.width):
              if s[x, y] and x % 8 < 7 and y < 7 and not s[x + 1, y + 1]:
                  o[x + 1, y + 1] = 2   # stays inside the glyph's 8x8 cell
      out.putpalette(list(KEY) + [248, 248, 248, 24, 20, 32])
      return out
  ```
- **snesbrr** (`$(BRCONV) -e in.wav out.brr`) converts mono 16-bit WAVs to BRR samples. 8 kHz is enough for
  placeholder effects (play them with pitch 2, see graphics-sound.md).
- The PVSnesLib example font is at `.tools/pvsneslib/snes-examples/input/mouse/pvsneslibfont.bmp` (zlib license:
  ship its license file and credit Alekmaul).

## Writing C for 816-tcc

The compiler (816-tcc, followed by PVSnesLib's 816-opt pass, already in snes_rules) produces correct but slow
code. What matters:

- **Initialized globals are ROM.** `u8 lives = 3;` creates a constant in ROM; writing to it does nothing. Only
  initialize tables (`const u8 spawn_x[4] = {...};`) and set RAM variables in an init function.
- **No 32-bit shifts**: they need `tcc__ashldi3`, which isn't in the library (link error). Use u16 values, or
  split the value into lo/hi parts.
- **Array accesses are expensive**, about 10 instructions each: the compiler builds a 24-bit pointer in direct
  page and reads through it. Prefer u8 indices, read an element once into a local, and precompute lookup tables
  (e.g. the BG-map index of every cell) instead of multiplying.
- **Calls with arguments are expensive** (arguments pushed, reloaded from the stack in the callee). A 4-line
  helper compiled to 66 lines in the reference game. Inlining helpers as macros saved a little, not a lot.
- **Division and modulo call library routines.** Fine once per second (a timer display), not per cell.
- `extern` across .c files works normally. PVSnesLib globals worth knowing: `snes_vblank_count` (frames since
  boot), `lag_frame_counter` (frames where the game missed VBlank), `snes_mplay5` (Multitap detected, after
  `detectMPlay5()`), `oambuffer[]` (sprites).

## Calling assembly from C

Only after measuring (see SKILL.md step 4). The ABI, as used in `src/cells.asm` of the reference game:

- Arguments are on the stack after the 3-byte return address, the first one at `4,s` (`5,s` after a `php`). A u8
  argument takes one byte, so `f(u8 c, u8 mt)` has `c` at `4,s` and `mt` at `5,s`.
- A, X and Y are 16-bit on entry and must be 16-bit on exit (`php` ... `plp` around width changes). The data bank
  is `$7E`, so C globals are reachable as `lda.w name,x`.
- Return values go in `tcc__r0`. `tcc__r0`/`tcc__r1` are scratch: the compiler saves what it needs before a call.
- To call C or another routine: push the arguments last-to-first (`pha` of 8-bit values), `jsl`, then pop them.
- ROM tables need long addressing: `lda.l table,x`. There is no `lda long,y`, so move the index to X.
- Branches reach ±127 bytes; use a `jmp` trampoline when a routine grows past that (wla-dx errors out).
- File header: `.include "hdr.asm"`, `.accu 16`, `.index 16`, `.16bit`, `.BASE $80` (FastROM), then
  `.SECTION ".name" SUPERFREE` ... `.ENDS`. Keep any constants shared with C in sync by hand, with a comment
  saying so.
