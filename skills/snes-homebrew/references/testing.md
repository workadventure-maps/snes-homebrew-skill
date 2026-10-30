# Testing on the real ROM

## Contents
- tools/snes.py
- A test file
- The budget tests
- Visual checks
- Testing a web page that embeds the ROM

## tools/snes.py

A small headless libretro frontend over the snes9x core (`.tools/snes9x/snes9x_libretro.so`), the same core
cloud-game and EmulatorJS use. No window, no audio device; a frame runs in well under a millisecond.

```python
from snes import Snes, symbols
s = Snes('mygame.sfc')            # P1 on port 1, a Multitap on port 2 (multitap=False for a plain pad)
s.run(60)                         # run frames
s.press(0, 'start', frames=2)     # player 0..3 holds buttons, then releases
s.held[1] = {'left', 'b'}         # or hold buttons across run() calls
ram = s.wram()                    # 128 KB work RAM, bytes
vram = s.vram()                   # 64 KB video RAM
s.poke_wram(addr, [1, 2])         # set up a situation directly
s.loudness                        # peak audio sample of the last frame (0 = silence)
s.screenshot('shot.png')
SYM = symbols('mygame.sym')       # {'variable': wram offset} for WRAM labels
```

Buttons: `b y select start up down left right a x l r`. Player numbers map to libretro ports: P1 = port 0,
Multitap pads = ports 1-4. The game needs `detectMPlay5()` to see the Multitap. The default (`multitap=True`)
also works for 2-player games: the Multitap's first pad is player 2. The core prints `Map_LoROMMap` on stdout
when it loads a ROM; filter it out of test logs if it bothers you.

## A test file

Give the frontend name-based access to game variables:

```python
class Game(Snes):
    def peek(self, name, n=1):
        ram = self.wram()
        v = list(ram[SYM[name]:SYM[name] + n])
        return v if n > 1 else v[0]

    def peek16(self, name, index=0):          # index: element of a u16 array
        ram, a = self.wram(), SYM[name] + 2 * index
        return ram[a] | ram[a + 1] << 8

    def poke(self, name, values, offset=0):
        self.poke_wram(SYM[name] + offset, values)
```

Then write each rule as a short scenario: start a round, poke the arena into a known layout (clear a path, place
a power-up, set the timer to 1 second), press buttons for a counted number of frames (a player moving 1 px per
frame crosses a 16 px cell in 16 frames), and assert on variables. Poking is what keeps tests short and
deterministic; random levels otherwise make every test flaky. If you poke cells, also queue them for redraw or
the screen won't match.

A test must fail without the fix it covers. When fixing a bug, run the new test on the old code once
(`git stash` the fix) to see it fail.

## The budget tests

1. **VRAM matches RAM.** Once nothing is pending (dirty ranges clear, redraw queue empty, no DMA prepared),
   compare the RAM copies of the BG maps with VRAM. A mismatch means a transfer was lost. Skip states where a
   layer intentionally shows something else (a title picture).
2. **No lag frames during play.** Read `lag_frame_counter` before and after a scenario. Level rebuilds behind a
   static screen may lag; exclude those frames explicitly.
3. **Frame cost under a budget.** Drive 4 bots randomly at maximum power for ~1,500 frames (fixed RNG seed),
   record `(work_end - vbl_end) % 262` each frame outside transitions, and fail above 200 scanlines. Also assert
   `vbl_late == 0`. Print the busiest frame so changes in cost are visible in CI logs.

Tests 2 and 3 only work together: the cost formula wraps at 262, so a frame of 419 lines reads as 157 and passes
the budget. The lag counter is what catches it.

Force rare situations into the random run (max range, max bombs, an end-of-round mode starting after 3 seconds)
so they get measured too.

## Visual checks

Tests don't see ugliness. After each visible change, take screenshots at the moments that matter, scale them 2x
with nearest-neighbour, put several side by side in one image, look at it, and send it to the user.

## Testing a web page that embeds the ROM

EmulatorJS needs WebGL. The Claude desktop app's built-in browser has none, so drive headless Chromium through
Playwright with software WebGL:

```js
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
await page.click('.ejs_start_button');
await page.waitForFunction(() => window.EJS_emulator && window.EJS_emulator.started);
// keyboard: page.keyboard.down('Enter'); gamepad players: EJS_emulator.gameManager.simulateInput(player, button, 1)
```

Serve the page over HTTP (the ROM can't load from file://). Check the screenshots for players joining and
moving.
