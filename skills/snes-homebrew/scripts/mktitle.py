"""Build the title screen: background art + logo -> SNES 4bpp tiles, tilemap and palettes.

Usage: mktitle.py <assets dir> <output dir>

  assets/title_bg.png    background art, any size, scaled to 256x224
  assets/title_logo.png  logo on a flat magenta background, scaled to fit the top of the screen

Outputs title.pic (tiles), title.map (32x32 BG map) and title.pal (palettes 2..7, 16 colors each).
Each 8x8 tile can only use one 15-color palette, so tiles are grouped into PALETTES palettes
(k-means: build each palette from its tiles' pixels, move each tile to its best palette, repeat).
"""
import os
import sys

import numpy as np
from PIL import Image

W, H = 256, 224
PALETTES = 6       # BG palettes 2..7; 0 and 1 hold the 2bpp text palettes (BG3)
FIRST_PALETTE = 2
COLORS = 15        # color 0 of each palette is transparent


def snes(rgb):
    """Round to the SNES's 5 bits per channel."""
    return (np.asarray(rgb, dtype=np.int32) >> 3) << 3


def compose(assets):
    bg = Image.open(os.path.join(assets, 'title_bg.png')).convert('RGB')
    # crop to 8:7, then scale down
    bw, bh = bg.size
    if bw * H > bh * W:
        nw = bh * W // H
        bg = bg.crop(((bw - nw) // 2, 0, (bw - nw) // 2 + nw, bh))
    else:
        nh = bw * H // W
        bg = bg.crop((0, (bh - nh) // 2, bw, (bh - nh) // 2 + nh))
    img = bg.resize((W, H), Image.LANCZOS).convert('RGBA')

    logo = Image.open(os.path.join(assets, 'title_logo.png')).convert('RGBA')
    px = np.asarray(logo).copy()
    r, g, b = px[..., 0].astype(int), px[..., 1].astype(int), px[..., 2].astype(int)
    px[..., 3] = np.where((r > 200) & (b > 200) & (g < 90), 0, 255)  # key out magenta
    logo = Image.fromarray(px)
    logo = logo.crop(logo.getbbox())
    lw = 236
    lh = logo.height * lw // logo.width
    if lh > 88:
        lh, lw = 88, logo.width * 88 // logo.height
    logo = logo.resize((lw, lh), Image.LANCZOS)
    a = np.asarray(logo).copy()
    a[..., 3] = np.where(a[..., 3] > 128, 255, 0)  # hard edges
    img.alpha_composite(Image.fromarray(a), ((W - lw) // 2, 10))
    return snes(np.asarray(img.convert('RGB')))


def tiles_of(img):
    t = img.reshape(H // 8, 8, W // 8, 8, 3).swapaxes(1, 2)
    return t.reshape(-1, 64, 3)  # (896, 64, 3), row-major tiles


def make_palette(pixels):
    """15 SNES colors for a set of pixels (median cut, no dithering)."""
    im = Image.fromarray(pixels.reshape(1, -1, 3).astype(np.uint8))
    q = im.quantize(COLORS, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[:COLORS * 3]).reshape(-1, 3)
    pal = snes(pal)
    used = len(set(map(tuple, pal)))
    return pal, used


def errors(tiles, pal):
    """Squared error of each tile mapped to its nearest colors in pal: (n,)."""
    d = ((tiles[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1)  # (n, 64, 15)
    return d.min(-1).sum(-1)


def quantize(tiles):
    n = len(tiles)
    # start from k-means on the tiles' average color
    means = tiles.mean(1)
    rng = np.random.default_rng(1)
    centers = means[rng.choice(n, PALETTES, replace=False)]
    for _ in range(10):
        assign = ((means[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
        centers = np.array([means[assign == k].mean(0) if (assign == k).any() else centers[k]
                            for k in range(PALETTES)])
    pals = None
    for _ in range(8):
        pals = []
        for k in range(PALETTES):
            members = tiles[assign == k]
            if len(members) == 0:  # empty group: seed it with the worst tile
                members = tiles[[0]]
            pals.append(make_palette(members.reshape(-1, 3))[0])
        err = np.stack([errors(tiles, p) for p in pals], 1)  # (n, PALETTES)
        new = err.argmin(1)
        if (new == assign).all():
            break
        assign = new
    return assign, pals


def planar(idx):
    """64 color indices (row-major) -> 32 bytes of SNES 4bpp tile data."""
    out = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = idx[y * 8 + x]
            bit = 0x80 >> x
            for plane in range(4):
                if v >> plane & 1:
                    out[(plane >> 1) * 16 + y * 2 + (plane & 1)] |= bit
    return bytes(out)


def main():
    assets, out = sys.argv[1], sys.argv[2]
    img = compose(assets)
    tiles = tiles_of(img)
    assign, pals = quantize(tiles)

    pic, seen, tmap = bytearray(), {}, [0] * 1024
    for i, t in enumerate(tiles):
        pal = pals[assign[i]]
        idx = ((t[:, None, :] - pal[None]) ** 2).sum(-1).argmin(1) + 1  # 1..15
        grid = idx.reshape(8, 8)
        entry = None
        for flip, g in ((0, grid), (0x4000, grid[:, ::-1]), (0x8000, grid[::-1, :]), (0xC000, grid[::-1, ::-1])):
            key = (int(assign[i]), g.tobytes())
            if key in seen:
                entry = seen[key] | flip
                break
        if entry is None:
            n = len(pic) // 32
            seen[(int(assign[i]), grid.tobytes())] = n
            pic += planar(grid.reshape(-1))
            entry = n
        ty, tx = divmod(i, W // 8)
        tmap[ty * 32 + tx] = entry | (FIRST_PALETTE + int(assign[i])) << 10

    pal_bytes = bytearray()
    for p in pals:
        cols = [(0, 0, 0)] + [tuple(int(v) for v in c) for c in p]
        for r, g, b in cols:
            v = (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10
            pal_bytes += v.to_bytes(2, 'little')

    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'title.pic'), 'wb').write(pic)
    open(os.path.join(out, 'title.map'), 'wb').write(b''.join(e.to_bytes(2, 'little') for e in tmap))
    open(os.path.join(out, 'title.pal'), 'wb').write(pal_bytes)

    # what the SNES will show, for a quick look
    preview = np.zeros((H, W, 3), np.uint8)
    for i, t in enumerate(tiles):
        pal = pals[assign[i]]
        idx = ((t[:, None, :] - pal[None]) ** 2).sum(-1).argmin(1)
        ty, tx = divmod(i, W // 8)
        preview[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = pal[idx].reshape(8, 8, 3)
    Image.fromarray(preview).save(os.path.join(out, 'title_preview.png'))
    print(f'title: {len(pic) // 32} tiles, {PALETTES} palettes')


if __name__ == '__main__':
    main()
