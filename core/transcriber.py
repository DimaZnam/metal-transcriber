# core/transcriber.py
from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np
import tempfile
import os

NoteEvent = Tuple[float, float, int]

def check_models_available() -> Tuple[bool, str]:
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_models = os.path.join(project_dir, "models")
    
    if os.path.exists(local_models) and os.listdir(local_models):
        return True, ""
        
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub")
    if not os.path.exists(hf_cache):
        return False, "Кэш HuggingFace не найден. Транскрипция недоступна без интернета."
    
    dirs = os.listdir(hf_cache)
    demucs_ok = any("demucs" in d.lower() or "stemsplit" in d.lower() for d in dirs)
    muscriptor_ok = any("muscriptor" in d.lower() for d in dirs)
    
    if demucs_ok and muscriptor_ok:
        return True, ""
    elif not demucs_ok and not muscriptor_ok:
        return False, "Модели Demucs и MuScriptor не найдены."
    elif not demucs_ok:
        return False, "Модель Demucs не найдена."
    else:
        return False, "Модель MuScriptor не найдена."

class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sr: int, instrument: str) -> List[NoteEvent]:
        pass

class DemucsOnnxSeparator:
    def __init__(self):
        from demucs_onnx import separate_stem, separate
        self._separate_stem = separate_stem
        self._separate = separate

    def separate_stems(self, audio_path: str) -> dict:
        return self._separate(audio_path, model="htdemucs_ft")

    def separate_guitar(self, audio: np.ndarray, sr: int) -> np.ndarray:
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sr)
            tmp = f.name
        try:
            guitar = self._separate_stem(tmp, "guitar")
            return np.mean(guitar, axis=0) if guitar.ndim > 1 else guitar
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

def clean_notes(notes: List[NoteEvent], min_duration: float = 0.05) -> List[NoteEvent]:
    if not notes:
        return []
    
    filtered = [n for n in notes if (n[1] - n[0]) >= min_duration]
    filtered.sort(key=lambda x: x[0])
    
    merged = []
    for note in filtered:
        start, end, pitch = note
        if not merged:
            merged.append(note)
            continue
            
        prev = merged[-1]
        if pitch == prev[2] and (start - prev[1]) < 0.03:
            merged[-1] = (prev[0], end, pitch)
        elif pitch == prev[2] and abs(start - prev[0]) < 0.05:
            merged[-1] = (prev[0], max(prev[1], end), pitch)
        else:
            merged.append(note)
            
    return merged

class MuScriptorTranscriber(BaseTranscriber):
    def __init__(self, model_size: str = "small"):
        try:
            from muscriptor import TranscriptionModel
            from muscriptor.events import NoteStartEvent, NoteEndEvent, ProgressEvent
        except ImportError as e:
            raise RuntimeError("MuScriptor не установлен.") from e
        self.model = TranscriptionModel.load_model(model_size)
        self._Start = NoteStartEvent
        self._End = NoteEndEvent

    def transcribe(self, audio: np.ndarray, sr: int, instrument: str = "distorted_electric_guitar") -> List[NoteEvent]:
        if audio is None or len(audio) == 0:
            return []

        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            data = audio.T if audio.ndim > 1 else audio
            sf.write(f.name, data, sr)
            tmp_wav = f.name

        try:
            notes = []
            active = {}
            for event in self.model.transcribe(tmp_wav, instruments=[instrument]):
                if isinstance(event, self._Start):
                    active[event.index] = event
                elif isinstance(event, self._End):
                    start = active.pop(event.start_event.index, None)
                    if start is not None:
                        notes.append((start.start_time, event.end_time, start.pitch))
                        
            notes.sort(key=lambda x: x[0])
            return clean_notes(notes)
        finally:
            if os.path.exists(tmp_wav):
                os.unlink(tmp_wav)