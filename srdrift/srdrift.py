import numpy as np
import scipy.interpolate as interpolate
import soundfile as sf
import os

def windowed_sinc_interp_nonuniform(real_time, audio_data, ideal_time, num_taps=512):
    """
    Высокоточный векторизованный оконный Sinc-ресэмплинг для неравномерной временной сетки.
    """
    num_output = len(ideal_time)
    num_channels = audio_data.shape[1]
    processed_audio = np.zeros((num_output, num_channels), dtype=np.float32)
    
    # Оценка средней частоты дискретизации для нормирования шкалы sinc
    fs_est = 1.0 / np.mean(np.diff(real_time))
    
    # Обрабатываем блоками (чанками), чтобы не перегружать RAM огромными матрицами
    chunk_size = 4096
    half_taps = num_taps // 2
    
    # Создаем статический сглаживающий фильтр Хэмминга для устранения джиттера
    window = np.hamming(num_taps)
    
    for start_idx in range(0, num_output, chunk_size):
        end_idx = min(start_idx + chunk_size, num_output)
        t_targets = ideal_time[start_idx:end_idx]
        
        # Находим ближайшие индексы в исходной временной сетке
        nearest_indices = np.searchsorted(real_time, t_targets)
        
        # Формируем матрицу индексов окрестности сэмплов вокруг целевой точки
        offsets = np.arange(-half_taps, half_taps)
        idx_matrix = nearest_indices[:, None] + offsets[None, :]
        idx_matrix = np.clip(idx_matrix, 0, len(real_time) - 1)
        
        # Извлекаем точные физические моменты времени для выбранных точек
        t_samples = real_time[idx_matrix]
        
        # Расчет временных разностей, приведенных к шагу дискретизации
        t_diff = (t_targets[:, None] - t_samples) * fs_est
        
        # Вычисляем sinc-коэффициенты (np.sinc в numpy уже нормализован: sin(pi*x)/(pi*x))
        sinc_coeffs = np.sinc(t_diff) * window[None, :]
        
        # Нормализация суммы коэффициентов в строках во избежание просадки/искажения громкости
        row_sums = np.sum(sinc_coeffs, axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        sinc_coeffs /= row_sums
        
        # Свертка коэффициентов с сэмплами аудио отдельно по каждому каналу
        for ch in range(num_channels):
            ch_samples = audio_data[idx_matrix, ch]
            processed_audio[start_idx:end_idx, ch] = np.sum(ch_samples * sinc_coeffs, axis=1)
            
    return processed_audio

def process_drift_with_options(audio_wav_path, drift_wav_path, output_wav_path, mode='sinc_512', smoothing_window=512):
    """
    Основная функция обработки. Читает аудио и карту, сглаживает джиттер ОС,
    и применяет выбранный алгоритм интерполяции (cubic или sinc_XX).
    """
    print(f"=== Audio Drift Processor | Режим: {mode} ===")
    
    # 1. Чтение исходного стерео-аудио (Экспортировано кнопкой 1 из JSFX)
    audio_data, sample_rate = sf.read(audio_wav_path, dtype='float32')
    if audio_data.ndim == 1:
        audio_data = audio_data.reshape(-1, 1)
    print(f"Загружено аудио: {len(audio_data)} сэмплов, каналов: {audio_data.shape[1]}")
    
    # 2. Чтение моно-файла карты дрейфа (Экспортировано кнопкой 2 из JSFX)
    drift_data, _ = sf.read(drift_wav_path, dtype='float32')
    delta_times = drift_data.astype(np.float64)
    print(f"Загружена карта дрейфа: {len(delta_times)} шагов.")
    
    # Синхронизация длин массивов
    min_len = min(len(audio_data), len(delta_times))
    audio_data = audio_data[:min_len]
    delta_times = delta_times[:min_len]
    
    # Защита от нулевых таймингов
    ideal_step = 1.0 / sample_rate
    delta_times[delta_times <= 0] = ideal_step
    
    # 3. Фильтрация джиттера таймеров операционной системы (Скользящее среднее)
    print(f"Сглаживание цифрового шума времени (окно: {smoothing_window} сэмплов)...")
    kernel = np.ones(smoothing_window) / smoothing_window
    smoothed_deltas = np.convolve(np.pad(delta_times, smoothing_window//2, mode='edge'), kernel, mode='valid')
    smoothed_deltas = smoothed_deltas[:min_len]
    
    # Коррекция баланса общей длины
    smoothed_deltas *= (np.sum(delta_times) / np.sum(smoothed_deltas))
    
    # Строим реальную и идеальную временные оси
    real_time_axis = np.cumsum(smoothed_deltas)
    ideal_time_axis = np.arange(min_len, dtype=np.float64) * ideal_step
    
    # Ограничиваем сетку во избежание экстраполяции на концах
    ideal_time_axis = ideal_time_axis[ideal_time_axis <= real_time_axis[-1]]
    output_len = len(ideal_time_axis)
    
    # 4. Выбор и выполнение алгоритма интерполяции
    if mode == 'cubic':
        print("Выполняется кубический ресэмплинг кривыми Эрмита/Catmull-Rom...")
        processed_audio = np.zeros((output_len, audio_data.shape[1]), dtype=np.float32)
        for ch in range(audio_data.shape[1]):
            spline = interpolate.CubicSpline(real_time_axis, audio_data[:, ch])
            processed_audio[:, ch] = spline(ideal_time_axis)
            
    elif mode.startswith('sinc_'):
        # Парсим количество точек из названия режима
        taps = int(mode.split('_')[1])
        print(f"Выполняется многоточечный оконный Sinc-ресэмплинг ({taps} pt)...")
        processed_audio = windowed_sinc_interp_nonuniform(real_time_axis, audio_data, ideal_time_axis, num_taps=taps)
        
    else:
        raise ValueError(f"Неизвестный режим интерполяции: {mode}")
        
    # 5. Экспорт финального мастер-файла 32-bit Float
    sf.write(output_wav_path, processed_audio, sample_rate, subtype='FLOAT')
    print(f"=== Успех! Файл сохранен: {output_wav_path} ===\n")

# --- ИНСТРУКЦИЯ И НАСТРОЙКА ЗАПУСКА ---
if __name__ == "__main__":
    # Укажите пути к вашим файлам из REAPER
    AUDIO_FILE = "record_1.L_left_0_stereo.wav" 
    DRIFT_FILE = "01-Guitar-261030_1500-jsfx-01.wav"   
    OUTPUT_FILE = "python_master_result_2.wav"
    
    # ДОСТУПНЫЕ РЕЖИМЫ (МЕТОДЫ) ДЛЯ ВЫБОРА:
    # 'cubic'   - Стандартный кубический сплайн
    # 'sinc_16'  - Быстрый sinc фильтр (16 точек)
    # 'sinc_64'  - Среднее качество (64 точки)
    # 'sinc_192' - Высокое качество (192 точки)
    # 'sinc_384' - Сверхвысокое качество (384 точки)
    # 'sinc_512' - Студийный медленный sinc (512 точек)
    # 'sinc_768' - Максимальное качество, очень медленный (768 точек)
    
    SELECTED_MODE = 'sinc_512' # Выберите нужный режим здесь
    
    process_drift_with_options(
        audio_wav_path=AUDIO_FILE,
        drift_wav_path=DRIFT_FILE,
        output_wav_path=OUTPUT_FILE,
        mode=SELECTED_MODE,
        smoothing_window=512 # Окно фильтрации джиттера ОС
    )
