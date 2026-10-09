import numpy as np
import soundfile as sf
from scipy.signal import hilbert, butter, filtfilt
from scipy.interpolate import CubicSpline

def find_dominant_pilot_frequency(signal, fs, min_freq=30.0, max_freq=150.0):
    """
    Автоматически находит самую громкую частоту (пилот-тон) в заданном диапазоне.
    """
    print(f"[*] Сканирование спектра в диапазоне {min_freq} - {max_freq} Гц для поиска опорного тона...")
    
    # Вычисляем FFT сигнала
    n = len(signal)
    fft_vals = np.fft.rfft(signal)
    fft_freqs = np.fft.rfftfreq(n, d=1.0/fs)
    
    # Берем модуль амплитуд
    fft_amps = np.abs(fft_vals)
    
    # Создаем маску для интересующего нас диапазона частот
    mask = (fft_freqs >= min_freq) & (fft_freqs <= max_freq)
    
    if not np.any(mask):
        print(f"[!] В диапазоне {min_freq}-{max_freq} Гц ничего не найдено. Возврат к дефолтным 50 Гц.")
        return 50.0
        
    # Находим индекс максимальной амплитуды внутри маски
    idx_in_mask = np.argmax(fft_amps[mask])
    dominant_freq = fft_freqs[mask][idx_in_mask]
    
    print(f"[+] Автоопределение: Найден сильнейший пилот-тон на частоте {dominant_freq:.2f} Гц")
    return dominant_freq

def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = filtfilt(b, a, data)
    return y

def fix_wow_and_flutter(input_file, output_file, target_freq=None, search_width=2.0, min_search_freq=30.0, max_search_freq=150.0):
    """
    Корректирует 'плавающий' звук с автоматическим поиском или ручным указанием опорной частоты.
    """
    # 1. Загрузка файла
    data, fs = sf.read(input_file)
    
    if len(data.shape) > 1:
        signal = data[:, 0]
        stereo = True
        num_channels = data.shape[1]
    else:
        signal = data
        stereo = False
        num_channels = 1
        
    num_samples = len(signal)
    ideal_time = np.linspace(0, num_samples / fs, num_samples, endpoint=False)
    
    # АВТОПОИСК: Если target_freq не передан (равен None), скрипт найдет частоту сам
    if target_freq is None:
        target_freq = find_dominant_pilot_frequency(signal, fs, min_freq=min_search_freq, max_freq=max_search_freq)
    
    print(f"[*] Выделение опорной частоты {target_freq:.2f} Гц...")
    # 2. Фильтрация зоны пилот-тона
    pilot_zone = butter_bandpass_filter(signal, target_freq - search_width, target_freq + search_width, fs, order=4)
    
    print("[*] Анализ мгновенной частоты...")
    # 3. Преобразование Гильберта
    analytic_signal = hilbert(pilot_zone)
    
    phases = np.angle(analytic_signal)
    if np.any(np.isnan(phases)):
        phases = np.nan_to_num(phases, nan=0.0)
        
    instantaneous_phase = np.unwrap(phases)
    
    # Расчет мгновенной частоты
    instantaneous_frequency = np.diff(instantaneous_phase) / (2.0 * np.pi) * fs
    instantaneous_frequency = np.append(instantaneous_frequency, instantaneous_frequency[-1])
    
    # Сглаживание частоты низкочастотным фильтром
    b_low, a_low = butter(2, 2.0 / (0.5 * fs), btype='low')
    smooth_freq = filtfilt(b_low, a_low, instantaneous_frequency)
    
    # Ограничиваем частоту физическими рамками фильтра
    min_allowable_freq = max(target_freq - search_width, 1.0)
    max_allowable_freq = target_freq + search_width
    smooth_freq = np.clip(smooth_freq, min_allowable_freq, max_allowable_freq)

    print("[*] Построение карты временных искажений...")
    # 4. Расчет относительной скорости
    relative_speed = smooth_freq / target_freq
    
    relative_speed[~np.isfinite(relative_speed)] = 1.0
    relative_speed[relative_speed <= 0] = 1.0
    
    dt = 1.0 / fs
    real_time = np.cumsum(dt / relative_speed)
    
    t_start = real_time[0]
    real_time = real_time - t_start
    
    # Гарантируем строгое монотонное возрастание для CubicSpline
    for i in range(1, len(real_time)):
        if real_time[i] <= real_time[i-1]:
            real_time[i] = real_time[i-1] + 1e-10

    if not np.all(np.isfinite(real_time)):
        raise ValueError("Ошибка: Массив времени всё еще содержит NaN/Inf.")

    print("[*] Ресэмплинг и выравнивание аудио...")
    # 5. Интерполяция
    if stereo:
        corrected_data = np.zeros_like(data)
        for ch in range(num_channels):
            cs = CubicSpline(real_time, data[:, ch])
            corrected_data[:, ch] = cs(ideal_time)
    else:
        cs = CubicSpline(real_time, signal)
        corrected_data = cs(ideal_time)
        
    # 6. Сохранение результата
    sf.write(output_file, corrected_data, fs)
    print(f"[+] Успех! Стабилизированный файл сохранен как: {output_file}\n")


# Вариант 1: Полный автомат (ищет самую громкую частоту от 30 до 150 Гц)
fix_wow_and_flutter("output_stereo.wav", "output_fixed.wav", target_freq=None, search_width=2.0)
        
# Вариант 2: Если вы знаете, что искать нужно в районе гитары/баса (например, от 70 до 100 Гц),
# можно сузить рамки поиска, чтобы музыка не сбивала алгоритм:
# fix_wow_and_flutter("input.wav", "output_fixed.wav", target_freq=None, search_width=2.0, min_search_freq=70.0, max_search_freq=100.0)
        

