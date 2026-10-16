#!/usr/bin/env python3
"""Join two raw PCM 32-bit float mono files into a stereo raw float32 file.

Either the left or the right channel can be delayed relative to the other.

Usage: join.py left.raw right.raw out.raw [--delay-left N | --delay-right N]

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
    args = list(argv[1:])
    if len(args) < 3:
        print(__doc__)
        raise SystemExit(1)

    left_delay = 0
    right_delay = 0
    left_delay_index = next((i for i, arg in enumerate(args) if arg == '--delay-left'), None)
    right_delay_index = next((i for i, arg in enumerate(args) if arg == '--delay-right'), None)

    if left_delay_index is not None and right_delay_index is not None:
        raise SystemExit("Left and right channel delays are mutually exclusive")

    if left_delay_index is not None:
        if left_delay_index + 1 >= len(args):
            raise SystemExit("Missing value for delay")
        try:
            left_delay = int(args[left_delay_index + 1])
        except ValueError as exc:
            raise SystemExit(f"Invalid delay value: {args[left_delay_index + 1]}") from exc
        if left_delay < 0:
            raise SystemExit("Delay must be >= 0")
        args.pop(left_delay_index + 1)
        args.pop(left_delay_index)

    if right_delay_index is not None:
        if right_delay_index + 1 >= len(args):
            raise SystemExit("Missing value for --delay-right")
        try:
            right_delay = int(args[right_delay_index + 1])
        except ValueError as exc:
            raise SystemExit(f"Invalid delay value: {args[right_delay_index + 1]}") from exc
        if right_delay < 0:
            raise SystemExit("Delay must be >= 0")
        args.pop(right_delay_index + 1)
        args.pop(right_delay_index)

    if len(args) < 3:
        print(__doc__)
        raise SystemExit(1)

    left_in = Path(args[0])
    right_in = Path(args[1])
    out = Path(args[2])

    left = read_f32_mono(left_in)
    right = read_f32_mono(right_in)

    left_delayed = [0.0] * left_delay + left
    right_delayed = [0.0] * right_delay + right

    maxlen = max(len(left_delayed), len(right_delayed))
    if len(left_delayed) < maxlen:
        left_delayed += [0.0] * (maxlen - len(left_delayed))
    if len(right_delayed) < maxlen:
        right_delayed += [0.0] * (maxlen - len(right_delayed))

    write_f32_stereo_interleaved(out, left_delayed, right_delayed)
    print(
        f"Wrote stereo (float32) to {out} — frames: {maxlen} — "
        f"left delay: {left_delay} samples — right delay: {right_delay} samples"
    )


if __name__ == '__main__':
    main(sys.argv)
