import os
import numpy as np
import scipy.signal as signal
import scipy.io.wavfile as wavfile


def filter_wav_file(input_filename, output_filename, cutoff_hz=2000, num_taps=512):
    # 1. Проверяем, существует ли входной файл
    if not os.path.exists(input_filename):
        print(f"Ошибка: Файл '{input_filename}' не найден!")
        return

    # 2. Читаем WAV файл
    # sample_rate — частота дискретизации (например, 44100 или 176400)
    # data — массив сэмплов аудио
    sample_rate, data = wavfile.read(input_filename)
    print(f"Успешно прочитан файл: {input_filename}")
    print(f"Исходная частота дискретизации: {sample_rate} Гц")
    print(f"Формат данных: {data.dtype}")

    # Переводим аудиоданные во флоат (от -1.0 до 1.0) для корректной математики DSP
    # Сохраняем исходный тип, чтобы в конце вернуть всё обратно
    original_dtype = data.dtype
    if original_dtype == np.int16:
        audio_data = data.astype(np.float32) / 32768.0
    elif original_dtype == np.int32:
        audio_data = data.astype(np.float32) / 2147483648.0
    else:
        audio_data = data.astype(np.float32)

    # 3. Проектируем Sinc-фильтр (Low-pass)
    nyquist = sample_rate / 2
    
    # Защита: частота среза не может быть выше частоты Найквиста
    if cutoff_hz >= nyquist:
        print(f"Ошибка: Частота среза {cutoff_hz} Гц не может быть выше или равна частоте Найквиста файла ({nyquist} Гц)!")
        return
        
    normalized_cutoff = cutoff_hz / nyquist

    # Генерация 512 коэффициентов Windowed Sinc фильтра (окно Хэмминга)
    filter_coefficients = signal.firwin(num_taps, normalized_cutoff, window='hamming')
    print(f"Спроектирован sinc-фильтр со срезом {cutoff_hz} Гц (нормализованная: {normalized_cutoff:.4f})")

    # 4. Применяем фильтрацию (свертку)
    print("Идет фильтрация сигнала (свертка)...")
    
    # Обработка стерео или моно
    if len(audio_data.shape) == 2:  # Стерео файл
        # Фильтруем каждый канал отдельно
        left_channel = np.convolve(audio_data[:, 0], filter_coefficients, mode='same')
        right_channel = np.convolve(audio_data[:, 1], filter_coefficients, mode='same')
        filtered_audio = np.column_stack((left_channel, right_channel))
    else:  # Моно файл
        filtered_audio = np.convolve(audio_data, filter_coefficients, mode='same')

    # 5. Возвращаем аудио в исходный аудиоформат и диапазон
    if original_dtype == np.int16:
        # Ограничиваем значения (clipping), чтобы избежать цифрового клиппинга при конвертации
        filtered_audio = np.clip(filtered_audio, -1.0, 1.0)
        output_data = (filtered_audio * 32767.0).astype(np.int16)
    elif original_dtype == np.int32:
        filtered_audio = np.clip(filtered_audio, -1.0, 1.0)
        output_data = (filtered_audio * 2147483647.0).astype(np.int32)
    else:
        output_data = filtered_audio

    # 6. Записываем результат в новый файл
    wavfile.write(output_filename, sample_rate, output_data)
    print(f"Фильтрация завершена! Результат сохранен в: {output_filename}\n")


if __name__ == "__main__":
    input_filename = "01-Guitar-261101_0012-jsfx.wav"
    cutoff_hz = 20000
    num_taps = 512
    base_name = input_filename.rsplit(".", 1)[0]
    output_filename = f"{base_name}_{cutoff_hz}.wav"

    filter_wav_file(input_filename, output_filename, cutoff_hz=cutoff_hz, num_taps=num_taps)
