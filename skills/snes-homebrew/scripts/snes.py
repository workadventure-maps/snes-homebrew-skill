"""Minimal headless libretro frontend for automated ROM tests.

Drives the snes9x libretro core (the same core cloud-game runs for the arcade):
scripted input for up to 4 players (P1 on port 1, P2-P4 on a Multitap in port 2),
screenshots and work RAM reads.
"""
import ctypes as C
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, '..', '.tools', 'snes9x', 'snes9x_libretro.so')

DEVICE_JOYPAD = 1
DEVICE_MULTITAP = (1 << 8) | DEVICE_JOYPAD
MEMORY_SYSTEM_RAM = 2
MEMORY_VIDEO_RAM = 3
# libretro joypad ids
BUTTONS = {'b': 0, 'y': 1, 'select': 2, 'start': 3, 'up': 4, 'down': 5, 'left': 6, 'right': 7,
           'a': 8, 'x': 9, 'l': 10, 'r': 11}

ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class Snes:
    def __init__(self, rom, multitap=True):
        self.lib = C.CDLL(CORE)
        self.held = [set() for _ in range(5)]  # buttons held per player
        self.frame = None
        self.frames = 0
        self.loudness = 0  # peak audio sample of the last frame
        self.audio = None  # set to a list to record PCM (stereo int16, 32040 Hz)
        # keep references so callbacks are not garbage collected
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(lambda l, r: None),
                     AUDIO_BATCH_CB(self._audio), POLL_CB(lambda: None), STATE_CB(self._state)]
        for fn, cb in zip(['retro_set_environment', 'retro_set_video_refresh', 'retro_set_audio_sample',
                           'retro_set_audio_sample_batch', 'retro_set_input_poll', 'retro_set_input_state'],
                          self._cbs):
            getattr(self.lib, fn)(cb)
        self.lib.retro_init()
        data = open(rom, 'rb').read()
        self._rom = C.create_string_buffer(data, len(data))
        info = GameInfo(rom.encode(), C.cast(self._rom, C.c_void_p), len(data), None)
        if not self.lib.retro_load_game(C.byref(info)):
            raise RuntimeError('core refused ' + rom)
        self.lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
        self.lib.retro_set_controller_port_device(1, DEVICE_MULTITAP if multitap else DEVICE_JOYPAD)
        self.lib.retro_get_memory_data.restype = C.c_void_p
        self.lib.retro_get_memory_size.restype = C.c_size_t

    def _env(self, cmd, data):
        cmd &= 0xffff  # drop the experimental flag
        if cmd == 10:  # SET_PIXEL_FORMAT: accept RGB565 only
            return C.cast(data, C.POINTER(C.c_int))[0] == 2
        if cmd in (9, 31):  # GET_SYSTEM_DIRECTORY, GET_SAVE_DIRECTORY
            C.cast(data, C.POINTER(C.c_char_p))[0] = None
            return True
        if cmd == 3:  # GET_CAN_DUPE
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        return False

    def _video(self, data, w, h, pitch):
        if data:
            self.frame = (C.string_at(data, pitch * h), w, h, pitch)

    def _audio(self, data, n):
        import numpy as np
        pcm = np.frombuffer(C.string_at(data, n * 4), dtype='<i2')
        self.loudness = max(self.loudness, int(np.abs(pcm).max()) if n else 0)
        if self.audio is not None:
            self.audio.append(pcm.tobytes())
        return n

    def _state(self, port, device, index, id):
        if device != DEVICE_JOYPAD or port >= 5:
            return 0
        return 1 if any(BUTTONS[b] == id for b in self.held[port]) else 0

    def run(self, frames=1):
        for _ in range(frames):
            self.loudness = 0
            self.lib.retro_run()
            self.frames += 1

    def press(self, player, *buttons, frames=1, release=True):
        """Hold buttons for `frames` frames. player 0 = P1 ... 3 = P4."""
        self.held[player] |= set(buttons)
        self.run(frames)
        if release:
            self.held[player] -= set(buttons)

    def wram(self):
        return self._mem(MEMORY_SYSTEM_RAM)

    def poke_wram(self, offset, data):
        C.memmove(self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM) + offset, bytes(data), len(data))

    def vram(self):
        return self._mem(MEMORY_VIDEO_RAM)

    def _mem(self, kind):
        return C.string_at(self.lib.retro_get_memory_data(kind), self.lib.retro_get_memory_size(kind))

    def screenshot(self, path):
        import numpy as np
        from PIL import Image
        buf, w, h, pitch = self.frame
        px = np.frombuffer(buf, dtype='<u2').reshape(h, pitch // 2)[:, :w]
        rgb = np.dstack([(px >> 11) << 3, ((px >> 5) & 63) << 2, (px & 31) << 3]).astype('uint8')
        Image.fromarray(rgb).save(path)


def symbols(sym_path):
    """Read a wlalink .sym file into {name: wram offset}, for labels in banks $7E/$7F or the low-RAM mirror."""
    out = {}
    for line in open(sym_path):
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 8 or line.startswith(';'):
            continue
        bank, addr = int(parts[0][:4], 16), int(parts[0][4:], 16)
        if bank in (0x7e, 0x7f):
            out[parts[1]] = (bank - 0x7e) * 0x10000 + addr
        elif addr < 0x2000:
            out[parts[1]] = addr
    return out


if __name__ == '__main__':
    # usage: snes.py rom.sfc frames out.png
    s = Snes(sys.argv[1])
    s.run(int(sys.argv[2]))
    s.screenshot(sys.argv[3])
