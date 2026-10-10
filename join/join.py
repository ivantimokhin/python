#!/usr/bin/env python3
"""Join two raw PCM 32-bit float mono files into a stereo raw float32 file.

The left channel is delayed by 1 sample relative to the right channel.

Usage: join.py left.raw right.raw out.raw [--samplerate N]

This script operates on raw interleaved float32 little-endian files (mono).
It pads the shorter input with zeros so both channels align after applying the delay.
"""

import sys
import struct
from pathlib import Path


def read_f32_mono(path: Path):
    data = path.read_bytes()
    # float32 little-endian
    if len(data) % 4 != 0:
        raise SystemExit(f"Input {path} size not a multiple of 4 bytes")
    count = len(data) // 4
    return list(struct.unpack('<' + 'f' * count, data))


def write_f32_stereo_interleaved(path: Path, left, right):
    # left and right are lists of floats of equal length
    out = bytearray()
    for l, r in zip(left, right):
        out += struct.pack('<f', l)
        out += struct.pack('<f', r)
    path.write_bytes(bytes(out))


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        raise SystemExit(1)

    left_in = Path(argv[1])
    right_in = Path(argv[2])
    out = Path(argv[3])    

    left = read_f32_mono(left_in)
    right = read_f32_mono(right_in)

    # Delay left by 1 sample: prepend a zero at start and drop last sample
    # To keep overall length, we'll prepend a zero to left. That makes left length+1.
    # To produce equal-length channels, pad the shorter channel with zeros to match.
    left_delayed = [0.0] + left

    # Ensure both channels same length
    maxlen = max(len(left_delayed), len(right))
    if len(left_delayed) < maxlen:
        left_delayed += [0.0] * (maxlen - len(left_delayed))
    if len(right) < maxlen:
        right += [0.0] * (maxlen - len(right))

    write_f32_stereo_interleaved(out, left_delayed, right)
    print(f"Wrote stereo (float32) to {out} — frames: {maxlen}")


if __name__ == '__main__':
    main(sys.argv)
