# VBlank and frame budgets

## Contents
- The two budgets
- Measuring: scanline counters
- VBlank: prepare during the frame, only DMA in VBlank
- Keeping busy frames in budget
- C or assembly: the measurements

## The two budgets

An NTSC frame has 262 scanlines. The picture uses lines 0-224; VBlank is lines 225-261 (37 lines).

- **VBlank budget**: VRAM, CGRAM and OAM can only be written during VBlank (or with the screen off). A DMA that
  runs past line 261 writes into the visible picture and those writes are lost: tiles go missing or stay stale.
  Nothing crashes, which is why it must be tested.
- **Frame budget**: game logic for the next frame must finish before the next VBlank, about 240 lines after the
  previous VBlank work ends. Otherwise the frame is a lag frame (PVSnesLib counts them in `lag_frame_counter`)
  and the game slows down.

## Measuring: scanline counters

```c
u16 vbl_end, vbl_late, work_end;

u16 scanline(void)
{
    u8 lo;
    lo = *(vuint8 *)0x2137; // latch the PPU counters
    lo = *(vuint8 *)0x213F; // reset the read flip-flop
    lo = *(vuint8 *)0x213D; // vertical counter, low byte then high bit
    return lo | ((*(vuint8 *)0x213D & 1) << 8);
}

void measure_vblank(void)       // right after the VBlank DMAs
{
    vbl_end = scanline();
    if (vbl_end < 225 && vbl_late < 65535)
        vbl_late++;             // VBlank work ran into the picture
}
```

`work_end = scanline()` just before `WaitForVBlank()`. The frame's CPU cost is
`(work_end - vbl_end) mod 262` scanlines. The tests read these three variables (testing.md).

That formula wraps: a frame that takes 419 lines reads as 157. It is only meaningful on frames without lag, so a
budget test must always also assert that `lag_frame_counter` didn't move.

## VBlank: prepare during the frame, only DMA in VBlank

Compiled C is too slow to decide anything inside VBlank. Split the work:

- Keep RAM copies of the BG maps (`u16 bgmap[1024]`, `u16 txtmap[1024]`). Game logic writes there and widens a
  dirty row range (`map_lo..map_hi`, 255 = clean).
- `prepare_vblank()`, during the frame, turns the dirty range into DMA source, VRAM address and length, capped
  per frame. In the reference game: at most 6 arena rows of 16 px cells (768 bytes), 8 text rows, and text waits
  a frame when the arena update is big. A full arena redraw takes 3 frames.
- `vblank_work()` only calls `oamVramQueueUpdate()` and `dmaCopyVram()` with the prepared values.
- Sprite frame uploads (512 bytes per 32x32 frame) go through the same budget: at most 2 per frame.

Busiest VBlank seen in the reference game with these caps: 23 of 37 lines. Full-screen changes (title to arena)
don't fit: `setScreenOff()`, DMA everything, `setScreenOn()`.

## Keeping busy frames in budget

These patterns are language-independent and made the difference; the first version did a whole explosion and
started its sound in one frame (54 + 44 scanlines).

- **Change state at once, draw later.** Game logic updates the cell array immediately (so rules stay exact) and
  pushes changed cells on a redraw queue; a fixed number (8) are drawn per frame. A big blast spreads its drawing
  over a few frames, which nobody can see.
- **One heavy event per frame.** At most one bomb explodes per frame; a chain reaction ripples one bomb per frame.
- **Defer sound starts** to a frame without a heavy event: `spcPlaySound()` costs about 40 scanlines.
- **Text is slow to draw in C** (a 32-tile row is a 32-iteration loop). Draw messages on frames between heavy
  events (Bombadventure's "SUDDEN DEATH!" message waits for a frame between two falling walls).
- **Rebuilding a level** takes several frames: do it while a static screen (results) is showing.

## C or assembly: the measurements

Bombadventure, 4 players at full power, three random battles of ~1,850 frames each, scanlines per frame
(about 240 available):

| Build | Mean | Busiest frame |
|---|---|---|
| Per-cell routines in assembly (shipped) | 85-88 | 152-164 |
| Same routines in plain C | 90-92 | 201-229 |
| C with helpers inlined, addresses computed once | 89-92 | 197-224 |
| C with only the per-frame timer loop in assembly | 88-91 | 188-207 |

No build dropped a frame during play. Assembly only matters at the peaks, and only for loops over many cells
or objects; everything else (rules, players, menus, HUD) stays in C. Decide with the frame-cost test, not by
default.
