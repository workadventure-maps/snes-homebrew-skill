#!/bin/sh
# Download the toolchain (PVSnesLib) and the snes9x libretro core used by the tests into .tools/
set -e
cd "$(dirname "$0")/.."
mkdir -p .tools

if [ ! -d .tools/pvsneslib ]; then
    curl -sSL -o .tools/pvsneslib.zip \
        https://github.com/alekmaul/pvsneslib/releases/download/4.6.0/pvsneslib_460_64b_linux_release.zip
    (cd .tools && unzip -q pvsneslib.zip && rm pvsneslib.zip)
fi

# the same core cloud-game runs; nightly build, not pinned
if [ ! -f .tools/snes9x/snes9x_libretro.so ]; then
    mkdir -p .tools/snes9x
    curl -sSL -o .tools/snes9x/core.zip \
        https://buildbot.libretro.com/nightly/linux/x86_64/latest/snes9x_libretro.so.zip
    (cd .tools/snes9x && unzip -q core.zip && rm core.zip)
fi
