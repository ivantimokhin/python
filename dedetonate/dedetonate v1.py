import numpy as np
import soundfile as sf
from scipy.signal import hilbert, butter, filtfilt
from scipy.interpolate import CubicSpline


# Ресэмплинг как альтернатива: Если природа джиттера — это просто случайный белый шум клока АЦП, то лучшим «лечением» в Python будет применение высококачественного низкочастотного фильтра (LPF) или апсэмплинг с последующим даунсэмплингом через scipy.signal.resample, что сгладит высокочастотный фазовый шум.


# • Вы боретесь с конкретным искажением в файле (например, звук «плавает» по скорости, как на старой кассете)?
# • Был ли в аудио записан постоянный тестовый сигнал, по которому можно вычислить ошибку тайминга?


# Если звук в файле «плавает» (то есть плавно меняется скорость и тональность, как на старой аудиокассете или виниле), этот эффект называется детонацией, вау-энд-флаттером (wow and flutter) или низкочастотным джиттером.


# В этом случае временная ошибка клока исчисляется уже не пикосекундами, а миллисекундами, и её можно эффективно исправить, если в аудиозаписи есть фрагменты с постоянной, заведомо известной частотой


# На будущее — если вы столкнетесь с другими записями, где этот же скрипт покажет себя чуть хуже, вот три быстрых совета, как довести результат до идеала:
# • Если звук плавает слишком сильно (амплитуда «качелей» огромная): увеличьте параметр search_width с 2.0 до 4.0 или 5.0 Гц, чтобы алгоритм не терял пилот-тон при резких скачках скорости.
# • Если запись из США/Японии: сетевой гул там работает на частоте 60 Гц вместо европейских 50 Гц. В таком случае просто поменяйте параметр target_freq=60.0.
# • Если в звуке появились «роботизированные» артефакты: это значит, что в полосу фильтра попал полезный сигнал (например, низкий бас или суб-басовая бочка). Чтобы этого избежать, можно снизить частоту среза сглаживающего фильтра (в строке butter(2, 2.0 / ...), заменив 2.0 на 0.5 или 1.0), чтобы алгоритм реагировал только на плавные изменения скорости.


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

def fix_wow_and_flutter(input_file, output_file, target_freq=50.0, search_width=2.0):
    """
    Корректирует 'плавающий' звук с полной защитой от NaN и Inf в тихих местах.
    """
    # 1. Загрузка файла
    data, fs = sf.read(input_file)
    
    if len(data.shape) > 1:
        signal = data[:, 0]
        stereo = True
        num_channels = data.shape[1]  # Исправлено: берем второй элемент shape для каналов
    else:
        signal = data
        stereo = False
        num_channels = 1
        
    num_samples = len(signal)
    ideal_time = np.linspace(0, num_samples / fs, num_samples, endpoint=False)
    
    print(f"[*] Выделение опорной частоты {target_freq} Гц...")
    # 2. Фильтрация зоны пилот-тона
    pilot_zone = butter_bandpass_filter(signal, target_freq - search_width, target_freq + search_width, fs, order=4)
    
    print("[*] Анализ мгновенной частоты...")
    # 3. Преобразование Гильберта
    analytic_signal = hilbert(pilot_zone)
    
    # Получаем фазу и обрабатываем возможные NaN/замирания
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
    
    # ЖЕСТКАЯ ЗАЩИТА: Заменяем любые NaN или бесконечности на стабильную скорость (1.0)
    # Это спасет скрипт, если в файле была абсолютная тишина
    relative_speed[~np.isfinite(relative_speed)] = 1.0
    relative_speed[relative_speed <= 0] = 1.0
    
    dt = 1.0 / fs
    # Расчет кумулятивного времени (интеграл скорости)
    real_time = np.cumsum(dt / relative_speed)
    
    # Сдвиг шкалы, чтобы отсчет шел от 0.0 секунд
    t_start = real_time[0]
    real_time = real_time - t_start
    
    # Гарантируем строгое монотонное возрастание для CubicSpline
    for i in range(1, len(real_time)):
        if real_time[i] <= real_time[i-1]:
            real_time[i] = real_time[i-1] + 1e-10

    # Проверка на корректность данных
    if not np.all(np.isfinite(real_time)):
        raise ValueError("Ошибка: Массив времени всё еще содержит NaN/Inf после всех фильтраций.")

    print("[*] Ресэмплинг и выравнивание аудио...")
    # 5. Интерполяция (перенос амплитуд на идеальную сетку)
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
    print(f"[+] Успех! Стабилизированный файл сохранен как: {output_file}")



fix_wow_and_flutter("input.wav", "output_fixed.wav", target_freq=82.41, search_width=2.0)
