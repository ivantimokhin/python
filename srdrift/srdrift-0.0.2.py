import numpy as np
import soundfile as sf

def windowed_sinc_interp_nonuniform(real_time, audio_data, ideal_time, num_taps=512):
    """ Высокоточный векторизованный оконный Sinc-ресэмплинг """
    num_output = len(ideal_time)
    num_channels = audio_data.shape[1]
    processed_audio = np.zeros((num_output, num_channels), dtype=np.float32)
    fs_est = 1.0 / np.mean(np.diff(real_time))
    
    chunk_size = 4096
    half_taps = num_taps // 2
    window = np.hamming(num_taps)
    
    for start_idx in range(0, num_output, chunk_size):
        end_idx = min(start_idx + chunk_size, num_output)
        t_targets = ideal_time[start_idx:end_idx]
        
        nearest_indices = np.searchsorted(real_time, t_targets)
        offsets = np.arange(-half_taps, half_taps)
        idx_matrix = nearest_indices[:, None] + offsets[None, :]
        idx_matrix = np.clip(idx_matrix, 0, len(real_time) - 1)
        
        t_samples = real_time[idx_matrix]
        t_diff = (t_targets[:, None] - t_samples) * fs_est
        sinc_coeffs = np.sinc(t_diff) * window[None, :]
        
        row_sums = np.sum(sinc_coeffs, axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        sinc_coeffs /= row_sums
        
        for ch in range(num_channels):
            ch_samples = audio_data[idx_matrix, ch]
            processed_audio[start_idx:end_idx, ch] = np.sum(ch_samples * sinc_coeffs, axis=1)
            
    return processed_audio

def process_hybrid_drift_stereo(audio_wav_path, drift_wav_path, output_wav_path, smoothing_window=3200):
    """
    Двухэтапная гибридная обработка:
    1. Идеальное восстановление аудио через Sinc 512.
    2. Применение дрейфа клока через Sinc 64 для максимального расширения стереобазы.
    """
    print("=== Старт гибридного Sinc-расширения стерео ===")
    
    # 1. Загрузка файлов
    audio_data, sample_rate = sf.read(audio_wav_path, dtype='float32')
    if audio_data.ndim == 1:
        audio_data = audio_data.reshape(-1, 1)
        
    drift_data, _ = sf.read(drift_wav_path, dtype='float32')
    delta_times = drift_data.astype(np.float64)
    
    min_len = min(len(audio_data), len(delta_times))
    audio_data = audio_data[:min_len]
    delta_times = delta_times[:min_len]
    
    ideal_step = 1.0 / sample_rate
    delta_times[delta_times <= 0] = ideal_step
    
    # 2. Сглаживание джиттера под буфер 800
    kernel = np.ones(smoothing_window) / smoothing_window
    smoothed_deltas = np.convolve(np.pad(delta_times, smoothing_window//2, mode='edge'), kernel, mode='valid')
    smoothed_deltas = smoothed_deltas[:min_len]
    smoothed_deltas *= (np.sum(delta_times) / np.sum(smoothed_deltas))
    
    # 3. ЭТАП 1: Идеальный рендеринг исходного аудио (Sinc 512)
    # Восстанавливаем оригинальный спектр и транзиенты без потерь
    print("Этап 1: Восстановление волны через Sinc 512...")
    t_ideal = np.arange(min_len, dtype=np.float64) * ideal_step
    audio_sinc512 = windowed_sinc_interp_nonuniform(t_ideal, audio_data, t_ideal, num_taps=512)
    
    # 4. ЭТАП 2: Впекание дрейфа через более грубый Sinc 64
    # Это создаст микро-асимметрию фазы каналов и сделает панораму сверхширокой
    print("Этап 2: Применение дрейфа частоты через Sinc 64 для расширения панорамы...")
    real_time_axis = np.cumsum(smoothed_deltas)
    ideal_time_axis = t_ideal[t_ideal <= real_time_axis[-1]]
    
    final_audio = windowed_sinc_interp_nonuniform(real_time_axis, audio_sinc512, ideal_time_axis, num_taps=64)
    
    # 5. Сохранение результата
    sf.write(output_wav_path, final_audio, sample_rate, subtype='FLOAT')
    print(f"=== Успех! Сверхширокий файл сохранен: {output_wav_path} ===")

if __name__ == "__main__":
    AUDIO_FILE = "01-Guitar-261030_1500-jsfx.wav" 
    DRIFT_FILE = "01-Guitar-261030_1500-jsfx-01.wav"   
    OUTPUT_FILE = "python_master_result_5.wav"
    
    # Запускаем с окном 3200 под ваш буфер 800
    process_hybrid_drift_stereo(AUDIO_FILE, DRIFT_FILE, OUTPUT_FILE, smoothing_window=3200)
