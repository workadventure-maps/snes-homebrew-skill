---
name: snes-homebrew
description: Build original Super Nintendo (SNES / Super Famicom) homebrew games as real ROMs, in C with PVSnesLib plus a little 65816 assembly: toolchain setup, project layout, VBlank and frame-time budgets, headless tests on the snes9x libretro core, sprites, text, title screens, sound, 4 players with a Multitap, and publishing (GitHub Actions, a playable GitHub Pages site, the WorkAdventure arcade cabinet). Use this skill whenever the user wants to make, extend, debug, test or ship a SNES game or .sfc ROM, or asks what it would take to build one, even if they don't mention PVSnesLib.
---

# SNES homebrew games

This skill captures what it took to ship **Bombadventure**, a 1-4 player bomb-maze game, as a real SNES ROM:
https://github.com/workadventure-maps/bombadventure (MIT). That repo is the worked example: when a section
below says "see the reference game", read the named file there instead of reinventing it.

Most of the effort in a SNES game goes into the platform, not the gameplay: a 3.58 MHz CPU, a C compiler that
generates slow code, video memory that can only be written during 37 scanlines per frame, and no debugger in the
loop. The workflow below front-loads the measurements and tests that catch those problems while they are cheap.

## Workflow

### 1. Pin down the game with the user first

Ask about whatever the request leaves open before writing code (a fully specified small prototype can skip
this); these answers change the architecture. Number of players and controllers (more than 2
needs a Multitap in port 2), how players join, round and win rules, art sources and their licenses, sound, code
license, scope (prototype or polished), and where it will run (browser, arcade cabinet, real hardware). Record the
answers in a DESIGN.md decision table so later sessions don't re-ask.

Check art rights before the first public push. Anything committed to a public repo stays in its history: removing
it later means rewriting history and force-pushing. Third-party asset packs often allow use in games but forbid
redistributing the raw files.

### 2. Toolchain and project

Copy `scripts/setup.sh`, `scripts/snes.py` and `scripts/mktitle.py` from this skill into the project's `tools/`,
then run `tools/setup.sh`. It downloads PVSnesLib 4.6.0 and the snes9x libretro core into `.tools/` (gitignored).
You also need Python 3 with Pillow and NumPy, make, curl and unzip.

Do not launch GUI emulators to test (Mesen 2 crashed on Linux and opened a setup window on the user's desktop).
Everything is tested headless (step 5) and checked visually through screenshots.

Read `references/toolchain.md` for the Makefile, the `data.asm` asset file, asset converters, and the C compiler's
rules and traps.

### 3. Main loop and budgets from day one

Every frame has a fixed shape. Build it before any gameplay, with the measurements, because both budgets fail
silently: a late VBlank transfer drops tiles on screen, and an overlong frame makes the game slow down.

```c
while (1)
{
    update_game();      // logic; changes RAM copies of the BG maps only
    draw_sprites();     // fills the OAM buffer, queues sprite frame uploads
    update_sound();     // spcProcess(), and at most one new sound
    prepare_vblank();   // works out this frame's DMA source/dest/length
    work_end = scanline();
    WaitForVBlank();
    vblank_work();      // only starts DMAs: no C logic here
    measure_vblank();   // records vbl_end, counts vbl_late
}
```

Read `references/frame-budget.md` for the VBlank rules, the `scanline()` helper, the per-frame caps, and the
patterns that keep busy frames in budget.

### 4. Write the game in C, measure, and only then consider assembly

Write everything in C first. Measured on Bombadventure (4 players at full power, three random battles): an all-C
version averaged 5% slower than the shipped one, with no dropped frames, but its busiest frames used 201-229 of
the ~240 available scanlines against 152-164 with the per-cell routines in assembly.

So: keep the frame-cost test (step 5) failing above a budget with headroom (200). When it fails, first spread the
work over several frames (queues, one heavy event per frame). Move a routine to assembly only when it is a
per-cell or per-object loop that still blows the budget, and compare the numbers before and after. Tuning the C
helps little (about 5 scanlines in that experiment): the compiler spends about 10 instructions on every array
access, and nothing at the C level changes that.

### 5. Tests that run the real ROM

Use `tools/snes.py` (a headless libretro frontend: scripted input for 4 players, WRAM/VRAM reads, screenshots,
audio level) with the `.sym` file to read game variables by name. Write tests for the rules, plus three that
protect the budgets: VRAM equals the RAM copies of the maps once transfers settle, no lag frames during play,
and a random 4-player battle that fails if the busiest frame passes the budget. The whole suite runs in seconds.
See `references/testing.md`.

Look at the game too: take screenshots with `Snes.screenshot()` at key moments (title, play, the feature you just
built), view them, and send them to the user. Tests miss ugly.

### 6. Graphics, text, sound, title screen

See `references/graphics-sound.md`: the BG mode and VRAM/CGRAM layout that worked, text on BG3, 32x32 sprites
with the dynamic sprite engine, sound effects as BRR samples, and the title screen pipeline (generated art ->
`mktitle.py` -> 6 palettes of 15 colors). It also covers tiles drawn by Codex and how to let the
user compare versions inside a real game screenshot, and what to do when a graphic needs its own palette.

### 7. Publish

See `references/publishing.md`: a GitHub Actions workflow that builds and tests every push, a GitHub Pages site
that plays the ROM in the browser (EmulatorJS, with the Multitap for 4 players), and deploying to the
WorkAdventure arcade cabinet (cloud-game).

## Traps that cost time

- A bug that only shows as missing or stale tiles is almost always a VBlank overrun. Check `vbl_late` and the
  VRAM-vs-RAM test before debugging game logic.
- Wrong colors over a whole layer with no error: gfx4snes matches PNG pixels by RGB, so duplicate colors in a
  palette (black padding, a black index 0) send pixels to the wrong index. Keep palette colors unique, index 0 a
  key color (toolchain.md).
- `bgInitTileSet` overwrites CGRAM entries starting at the palette you give it, including color 0 (the backdrop)
  for BG3 palette 0. Set the backdrop after loading tilesets.
- The frame-cost formula wraps at 262 lines; a frame that is far too long can read as cheap. Always assert no lag
  frames alongside it.
- Starting a sound costs about 40 scanlines; streaming costs about 13 per frame. Never start one on a frame that
  already does heavy work.
- Initialized non-const globals don't work as variables: the compiler puts them in ROM. Initialize RAM in code.
- No 32-bit shifts in C (link error on `tcc__ashldi3`).
- Switching between two full screens (title and arena) can't go through the per-frame DMA budget: turn the screen
  off, DMA everything, turn it back on.
- The Claude desktop app's browser has no WebGL, so EmulatorJS can't run there; test web pages with Playwright's
  headless Chromium and software WebGL (`references/testing.md`).
- The snes9x core download is a nightly build, not pinned. If tests break with no code change, suspect the core.

## Improving this skill

This skill grows from real games. While you work, note every place where it was wrong, missing something or sent
you the wrong way, and anything that cost a lot of time, with measurements when you have them. At the end of the
task, tell the user what you would change in the skill and why. If they agree:

- Edit the skill in its git repository, https://github.com/workadventure-maps/snes-homebrew-skill. A maintainer
  may have a checkout linked as `~/.claude/skills/snes-homebrew`: follow the symlink to find it.
- Keep game-specific choices (characters, rules, art style) out; they belong to the game's own repo.
- The repo is public: no internal server addresses, private repositories or credentials.
- Check with `claude plugin validate <repo>`, and bump `version` in `.claude-plugin/plugin.json` (installed
  plugins only update to a new version).
- Push to `main` if the user has write access and wants that; otherwise open a pull request.
