# snes-homebrew: a Claude Code skill for SNES games

Teaches Claude how to build original Super Nintendo games as real ROMs, in C with
[PVSnesLib](https://github.com/alekmaul/pvsneslib): toolchain setup, VBlank and frame-time budgets, headless tests
on the snes9x core, graphics and sound, 4 players with a Multitap, and publishing (a GitHub Pages web player, the
WorkAdventure arcade cabinet).

It was written after building [Bombadventure](https://github.com/workadventure-maps/bombadventure), which serves
as its worked example.

## Install

In Claude Code:

```
/plugin marketplace add workadventure-maps/snes-homebrew-skill
/plugin install snes-homebrew@snes-homebrew
```

Or copy `skills/snes-homebrew/` into `~/.claude/skills/`.

Then ask for a game ("let's make a 2-player SNES racing game"): the skill loads on its own.

## Contents

| Path | What |
|---|---|
| `skills/snes-homebrew/SKILL.md` | the workflow and the rules that matter on every game |
| `skills/snes-homebrew/references/` | toolchain and C compiler, frame budgets, testing, graphics and sound, publishing |
| `skills/snes-homebrew/scripts/` | `setup.sh` (toolchain download), `snes.py` (headless test frontend), `mktitle.py` (title screen converter) |

## Improving it

After each new game, add what went wrong or took long, with measurements where possible. Keep game-specific
choices (characters, rules, art style) in the game's own repo.

## License

MIT, see [LICENSE](LICENSE).
