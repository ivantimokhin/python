import numpy as np
import scipy.io.wavfile as wavfile
from scipy.signal import butter, filtfilt


def butter_lowpass_filter(data, cutoff, fs, order=5):
    """Фильтр нижних частот (оставляет бас нетронутым)."""
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype="low", analog=False)
    return filtfilt(b, a, data, axis=0)


def apply_soft_stutter(high_data, sample_rate, beat_interval, chunk_ms):
    """Применяет мягкое заикание к высокочастотному слою с кроссфейдами."""
    chunk_size = int(sample_rate * (chunk_ms / 1000.0))

    # Создаем очень мягкое сглаживание углов (25% от размера кусочка)
    fade_len = int(chunk_size * 0.25)
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)

    if len(high_data.shape) > 1:
        fade_in = np.expand_dims(fade_in, axis=1)
        fade_out = np.expand_dims(fade_out, axis=1)

    glitched_chunks = []
    chunk_counter = 0

    for i in range(0, len(high_data), chunk_size):
        chunk = high_data[i : i + chunk_size]

        if len(chunk) < chunk_size:
            glitched_chunks.append(chunk)
            continue

        # Каждые N блоков повторяем аудио
        if chunk_counter % beat_interval == 0:
            # Сглаживаем края кусочка, чтобы убрать резкие щелчки
            faded_chunk = chunk.copy()
            faded_chunk[:fade_len] *= fade_in
            faded_chunk[-fade_len:] *= fade_out

            # Повторяем его 2 раза (мягкое «эхо-заикание»)
            glitched_chunks.append(faded_chunk)
            glitched_chunks.append(faded_chunk)
        else:
            glitched_chunks.append(chunk)

        chunk_counter += 1

    return np.concatenate(glitched_chunks, axis=0)


def make_calm_glitch(
    input_path, output_path, cutoff_hz=800, beat_interval=6, chunk_ms=35
):
    """Разделяет аудио, обрабатывает верх и склеивает обратно, сохраняя стерео-картину."""
    sample_rate, data = wavfile.read(input_path)
    original_dtype = data.dtype

    # Переводим во float для точных вычислений
    data_float = data.astype(float)

    # 1. Выделяем стабильный фундамент (низкие и средние частоты ниже 800 Гц)
    print("Фильтрация аудио...")
    low_freqs = butter_lowpass_filter(data_float, cutoff_hz, sample_rate)

    # 2. Выделяем высокие частоты (вычитаем низкие из оригинала)
    high_freqs = data_float - low_freqs

    # 3. Применяем статтеринг ТОЛЬКО к высоким частотам
    print("Применение мягкого статтеринга к ВЧ...")
    high_freqs_glitched = apply_soft_stutter(
        high_freqs, sample_rate, beat_interval, chunk_ms
    )

    # Выравниваем длину массивов (так как статтеринг удлиняет аудио)
    # Чтобы сохранить стабильную структуру, мы просто подрежем или расширим бас под новую длину
    new_len = len(high_freqs_glitched)
    if len(low_freqs) < new_len:
        # Продлеваем бас тишиной или дублированием финала, если нужно
        padded_low = np.zeros((new_len, data.shape[1])) if len(data.shape) > 1 else np.zeros(new_len)
        padded_low[: len(low_freqs)] = low_freqs
        low_freqs = padded_low
    else:
        low_freqs = low_freqs[:new_len]

    # 4. Смешиваем обработанный верх и чистый низ обратно
    final_data = low_freqs + high_freqs_glitched

    # Ограничиваем пики, чтобы избежать клиппинга, и возвращаем исходный тип данных
    final_data = np.clip(final_data, np.iinfo(original_dtype).min, np.iinfo(original_dtype).max)
    wavfile.write(output_path, sample_rate, final_data.astype(original_dtype))
    print(f"Спокойный аудиофайл сохранен в: {output_path}")


# Пример запуска:
# Разделение на 800 Гц. Бас стабилен, верха мягко заикаются кусочками по 35 мс каждые 6 блоков.
make_calm_glitch("input.wav", "calm_stable_glitch.wav", cutoff_hz=800, beat_interval=6, chunk_ms=35)
