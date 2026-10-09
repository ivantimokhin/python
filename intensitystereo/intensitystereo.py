import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, filtfilt

def butter_lowpass_highpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b_low, a_low = butter(order, normal_cutoff, btype='low', analog=False)
    b_high, a_high = butter(order, normal_cutoff, btype='high', analog=False)
    return b_low, a_low, b_high, a_high

def emulate_intensity_stereo(input_path, output_path, crossover_freq=2000):
    # 1. Load the WAV file
    fs, data = wavfile.read(input_path)
    
    # Ensure it is a stereo file
    if len(data.shape) != 2 or data.shape[1] != 2:
        raise ValueError("Input file must be a stereo WAV file.")
        
    # Convert integer formats to float32 for processing
    original_dtype = data.dtype
    if original_dtype != np.float32:
        data = data.astype(np.float32) / np.iinfo(original_dtype).max

    left = data[:, 0]
    right = data[:, 1]
    
    # 2. Separate low and high frequencies using a crossover filter
    b_low, a_low, b_high, a_high = butter_lowpass_highpass(crossover_freq, fs)
    
    left_low = filtfilt(b_low, a_low, left)
    right_low = filtfilt(b_low, a_low, right)
    
    left_high = filtfilt(b_high, a_high, left)
    right_high = filtfilt(b_high, a_high, right)
    
    # 3. Emulate Intensity Stereo on the High Frequencies
    # Sum the high frequencies to a single Mono carrier channel
    mono_high = (left_high + right_high) / 2.0
    
    # Calculate the localized intensity envelopes (L/R RMS or Absolute Energy)
    # Using small windows to track dynamic panning over time
    window_size = int(fs * 0.02) # 20ms windows (typical for audio frames)
    num_samples = len(mono_high)
    
    is_left_high = np.zeros_like(mono_high)
    is_right_high = np.zeros_like(mono_high)
    
    for i in range(0, num_samples, window_size):
        end = min(i + window_size, num_samples)
        
        # Calculate RMS energy of original high channels in this window
        rms_l = np.sqrt(np.mean(left_high[i:end]**2)) + 1e-10
        rms_r = np.sqrt(np.mean(right_high[i:end]**2)) + 1e-10
        rms_m = np.sqrt(np.mean(mono_high[i:end]**2)) + 1e-10
        
        # Determine the scaling factor to preserve the original channel intensities
        scale_l = rms_l / rms_m
        scale_r = rms_r / rms_m
        
        # Apply scaling factors to the mono high channel
        is_left_high[i:end] = mono_high[i:end] * scale_l
        is_right_high[i:end] = mono_high[i:end] * scale_r

    # 4. Recombine Low and Intensity-Stereo High components
    output_left = left_low + is_left_high
    output_right = right_low + is_right_high
    
    # Stack channels back together
    output_data = np.vstack((output_left, output_right)).T
    
    # 5. Convert back to original format and save
    if original_dtype != np.float32:
        output_data = np.clip(output_data, -1.0, 1.0)
        output_data = (output_data * np.iinfo(original_dtype).max).astype(original_dtype)
        
    wavfile.write(output_path, fs, output_data)
    print(f"Successfully generated Intensity Stereo emulated file: {output_path}")

# Example usage:
emulate_intensity_stereo("output_fixed.wav", "untitled_002_is.wav", crossover_freq=2590)
