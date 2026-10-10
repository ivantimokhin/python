#!/usr/bin/env python3
"""Convert 32-bit float PCM raw stereo audio into 16-bit WAV.

The raw input is assumed to be interleaved stereo PCM in 32-bit float format
(4 bytes per sample, little-endian), with samples normalized to the range
[-1.0, 1.0]. The output is a standard 16-bit PCM WAV file using signed
little-endian int16 samples.

Usage:
    python wav16.py input.raw output.wav --sample-rate 48000
"""

from __future__ import annotations

import argparse
import wave
from array import array
from pathlib import Path


def read_float32_raw(path: Path, channels: int = 2) -> array:
    """Read a raw float32 PCM file and return interleaved float samples."""
    data = path.read_bytes()
    if len(data) % (4 * channels) != 0:
        raise ValueError(
            f"Input length {len(data)} is not divisible by {4 * channels} bytes for "
            f"{channels} channels."
        )

    samples = array("f")
    samples.frombytes(data)
    return samples


def float32_to_int16(samples: array, channels: int = 2) -> array:
    """Convert normalized float32 audio to int16 PCM samples.

    The input is assumed to be in the range [-1.0, 1.0], which is the common
    convention for float PCM audio. Values are clamped to the valid 16-bit range,
    with no dithering applied.
    """
    if len(samples) % channels != 0:
        raise ValueError(f"Sample count {len(samples)} is not divisible by channel count {channels}.")

    out = array("h")
    for value in samples:
        clamped = max(-1.0, min(1.0, float(value)))
        pcm = int(round(clamped * 32767.0))
        if pcm > 32767:
            pcm = 32767
        elif pcm < -32768:
            pcm = -32768
        out.append(pcm)
    return out


def write_wav(path: Path, samples: array, channels: int, sample_rate: int) -> None:
    """Write interleaved int16 samples to a WAV file."""
    frames = len(samples) // channels

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.setnframes(frames)
        wav_file.writeframes(samples.tobytes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert headerless 32-bit float stereo raw PCM into 16-bit WAV."
    )
    parser.add_argument("input", type=Path, help="Input .raw file containing 32-bit float PCM samples")
    parser.add_argument("output", type=Path, help="Output .wav file")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=48000,
        help="Sample rate to store in the WAV header (default: 48000)",
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=2,
        help="Number of audio channels (default: 2)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.channels <= 0:
        raise ValueError("Channel count must be positive.")
    if args.sample_rate <= 0:
        raise ValueError("Sample rate must be positive.")

    raw_samples = read_float32_raw(args.input, channels=args.channels)
    pcm16 = float32_to_int16(raw_samples, channels=args.channels)
    write_wav(args.output, pcm16, channels=args.channels, sample_rate=args.sample_rate)

    print(
        f"Converted {len(raw_samples)} float32 samples -> {len(pcm16)} int16 samples "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
