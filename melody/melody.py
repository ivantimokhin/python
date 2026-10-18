import numpy as np
import scipy.io.wavfile as wav

# 1. Helper function to turn note names into exact frequencies (A4 = 440Hz)
def get_freq(note_str):
    if not note_str:
        return 0
    note_map = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4, 'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8, 'A':9, 'A#':10, 'Bb':10, 'B':11}
    name = note_str[:-1]
    octave = int(note_str[-1])
    semitones = note_map[name] + (octave - 4) * 12 - 9
    return 440.0 * (2.0 ** (semitones / 12.0))

# 2. Core Synthesizer function
def generate_beat(melody_note, chord_notes, duration=1.2, sample_rate=44100):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    
    # Smooth attack and decay envelope to prevent harsh digital clipping/clicking
    envelope = np.ones_like(t)
    attack_env = int(sample_rate * 0.05) # 50ms fade-in
    decay_env = int(sample_rate * 0.1)   # 100ms fade-out
    envelope[:attack_env] = np.linspace(0, 1, attack_env)
    envelope[-decay_env:] = np.linspace(1, 0, decay_env)
    
    # Generate the melody layer (sine wave, set slightly louder)
    melody_wave = 0.35 * np.sin(2 * np.pi * get_freq(melody_note) * t)
    
    # Generate the chord layer (mix of multiple notes, lower volume for background depth)
    chord_wave = np.zeros_like(t)
    if chord_notes:
        for note in chord_notes:
            chord_wave += (0.15 / len(chord_notes)) * np.sin(2 * np.pi * get_freq(note) * t)
            
    # Combine layers and apply the envelope
    combined = (melody_wave + chord_wave) * envelope
    return combined

def save_variation(filename, melody_line, chord_progression):
    audio_data = []
    for m_note, c_chord in zip(melody_line, chord_progression):
        beat_wave = generate_beat(m_note, c_chord)
        audio_data.append(beat_wave)
        
    # Stitch the beats together into one continuous track
    full_audio = np.concatenate(audio_data)
    
    # Normalize and convert to 16-bit PCM WAV format
    normalized_audio = np.int16(full_audio / np.max(np.abs(full_audio)) * 32767)
    wav.write(filename, 44100, normalized_audio)
    print(f"Generated successfully: {filename}")

# ==========================================
# CONFIGURING THE 4 SOUND EXAMPLES
# ==========================================

# The universal 4-note melody line
melody = ["E5", "F5", "G5", "E5"]

# Example 1: Standard / Diatonic (Bright & Simple)
chords_diatonic = [
    ["C3", "E3", "G3"],  # C Major
    ["G2", "B3", "D3"],  # G Major
    ["C3", "E3", "G3"],  # C Major
    ["C3", "E3", "G3"]   # C Major
]

# Example 2: Pop / Emotional (Bittersweet Minor)
chords_pop = [
    ["A2", "C3", "E3"],  # A minor
    ["D3", "F3", "A3"],  # D minor
    ["C3", "E3", "G3"],  # C Major
    ["A2", "C3", "E3"]   # A minor
]

# Example 3: Jazz (Sophisticated Extensions)
chords_jazz = [
    ["C2", "B3", "D4", "E4"],     # Cmaj9
    ["G2", "F3", "Ab3", "B3"],    # G7(b9)
    ["F2", "A3", "C4", "E4"],     # Fmaj7
    ["Bb2", "Ab3", "C4", "D4"]    # Bb7
]

# Example 4: Dramatic / Epic (Chromatic Shift)
chords_epic = [
    ["C3", "E3", "G3"],   # C Major
    ["Db3", "F3", "Ab3"], # Db Major
    ["Eb3", "G3", "Bb3"], # Eb Major
    ["C3", "E3", "G3"]    # C Major
]

# ==========================================
# EXECUTION
# ==========================================
if __name__ == "__main__":
    save_variation("1_diatonic_approach.wav", melody, chords_diatonic)
    save_variation("2_pop_emotional_approach.wav", melody, chords_pop)
    save_variation("3_jazz_approach.wav", melody, chords_jazz)
    save_variation("4_dramatic_epic_approach.wav", melody, chords_epic)
