# core/audio_processor.py
import librosa
import soundfile as sf
import numpy as np


class AudioProcessor:
    @staticmethod
    def process(
        input_path: str,
        output_path: str,
        rate: float = 1.0,
        semitones: float = 0.0,
    ) -> str:
        # Загружаем аудио с исходной частотой дискретизации, моно
        y, sr = librosa.load(input_path, sr=None, mono=True)

        # 1. Сначала изменяем тон (если нужно)
        if semitones != 0.0:
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=semitones)

        # 2. Затем изменяем скорость (если нужно)
        # rate=0.5 означает "играть в два раза медленнее"
        if rate != 1.0:
            y = librosa.effects.time_stretch(y, rate=rate)

        sf.write(output_path, y, sr)
        return output_path