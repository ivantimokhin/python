import argparse
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import hilbert

def rotate_phase(signal, degrees):
    """
    Rotates the phase of the audio signal by a specified number of degrees
    using the Hilbert Transform.
    """
    # Convert degrees to radians
    radians = np.deg2rad(degrees)
    
    # Compute the analytical signal using the Hilbert transform
    # This gives us: analytical_signal = signal + i * hilbert(signal)
    analytical = hilbert(signal, axis=0)
    
    # Apply phase rotation by multiplying by e^(i * radians)
    rotated_analytical = analytical * np.exp(1j * radians)
    
    # The real part of the rotated analytical signal is our phase-shifted audio
    return np.real(rotated_analytical)

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Rotate the phase of a WAV audio file by a given angle in degrees."
    )
    parser.add_argument("filename", type=str, help="Path to the input .wav file")
    parser.add_argument("phase", type=float, help="Phase rotation angle in degrees (e.g., 90, 180, -90)")
    
    args = parser.parse_args()
    
    # Verify file existence
    if not os.path.exists(args.filename):
        print(f"Error: The file '{args.filename}' does not exist.")
        return

    print(f"Reading {args.filename}...")
    # Read the WAV file
    samplerate, data = wavfile.read(args.filename)
    
    # Remember original data type to restore it later
    original_dtype = data.dtype
    
    # Convert integer formats to float for processing (-1.0 to 1.0)
    is_integer_type = np.issubdtype(original_dtype, np.integer)
    if is_integer_type:
        # Determine maximum value for normalization based on bit depth
        if original_dtype == np.int16:
            max_val = 32768.0
        elif original_dtype == np.int32:
            max_val = 2147483648.0
        elif original_dtype == np.uint8:
            # uint8 is unsigned, mid-point is 128
            data = (data.astype(np.float32) - 128.0) / 128.0
            max_val = 1.0
        else:
            max_val = float(np.iinfo(original_dtype).max)
        
        if original_dtype != np.uint8:
            data = data.astype(np.float32) / max_val
            
    print(f"Rotating phase by {args.phase} degrees...")
    # Perform phase rotation
    processed_data = rotate_phase(data, args.phase)
    
    # Reconvert back to the original format if it was an integer
    if is_integer_type:
        if original_dtype == np.uint8:
            processed_data = np.clip((processed_data * 128.0) + 128.0, 0, 255).astype(np.uint8)
        else:
            processed_data = np.clip(processed_data * max_val, -max_val, max_val - 1).astype(original_dtype)
    else:
        processed_data = processed_data.astype(original_dtype)
        
    # Generate output file name
    base, ext = os.path.splitext(args.filename)
    output_filename = f"{base}_rotated_{args.phase}{ext}"
    
    print(f"Saving output to {output_filename}...")
    # Write the modified data to a new WAV file
    wavfile.write(output_filename, samplerate, processed_data)
    print("Done!")

if __name__ == "__main__":
    main()
