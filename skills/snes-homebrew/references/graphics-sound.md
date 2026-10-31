# Graphics, input, sound and the title screen

## Contents
- A layout that works: Mode 1
- Text on BG3
- 16x16 cells on a BG layer
- Sprites: 32x32 with the dynamic sprite engine
- Input and the Multitap
- Sound effects
- Title screen from generated art
- Tiles drawn by Codex, and choosing between versions
- When a graphic needs more colors than its palette has

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

### When every frame fits in VRAM: static frames

The dynamic engine costs ~6 scanlines per 32x32 sprite on every frame (about 24 for four players), plus frame
uploads in VBlank. Sprite VRAM holds 32 frames of 32x32 (16 KB with the default name tables): when every frame
the game uses fits, load them once and write OAM directly. PVSnesLib copies `oamMemory` to OAM in VBlank.

```c
oamInit();
oamInitGfxAttr(0x0000, OBJ_SIZE16_L32);
dmaCopyVram(&p1_til, 0x0000, 4096);      // 8 frames: gfx4snes -s 32 output is VRAM-ready, 4 frames per band
dmaCopyVram(&p2_til, 0x0800, 4096);      // ... up to $1FFF
oamMemory[512] = 0xAA;                   // high table: entries 0..3 large, x < 256

// frame f of the sheet loaded at tile `base` (0, 128, 256, 384 above): base + (f >> 2) * 64 + (f & 3) * 4
void put_sprite(u8 id, u8 x, u8 y, u16 tile, u8 pal)
{
    u8 i = id << 2;
    oamMemory[i] = x;
    oamMemory[i + 1] = y;                // 224 hides a 32x32 sprite
    oamMemory[i + 2] = tile;
    oamMemory[i + 3] = OBJ_PRIO(2) | OBJ_PAL(pal) | (tile >> 8);
}
```

For characters on a 16 px grid, a 32x32 sprite at full size is too big; the reference game scales 32x32
character art to 21x21 (2/3) inside the 32x32 frame, feet near the bottom, head overlapping the row above. The
title screen uses extra full-size frames in the same sheet.

## Input and the Multitap

```c
detectMPlay5();
npads = snes_mplay5 ? 4 : 2;      // P1 on port 1, P2-P4 on a Multitap in port 2
keys = padsCurrent(p);            // held: KEY_LEFT, KEY_A, KEY_START...
down = keys & ~keys_before[p];    // pressed since the game last looked
keys_before[p] = keys;
```

Don't use `padsDown()`: PVSnesLib computes it at each VBlank, so when a frame runs late, the next VBlank clears
the press before the game sees it (a test caught a hard drop that never happened).

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

## Tiles drawn by Codex, and choosing between versions

Codex (`codex exec ... -C <dir> - < prompt.txt`) draws good pixel-art tiles when the brief is exact. Run several art
directions in parallel, one directory each, and let the user pick from a comparison. The brief that worked for
Bombadventure's explosion pieces:

- Exact deliverable: one strip PNG (e.g. 112x16 = seven 16x16 pieces), the piece order and what each piece
  connects to, a preview of a test layout at 8x, and the script if it drew in code.
- Give it the current tiles and the floor tile as files, and say what is wrong with the current ones.
- Every tile fully replaces its cell, so the floor must be drawn behind the art.
- Joins: pieces that touch must continue across the edge. If the floor has edge lines (grout), edges can't be
  identical: compare them treating the floor colors as the same, and say so in the brief.
- At most 15 colors including the floor, distinct after rounding each channel down to a multiple of 8.
- No anti-aliasing, blur or dithering noise; 16 px tiles need clear silhouettes.
- Ask it to check all of this with a script before finishing, then check again yourself.

To compare versions honestly, show them in the game, not on a white background:

1. Take a real screenshot of a scene that uses the tiles (from the test frontend), and read from RAM which cell
   shows which piece.
2. Paste each candidate's pieces onto those cells. First paste the *current* pieces: the result must equal the
   screenshot exactly (round both to 5 bits per channel), or the mapping is wrong.
3. Put the versions side by side at 2x, each with its pieces enlarged underneath, and send the image.
4. If the user mixes versions (one's ends, another's middles), joins and colors won't match: have Codex blend them
   (keep each piece's design, adapt edges and palette), possibly in two color schemes to choose from.
5. After integrating the winner, screenshot the same scene from the new ROM and diff it against the chosen
   mockup: it should be 0 pixels.

## When a graphic needs more colors than its palette has

Don't squeeze it into a full palette. Give it its own tiles and its own BG palette: convert it as a separate
image, upload its tiles right after the main tileset (`VRAM base + main tileset bytes / 2`, in words), compute its
first tile number from the tileset size at run time (`(&tiles_tilend - &tiles_til) >> 5` for 4bpp), set its
metatile entries with the new palette bits (`palette << 10`), and reload both tiles and palette wherever the
screen is rebuilt (e.g. leaving the title screen). Add a test that screenshots the graphic and compares its
pixels with the art file: a wrong palette or tile offset fails it, which nothing else would catch.
