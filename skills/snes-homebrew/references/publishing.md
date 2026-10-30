# Publishing

## Contents
- GitHub Actions: build and test every push
- GitHub Pages: play in the browser
- The WorkAdventure arcade cabinet (cloud-game)

## GitHub Actions: build and test every push

Copy `.github/workflows/build.yml` from the reference game. It runs on every push and pull request: Python with
Pillow and NumPy, cache `.tools/` keyed on `tools/setup.sh`, `tools/setup.sh`, `make test`, `make site`, upload the
`.sfc` as a run artifact. On `main` a second job deploys `_site/` to GitHub Pages
(`actions/upload-pages-artifact` + `actions/deploy-pages`, with `pages: write` and `id-token: write`).

The cache also keeps CI on one snes9x nightly until `setup.sh` changes. The whole job takes under a minute
(tests ~5 s).

Enable Pages for workflow builds once (needs admin rights on the repo; ask the user first, it's a repo setting):

```bash
gh api -X POST repos/OWNER/REPO/pages -f build_type=workflow
```

## GitHub Pages: play in the browser

`make site` copies `web/index.html`, the ROM and the title preview into `_site/`. Start from the reference
game's `web/index.html`. The parts that matter:

```html
<div id="game"></div>
<script>
  EJS_player = '#game';
  EJS_core = 'snes';                                   // snes9x
  EJS_gameUrl = 'mygame.sfc';
  EJS_pathtodata = 'https://cdn.emulatorjs.org/4.3.0-pre/data/';   // pinned version
  EJS_backgroundImage = new URL('title.png', location.href).href;  // relative paths resolve against the CDN
  EJS_defaultOptions = { 'controller-port-device-p2': '257' };     // Multitap in port 2
  EJS_defaultControls = { 1: { 3: { value: 'q' }, 4: { value: 'w' } /* ... */ } };
</script>
<script src="https://cdn.emulatorjs.org/4.3.0-pre/data/loader.js"></script>
```

- **Multitap**: EmulatorJS 4.3.0-pre is the first version with `controller-port-device-pN`; 4.2.3 (labelled
  "stable") can't plug a Multitap, so only 2 players work there. 257 is the snes9x Multitap device id
  (`RETRO_DEVICE_SUBCLASS(RETRO_DEVICE_JOYPAD, 0)`). EmulatorJS players 1-4 then map to the game's P1-P4.
- **Controls**: `EJS_defaultControls` merges button by button into the defaults, keyed by player (0-3) then button
  (0 B, 1 Y, 2 Select, 3 Start, 4-7 up/down/left/right, 8 A, 9 X, 10-13 L/R/L2/R2, 14-23 analog sticks).
  Player 1's defaults use arrows, x/z/a/s, q/e/tab/r and more letters; clear the ones you need (`{ value: '' }`)
  before giving them to player 2. Gamepads map to players in connection order.
- EmulatorJS is GPL-3.0; loading it from its CDN keeps it out of an MIT repo.
- Mention in the page that it needs a browser with WebGL. Test it as in testing.md.

## The WorkAdventure arcade cabinet (cloud-game)

The arcade streams games with cloud-game in cabinet mode (https://github.com/moufmouf/cloud-game, see its
CABINET.md). SNES runs on the snes9x libretro core, so the headless tests already cover the same emulator. How
ROMs get deployed to WorkAdventure's servers is in the team's internal deploy repository: ask the user for it
rather than guessing. What holds whatever the deployment:

- The game id is the ROM's file name without the extension; the cabinet page takes it as `game=<Name>`, with
  `players=4` for 4 players.
- Players get slots in order of arrival (badges: P1 red, P2 blue, P3 green, P4 yellow); keys are arrows,
  Z = A, X = B, Enter = Start. Keep HUD text away from the top corners, where the badges sit.
- The page sends input from `requestAnimationFrame`, so a background tab sends nothing: when testing several
  players from one machine, bring each tab to the front while it plays. Close test tabs afterwards: an open
  cabinet keeps a worker busy.
- After a deploy, check that the server runs the ROM you built (compare checksums), not just that the page loads.
- Only ship ROMs whose license allows it, and record that license next to the ROM.
