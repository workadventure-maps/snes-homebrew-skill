# Graphics, input, sound and the title screen

## Contents
- A layout that works: Mode 1
- Text on BG3
- 16x16 cells on a BG layer
- Sprites: 32x32 with the dynamic sprite engine
- Input and the Multitap
- Sound effects
- Title screen from generated art

## A layout that works: Mode 1

Mode 1 gives two 4bpp layers (BG1, BG2) and one 2bpp layer (BG3). The reference game uses:

| What | Where |
|---|---|
| Sprite tiles | VRAM $0000-$1FFF (words) |
| BG2 tiles (arena, or the title picture: up to 1024 tiles) | VRAM $2000 |
| BG3 font | VRAM $6000 |
| BG3 text map (32x32) | VRAM $7000 |
| BG2 map (32x32) | VRAM $7400 |
| BG3 text palettes (4 colors each) | CGRAM 0-31 |
| BG2 palettes | CGRAM palettes 2-7 (0 and 1 overlap BG3's colors) |
| Sprite palettes | CGRAM 128-255 (8 x 16 colors) |

CGRAM color 0 is the backdrop.

### Startup order

The screen is still off when `main()` starts, so VRAM and CGRAM can be loaded directly until `setScreenOn()`:

```c
int main(void)
{
    init_sound();                                  // spcBoot() and the sound table, first
    bgInitTileSet(2, &font_til, &font_pal, 0, (&font_tilend - &font_til), 4 * 2, BG_4COLORS, 0x6000);
    bgSetMapPtr(2, 0x7000, SC_32x32);              // BG3 text
    bgSetGfxPtr(1, 0x2000);                        // BG2 playfield
    bgSetMapPtr(1, 0x7400, SC_32x32);
    // bgInitTileSet just wrote the font's color 0 over CGRAM 0, the backdrop: set text palettes and backdrop now
    dmaCopyCGram((u8 *)textpal, 0, sizeof(textpal));
    oamInitDynamicSprite(0x0000, 0x1000, 0, 0, OBJ_SIZE16_L32);
    dmaCopyCGram((u8 *)&p1_pal, 128, 32);
    oambuffer[0].oamattribute = OBJ_PRIO(2) | OBJ_PAL(0) | OBJ_SIZEL;
    oambuffer[0].oamgraphics = &p1_til;
    oambuffer[0].oamrefresh = 1;                   // once is enough if the frame never changes
    // ... set every RAM variable here (initialized globals are ROM), fill bgmap/txtmap ...
    detectMPlay5();
    dmaCopyVram((u8 *)bgmap, 0x7400, 2048);
    dmaCopyVram((u8 *)txtmap, 0x7000, 2048);
    setMode(BG_MODE1, BG3_MODE1_PRIORITY_HIGH);    // BG3 tiles with the priority bit go above everything
    bgSetDisable(0);                               // BG1 unused
    setScreenOn();
    while (1) { /* the main loop from SKILL.md */ }
    return 0;
}
```

After that, load palettes with `dmaCopyCGram(src, first_color, bytes)` and tiles/maps with
`dmaCopyVram(src, word_addr, bytes)` only during VBlank (frame-budget.md) or between `setScreenOff()` and
`setScreenOn()`.

## Text on BG3

A text map entry is `(ch - 32) | 0x2000 | (palette << 10)` for a font converted as 96 glyphs from ASCII 32
(0x2000 = priority, so text draws over sprites). Write into the RAM copy and mark the row dirty; the VBlank code
sends it. Give the font a 1 px drop shadow in a second color (done in the Python generator): it stays readable on
any background. Use one 4-color text palette per player color so HUD labels match the characters.

Keep important text off the outermost rows: row 0 can be lost to TV overscan, and the arcade cabinet page draws
badges over the top corners.

## 16x16 cells on a BG layer

Draw the playfield as 16x16 metatiles: 4 map entries per cell (t, t+1, t+16, t+17 when the tileset image is 16
tiles wide). Precompute each cell's map index and each metatile's first entry (with its palette bits) in tables:
multiplication in C is slow.

A cell type -> metatile function plus a redraw queue (frame-budget.md) keeps drawing separate from the rules. Small
touches that read well: a shaded floor tile under walls, a two-frame blink for bombs.

## Sprites: 32x32 with the dynamic sprite engine

PVSnesLib's dynamic engine uploads only the frames in use:

```c
oamInitDynamicSprite(0x0000, 0x1000, 0, 0, OBJ_SIZE16_L32);
dmaCopyCGram((u8 *)&p1_pal, 128, 32);                        // sprite palette 0
oambuffer[0].oamattribute = OBJ_PRIO(2) | OBJ_PAL(0) | OBJ_SIZEL;
oambuffer[0].oamgraphics = &p1_til;                    // sheet of 32x32 frames stacked vertically

// every frame, for every sprite, always in the same order (each keeps its VRAM slot):
oambuffer[i].oamx = x; oambuffer[i].oamy = visible ? y : 224;   // hide below the screen
if (frame != last_frame[i] && uploads < 2) { oambuffer[i].oamframeid = frame; oambuffer[i].oamrefresh = 1; ... }
oamDynamic32Draw(i);
// after the last one:
oamInitDynamicSpriteEndFrame();
// in VBlank: oamVramQueueUpdate();
```

Each frame change uploads 512 bytes, so cap uploads per frame (2 in the reference game) and let the others catch
up next frame.

For characters on a 16 px grid, a 32x32 sprite at full size is too big; the reference game scales 32x32
character art to 21x21 (2/3) inside the 32x32 frame, feet near the bottom, head overlapping the row above. The
title screen uses extra full-size frames in the same sheet.

## Input and the Multitap

```c
detectMPlay5();
npads = snes_mplay5 ? 4 : 2;      // P1 on port 1, P2-P4 on a Multitap in port 2
keys = padsCurrent(p);            // held: KEY_LEFT, KEY_A, KEY_START...
down = padsDown(p);               // pressed this frame
```

Accept every face button (A, B, X, Y) for the main action: arcade and browser players have different mappings.
Track whether each player touched their pad during a round, to drop idle players from the next one.

## Sound effects

Streamed BRR samples through PVSnesLib's sound table (no music module needed):

```c
brrsamples sfx_table[N];
spcBoot();
spcAllocateSoundRegion(12);                         // 12 x 256 bytes of SPC RAM: fits the longest sample
spcSetSoundDataEntry(15, 8, 2, &sfx_a_end - &sfx_a, &sfx_a, &sfx_table[0]);  // volume, pan, pitch (2 = 8 kHz)
spcSetSoundTableEntry(&sfx_table[0]);
// play: spcPlaySound(0); every frame: spcProcess();
```

One effect plays at a time. Keep a single "next sound" slot with priorities (a death beats a bomb drop) and
start it on a quiet frame. Placeholder effects can be synthesized in Python (sweeps, noise bursts, square-wave
arpeggios) as 8 kHz WAVs.

## Title screen from generated art

1. Generate two images with an image model (the Codex CLI has one: `codex exec -s workspace-write
   --skip-git-repo-check -C <dir> - < prompt.txt`, with a prompt asking it to save the PNG into that directory;
   copies also land in `~/.codex/generated_images`).
   - Background: 8:7, authentic 16-bit pixel art (chunky pixels, dark outlines, flat colors, no dithering or
     anti-aliasing), no text at all, with plain areas where the logo, the characters and "PRESS START" will go.
   - Logo: the title lettering alone on a flat magenta (#FF00FF) background, which `mktitle.py` keys out.
2. `python3 tools/mktitle.py assets gfx` composes logo over background at 256x224, cuts it into 8x8 tiles,
   groups tiles into 6 palettes of 15 colors (k-means over tiles), dedupes tiles with flips (must stay at or under
   1024), and writes `title.pic`, `title.map`, `title.pal` and `title_preview.png`. Look at the preview first.
3. Show it with the screen off: tiles to the BG tile base, 2048-byte map, `dmaCopyCGram(&title_pal, 32, 6 * 32)`
   (palettes 2-7). Text stays on BG3 with palettes 0-1, which is why the title can only use 6 palettes.

Ask the user how generated art should be credited.
