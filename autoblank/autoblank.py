import argparse
import numpy as np
from pathlib import Path
from scipy.io import wavfile


def dBFS_to_float32(dbfs: float) -> float:
    """
    Convert dBFS to normalized float32 amplitude.
    0 dBFS = 1.0
    """
    if dbfs > 0:
        return 1.0
    if dbfs < -100:
        return 0.0
    return float(np.float32(10.0 ** (dbfs / 20.0)))


def find_trim_range(samples: np.ndarray, threshold: float) -> tuple[int, int]:
    """
    Return [start, end] of the first/last region above threshold.
    This is for trimming only: no sample in the middle is modified.
    """
    sample_array = np.asarray(samples, dtype=np.float32)
    abs_samples = np.abs(sample_array)

    active = abs_samples >= threshold

    if not np.any(active):
        return 0, len(sample_array) - 1

    start = int(np.argmax(active))
    end = int(len(active) - 1 - np.argmax(active[::-1]))

    return start, end


def add_silence_around_trimmed(
    data: np.ndarray,
    leading_samples: int = 0,
    trailing_samples: int = 0,
    padding_dbfs: float | None = None,
    pad_frequency_hz: float = 220.0,
    sample_rate: int = 44100,
) -> np.ndarray:
    """
    Add silence or an LFO-generated sine tone before and after the audio data.
    Silence duration is given in sample count.
    """
    leading_samples = max(0, int(leading_samples))
    trailing_samples = max(0, int(trailing_samples))

    if leading_samples == 0 and trailing_samples == 0:
        return data

    def noise_pad(length: int, level_dbfs: float, num_channels: int = 1) -> np.ndarray:
        if length <= 0:
            return np.zeros(0, dtype=data.dtype)
        amp = dBFS_to_float32(level_dbfs)
        if amp <= 0:
            return np.zeros((length, num_channels) if num_channels > 1 else length, dtype=data.dtype)
        rng = np.random.default_rng()
        size = (length, num_channels) if num_channels > 1 else length
        return rng.uniform(-amp, amp, size=size).astype(data.dtype, copy=False)

    def lfo_pad(length: int, level_dbfs: float, frequency_hz: float, num_channels: int = 1) -> np.ndarray:
        if length <= 0:
            return np.zeros(0, dtype=data.dtype)
        if frequency_hz <= 0 or sample_rate <= 0:
            return np.zeros((length, num_channels) if num_channels > 1 else length, dtype=data.dtype)

        amp = dBFS_to_float32(level_dbfs)
        if amp <= 0:
            return np.zeros((length, num_channels) if num_channels > 1 else length, dtype=data.dtype)

        t = np.arange(length, dtype=np.float32) / float(sample_rate)
        base = np.sin(2.0 * np.pi * frequency_hz * t).astype(np.float32)
        lfo = 0.5 * (1.0 + np.sin(2.0 * np.pi * 0.5 * t)).astype(np.float32)
        tone = base * lfo

        if num_channels > 1:
            tone = np.tile(tone[:, None], (1, num_channels))
        return np.clip(tone * amp, -1.0, 1.0).astype(data.dtype, copy=False)

    if data.ndim == 1:
        out = np.zeros(len(data) + leading_samples + trailing_samples, dtype=data.dtype)

        if padding_dbfs is not None:
            lead_pad = lfo_pad(leading_samples, padding_dbfs, pad_frequency_hz)
            trail_pad = noise_pad(trailing_samples, padding_dbfs)
        else:
            lead_pad = np.zeros(leading_samples, dtype=data.dtype)
            trail_pad = np.zeros(trailing_samples, dtype=data.dtype)

        out[:leading_samples] = lead_pad
        out[leading_samples:leading_samples + len(data)] = data
        out[-trailing_samples:] = trail_pad
        return out

    if data.ndim == 2:
        out = np.zeros(
            (data.shape[0] + leading_samples + trailing_samples, data.shape[1]),
            dtype=data.dtype,
        )

        if padding_dbfs is not None:
            lead_pad = lfo_pad(leading_samples, padding_dbfs, pad_frequency_hz, num_channels=data.shape[1])
            trail_pad = noise_pad(trailing_samples, padding_dbfs, num_channels=data.shape[1])
        else:
            lead_pad = np.zeros((leading_samples, data.shape[1]), dtype=data.dtype)
            trail_pad = np.zeros((trailing_samples, data.shape[1]), dtype=data.dtype)

        out[:leading_samples, :] = lead_pad
        out[leading_samples:leading_samples + data.shape[0], :] = data
        out[-trailing_samples:, :] = trail_pad
        return out

    raise ValueError(f"Unsupported channel layout: shape={data.shape}")


def auto_trim_wav(
    input_path: str | Path,
    output_path: str | Path,
    threshold_dbfs: float = -30.0,
    threshold_level: float | None = None,
    leading_silence_samples: int = 0,
    trailing_silence_samples: int = 0,
    padding_dbfs: float | None = None,
    pad_frequency_hz: float = 220.0,
) -> None:
    """
    Trim silence before and after real audio and then add an LFO-generated tone
    before the trimmed result, with regular noise after it.
    """
    fs, data = wavfile.read(str(input_path))

    if np.issubdtype(data.dtype, np.floating):
        processed = data.astype(np.float32, copy=False)
    elif np.issubdtype(data.dtype, np.integer):
        max_abs = float(np.iinfo(data.dtype).max + 1)
        processed = (data.astype(np.float32) / max_abs).astype(np.float32, copy=False)
    else:
        raise ValueError(f"Unsupported WAV dtype for float32 conversion: {data.dtype}")

    if threshold_level is None:
        threshold_level = dBFS_to_float32(threshold_dbfs)

    threshold_level = float(np.clip(threshold_level, 0.0, 1.0))

    if processed.ndim == 1:
        start, end = find_trim_range(processed, threshold_level)
        processed = processed[start:end + 1]
    elif processed.ndim == 2:
        starts = []
        ends = []

        for ch in range(processed.shape[1]):
            start, end = find_trim_range(processed[:, ch], threshold_level)
            starts.append(start)
            ends.append(end)

        trim_start = max(starts)
        trim_end = min(ends)

        if trim_end < trim_start:
            trim_start = 0
            trim_end = processed.shape[0] - 1

        processed = processed[trim_start:trim_end + 1]
    else:
        raise ValueError(f"Unsupported channel layout: shape={processed.shape}")

    processed = add_silence_around_trimmed(
        processed,
        leading_samples=leading_silence_samples,
        trailing_samples=trailing_silence_samples,
        padding_dbfs=padding_dbfs,
        pad_frequency_hz=pad_frequency_hz,
        sample_rate=fs,
    )

    wavfile.write(str(output_path), fs, processed.astype(np.float32, copy=False))
    print(
        f"Saved {output_path} | threshold={threshold_level} (float32), "
        f"dBFS={threshold_dbfs}, lead={leading_silence_samples}, trail={trailing_silence_samples}, "
        f"padding_dbfs={padding_dbfs} | pad_frequency_hz={pad_frequency_hz}"
    )


if __name__ == "__main__":
    auto_trim_wav(
        input_path="01-Guitar-261101_0106-jsfx_sinc_512_1536.wav",
        output_path="output_trim_1323_noise4.wav",
        threshold_dbfs=-40.0,
        threshold_level=None,
        leading_silence_samples=44100,
        trailing_silence_samples=120,
        padding_dbfs=-40.0,
        pad_frequency_hz=82.41,
    )
