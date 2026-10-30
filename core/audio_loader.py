# core/audio_loader.py
import miniaudio
import numpy as np
import librosa
import soundfile as sf

def load_audio_native(path: str, target_sr: int = 22050) -> tuple[np.ndarray, int]:
    try:
        decoded = miniaudio.decode_file(path, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1, sample_rate=target_sr)
        return np.frombuffer(decoded.samples, dtype=np.float32), target_sr
    except Exception:
        audio, sr = librosa.load(path, sr=target_sr, mono=True)
        return audio, sr

def cut_audio_segment(input_path: str, output_path: str, start_sec: float, end_sec: float):
    """Вырезает фрагмент аудио и сохраняет как WAV."""
    y, sr = librosa.load(input_path, sr=44100, mono=False)
    start_frame = int(start_sec * sr)
    end_frame = int(end_sec * sr)
    
    if y.ndim == 2:
        segment = y[:, start_frame:end_frame].T
    else:
        segment = y[start_frame:end_frame]
        
    sf.write(output_path, segment, sr)