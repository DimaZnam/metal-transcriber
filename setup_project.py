# setup_project.py
"""
Bootstrap-скрипт для проекта Metal Transcriber (PySide6).
Создаёт структуру папок и наполняет все файлы кодом.
Запуск:  python setup_project.py
"""
from pathlib import Path

PROJECT_NAME = "metal-transcriber"

FILES = {
    # ---------------------------------------------------------------- requirements
    "requirements.txt": '''miniaudio>=1.61
demucs-onnx>=0.3.3
basic-pitch>=0.3.0
librosa>=0.10.0
soundfile>=0.12.0
pyguitarpro>=0.9.0
music21>=9.0
PySide6>=6.6.0
pyqtgraph>=0.13.0
gingo>=1.0.0
numpy>=1.24.0
scipy>=1.10.0
''',

    # ---------------------------------------------------------------- main.py
    "main.py": '''import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
''',

    # ---------------------------------------------------------------- core/
    "core/__init__.py": "",

    "core/audio_loader.py": '''import miniaudio
import numpy as np


def load_audio_native(path: str, target_sr: int = 22050) -> tuple[np.ndarray, int]:
    """
    Декодирует аудио (MP3, FLAC, OGG, WAV) через miniaudio.
    FFmpeg не требуется.
    """
    decoded = miniaudio.decode_file(
        path,
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
        sample_rate=target_sr,
    )
    audio = np.frombuffer(decoded.samples, dtype=np.float32)
    return audio, target_sr
''',

    "core/transcriber.py": '''from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np
import tempfile
import os


NoteEvent = Tuple[float, float, int]


class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sr: int) -> List[NoteEvent]:
        """Возвращает список (start_time, end_time, midi_note)."""
        pass


class DemucsOnnxSeparator:
    """Разделение инструментов без PyTorch и FFmpeg."""
    def __init__(self):
        from demucs_onnx import separate_stem
        self._separate_stem = separate_stem

    def separate_guitar(self, audio: np.ndarray, sr: int) -> np.ndarray:
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sr)
            tmp = f.name
        try:
            guitar = self._separate_stem(tmp, "guitar", model="htdemucs_6s")
            return np.mean(guitar, axis=0) if guitar.ndim > 1 else guitar
        finally:
            os.unlink(tmp)


class BasicPitchTranscriber(BaseTranscriber):
    """Транскрипция через Spotify Basic Pitch (на Windows — ONNX runtime)."""
    def transcribe(self, audio: np.ndarray, sr: int) -> List[NoteEvent]:
        import soundfile as sf
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, sr)
            tmp = f.name
        try:
            _, _, events = predict(tmp, model_or_model_path=ICASSP_2022_MODEL_PATH)
            return [(s, e, int(p)) for s, e, p, *_ in events]
        finally:
            os.unlink(tmp)
''',

    "core/arranger.py": '''from typing import List, Tuple, Dict, Any
import math


NoteEvent = Tuple[float, float, int]
TabEvent = Tuple[float, float, int, int]

STANDARD_TUNING = [40, 45, 50, 55, 59, 64]  # E2 A2 D3 G3 B3 E4
MAX_FRET = 24
MAX_STRETCH = 5


def _playable_configs(midis: List[int]) -> List[Tuple[Tuple[int, int], ...]]:
    """Все играбельные комбинации (string_idx, fret) для одновременных нот."""
    per_note = []
    for midi in midis:
        opts = []
        for s_idx, open_midi in enumerate(STANDARD_TUNING):
            fret = midi - open_midi
            if 0 <= fret <= MAX_FRET:
                opts.append((s_idx, fret))
        if not opts:
            return []
        per_note.append(opts)

    configs = []

    def backtrack(i: int, used_strings: set, current: list):
        if i == len(per_note):
            frets = [f for _, f in current]
            if max(frets) - min(frets) <= MAX_STRETCH:
                configs.append(tuple(current))
            return
        for s, f in per_note[i]:
            if s in used_strings:
                continue
            used_strings.add(s)
            current.append((s, f))
            backtrack(i + 1, used_strings, current)
            current.pop()
            used_strings.remove(s)

    backtrack(0, set(), [])
    return configs


def _transition_cost(prev, curr) -> float:
    prev_frets = [f for _, f in prev]
    curr_frets = [f for _, f in curr]
    center_prev = sum(prev_frets) / len(prev_frets)
    center_curr = sum(curr_frets) / len(curr_frets)

    move = abs(center_curr - center_prev)
    zone_penalty = 0 if move <= 4 else 3 * move
    stretch_curr = max(curr_frets) - min(curr_frets)
    stretch_penalty = max(0, stretch_curr - 3) * 0.5
    open_bonus = -0.2 * sum(1 for f in curr_frets if f == 0)

    return move + zone_penalty + stretch_penalty + open_bonus


def arrange_with_dp(notes: List[NoteEvent]) -> List[TabEvent]:
    """Раскладка нот на гриф через Viterbi-подобное динамическое программирование."""
    if not notes:
        return []

    groups: Dict[float, List[int]] = {}
    for start, _end, midi in notes:
        groups.setdefault(round(start, 3), []).append(midi)

    sorted_times = sorted(groups.keys())
    group_midis = [groups[t] for t in sorted_times]

    all_configs = []
    for midis in group_midis:
        configs = _playable_configs(midis)
        all_configs.append(configs)

    dp: List[Dict[Any, float]] = []
    parent: List[Dict[Any, Any]] = []

    first = all_configs[0]
    dp.append({cfg: 0.0 for cfg in first})
    parent.append({cfg: None for cfg in first})

    for i in range(1, len(all_configs)):
        curr_configs = all_configs[i]
        prev_configs = all_configs[i - 1]
        if not curr_configs or not prev_configs:
            dp.append({cfg: 0.0 for cfg in curr_configs})
            parent.append({cfg: None for cfg in curr_configs})
            continue

        curr_dp = {}
        curr_parent = {}
        for cfg_curr in curr_configs:
            best_cost = math.inf
            best_prev = None
            for cfg_prev, cost_prev in dp[i - 1].items():
                total = cost_prev + _transition_cost(cfg_prev, cfg_curr)
                if total < best_cost:
                    best_cost = total
                    best_prev = cfg_prev
            curr_dp[cfg_curr] = best_cost
            curr_parent[cfg_curr] = best_prev
        dp.append(curr_dp)
        parent.append(curr_parent)

    if not dp[-1]:
        return []
    best_last = min(dp[-1], key=dp[-1].get)
    path = [best_last]
    for i in range(len(dp) - 1, 0, -1):
        prev = parent[i][path[-1]]
        path.append(prev)
    path.reverse()

    result: List[TabEvent] = []
    onset_to_duration = {}
    for start, end, _ in notes:
        onset_to_duration.setdefault(round(start, 3), end - start)

    for t, config in zip(sorted_times, path):
        if not config:
            continue
        dur = onset_to_duration.get(t, 0.1)
        for s_idx, fret in config:
            string_number = 6 - s_idx
            result.append((t, t + dur, string_number, fret))

    return result
''',

    "core/theory.py": '''from typing import List
from collections import Counter


class TheoryAnalyzer:
    @staticmethod
    def estimate_key(midi_notes: List[int]) -> str:
        if not midi_notes:
            return "C major"
        pcs = [n % 12 for n in midi_notes]
        tonic_pc = Counter(pcs).most_common(1)[0][0]
        note_names = ["C", "C#", "D", "D#", "E", "F",
                      "F#", "G", "G#", "A", "A#", "B"]
        tonic = note_names[tonic_pc]
        if (tonic_pc + 3) % 12 in pcs and (tonic_pc + 4) % 12 not in pcs:
            mode = "minor"
        else:
            mode = "major"
        return f"{tonic} {mode}"
''',

    "core/exporter_gp5.py": '''from typing import List
import guitarpro


TabEvent = tuple  # (start, end, string, fret)


def export_gp5(tab_events: List[TabEvent], path: str, tempo: int = 120):
    """Прямая запись в формат Guitar Pro 5 (.gp5)."""
    song = guitarpro.models.Song(tempo=tempo)
    song.title = "Transcribed by Metal Transcriber"

    track = guitarpro.models.Track(song=song, name="Guitar", channel=0)
    track.strings = [
        guitarpro.models.GuitarString(number=i, value=v)
        for i, v in enumerate([64, 59, 55, 50, 45, 40], start=1)
    ]
    song.tracks.append(track)

    measure = guitarpro.models.Measure(track=track, number=1)
    track.measures.append(measure)
    voice = guitarpro.models.Voice(measure=measure)
    measure.voices.append(voice)

    for start, end, string, fret in sorted(tab_events, key=lambda x: x[0]):
        beat = guitarpro.models.Beat(voice=voice)
        beat.start = int(start * 960)
        duration = max(1, int((end - start) * 960))
        beat.duration = guitarpro.models.Duration(value=duration)
        note = guitarpro.models.Note(beat=beat, string=string, value=fret)
        beat.notes.append(note)
        voice.beats.append(beat)

    guitarpro.write(song, path)
''',

    "core/exporter_musicxml.py": '''from typing import List
from music21 import stream, note, meter, tempo, articulations


TabEvent = tuple  # (start, end, string, fret)


def export_musicxml(tab_events: List[TabEvent], path: str, bpm: int = 120):
    """Экспорт в MusicXML — файл открывается в Guitar Pro 6/7/8."""
    score = stream.Score()
    part = stream.Part()
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=bpm))

    for start, end, string, fret in sorted(tab_events, key=lambda x: x[0]):
        n = note.Note()
        n.quarterLength = max(0.25, (end - start) * (bpm / 60.0))
        n.articulations.append(articulations.Fret(fret))
        n.articulations.append(articulations.String(string))
        part.append(n)

    score.append(part)
    score.write("musicxml", fp=path)
''',

    # ---------------------------------------------------------------- ui/
    "ui/__init__.py": "",

    "ui/waveform.py": '''import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget
import librosa


class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget = pg.PlotWidget(title="Mel-спектрограмма")
        self.plot_widget.setBackground("#1c2331")
        self.image_item = pg.ImageItem()
        self.plot_widget.addItem(self.image_item)
        layout.addWidget(self.plot_widget)

    def load_audio(self, path: str):
        y, sr = librosa.load(path, sr=22050, mono=True)
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
        S_db = librosa.power_to_db(S, ref=np.max)
        self.image_item.setImage(S_db.T, autoLevels=True)
        self.plot_widget.setLabel("left", "Mel-бин")
        self.plot_widget.setLabel("bottom", "Кадр")
''',

    "ui/fretboard.py": '''from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtSvgWidgets import QSvgWidget
from typing import List, Tuple


class FretboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.svg_widget = QSvgWidget()
        self.svg_widget.setMinimumHeight(300)
        layout.addWidget(self.svg_widget)

    def display_tab_notes(self, notes: List[Tuple[float, float, int, int]]):
        if not notes:
            self.svg_widget.load(b"")
            return
        try:
            from gingo import Fretboard, FretboardSVG, Orientation
            fb = Fretboard.violao()
            positions = [(n[3], n[2]) for n in notes]
            svg_str = FretboardSVG.positions(
                fb, positions, orient=Orientation.HORIZONTAL
            )
            self.svg_widget.load(svg_str.encode("utf-8"))
        except Exception as e:
            fallback = (
                "<svg><text x='10' y='30' fill='white'>"
                f"Ошибка грифа: {e}</text></svg>"
            )
            self.svg_widget.load(fallback.encode())

    def clear(self):
        self.svg_widget.load(b"")
''',

    "ui/main_window.py": '''import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QComboBox, QLabel, QProgressBar, QSplitter,
    QListWidget, QCheckBox, QGroupBox, QTabWidget, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal

from core.transcriber import DemucsOnnxSeparator, BasicPitchTranscriber
from core.arranger import arrange_with_dp
from core.theory import TheoryAnalyzer
from core.exporter_gp5 import export_gp5
from core.exporter_musicxml import export_musicxml
from ui.waveform import WaveformWidget
from ui.fretboard import FretboardWidget


GUITAR_PRO_QSS = """
QMainWindow, QWidget {
    background-color: #1c2331; color: #e8e8e8;
    font-family: "Segoe UI", "SF Pro Display", sans-serif; font-size: 13px;
}
QPushButton {
    background-color: #569FFF; color: white; border: none;
    border-radius: 6px; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #7ab3ff; }
QPushButton:pressed { background-color: #3d7acc; }
QPushButton:disabled { background-color: #3a4458; color: #8e9bb0; }
QComboBox, QListWidget {
    background-color: #2C446A; border: 1px solid #3d5a8a;
    border-radius: 6px; padding: 6px; color: white;
}
QProgressBar {
    border: none; border-radius: 4px; background-color: #2C446A;
    text-align: center; color: white;
}
QProgressBar::chunk { background-color: #569FFF; border-radius: 4px; }
QGroupBox {
    border: 1px solid #3d5a8a; border-radius: 8px;
    margin-top: 12px; padding-top: 10px;
    font-weight: 600; color: #569FFF;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QTabWidget::pane {
    border: 1px solid #3d5a8a; border-radius: 6px;
    background-color: #1c2331;
}
QTabBar::tab { background-color: #2C446A; color: #a0b4d0; padding: 8px 16px; }
QTabBar::tab:selected { background-color: #569FFF; color: white; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1px solid #569FFF; background-color: #2C446A;
}
QCheckBox::indicator:checked { background-color: #569FFF; }
"""


class ProcessingWorker(QThread):
    finished = Signal(list, str)
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, audio_path: str):
        super().__init__()
        self.audio_path = audio_path

    def run(self):
        try:
            from core.audio_loader import load_audio_native

            self.progress.emit(10, "Декодирование (miniaudio)...")
            audio, sr = load_audio_native(self.audio_path)

            self.progress.emit(20, "Разделение на стемы (demucs-onnx)...")
            guitar = DemucsOnnxSeparator().separate_guitar(audio, sr)

            self.progress.emit(50, "Транскрипция (Basic Pitch)...")
            notes = BasicPitchTranscriber().transcribe(guitar, sr)

            self.progress.emit(80, "Раскладка на гриф (DP)...")
            tab_notes = arrange_with_dp(notes)

            key = TheoryAnalyzer.estimate_key([n[2] for n in notes])
            self.progress.emit(100, f"Готово! Тональность: {key}")
            self.finished.emit(tab_notes, key)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metal Transcriber — PySide6 Edition")
        self.resize(1500, 950)
        self.setStyleSheet(GUITAR_PRO_QSS)
        self.worker = None
        self.tab_events = []
        self.audio_path = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        self.load_btn = QPushButton("Загрузить аудио")
        self.load_btn.clicked.connect(self._load_audio)
        toolbar.addWidget(self.load_btn)

        toolbar.addWidget(QLabel("Движок:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Basic Pitch (ONNX)"])
        toolbar.addWidget(self.engine_combo)

        self.process_btn = QPushButton("Транскрибировать")
        self.process_btn.clicked.connect(self._start_processing)
        self.process_btn.setEnabled(False)
        toolbar.addWidget(self.process_btn)

        self.export_gp5_btn = QPushButton("GP5")
        self.export_gp5_btn.clicked.connect(self._export_gp5)
        self.export_gp5_btn.setEnabled(False)
        toolbar.addWidget(self.export_gp5_btn)

        self.export_xml_btn = QPushButton("MusicXML")
        self.export_xml_btn.clicked.connect(self._export_musicxml)
        self.export_xml_btn.setEnabled(False)
        toolbar.addWidget(self.export_xml_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        toolbar.addWidget(self.progress, 1)
        main_layout.addLayout(toolbar)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        stems_group = QGroupBox("Дорожки")
        stems_layout = QVBoxLayout()
        self.stem_checks = {}
        for name in ["Гитара", "Бас", "Барабаны", "Вокал"]:
            cb = QCheckBox(name)
            cb.setChecked(name == "Гитара")
            self.stem_checks[name] = cb
            stems_layout.addWidget(cb)
        stems_layout.addStretch()
        stems_group.setLayout(stems_layout)
        left_layout.addWidget(stems_group)
        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # Center
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        self.waveform = WaveformWidget()
        self.fretboard = FretboardWidget()
        self.view_tabs = QTabWidget()
        self.view_tabs.addTab(self.waveform, "Спектрограмма")
        self.view_tabs.addTab(self.fretboard, "Гриф")
        center_layout.addWidget(self.view_tabs)
        splitter.addWidget(center_widget)

        # Right
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        notes_group = QGroupBox("Извлечённые ноты")
        notes_layout = QVBoxLayout()
        self.notes_list = QListWidget()
        self.notes_list.setAlternatingRowColors(True)
        notes_layout.addWidget(self.notes_list)
        notes_group.setLayout(notes_layout)
        right_layout.addWidget(notes_group)

        self.key_label = QLabel("Тональность: —")
        self.key_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "color: #569FFF; padding: 8px;"
        )
        right_layout.addWidget(self.key_label)
        splitter.addWidget(right_panel)

        splitter.setSizes([200, 850, 350])
        main_layout.addWidget(splitter, 1)

        # Bottom
        bottom = QFrame()
        bottom.setStyleSheet(
            "background-color: #2C446A; border-radius: 6px; padding: 4px;"
        )
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.addWidget(QLabel("Файл:"))
        self.file_label = QLabel("не загружен")
        self.file_label.setStyleSheet("color: #a0b4d0;")
        bottom_layout.addWidget(self.file_label, 1)
        main_layout.addWidget(bottom)

    def _load_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Аудиофайл", "", "Аудио (*.mp3 *.wav *.flac *.ogg)"
        )
        if path:
            self.audio_path = path
            self.process_btn.setEnabled(True)
            self.waveform.load_audio(path)
            self.file_label.setText(os.path.basename(path))
            self.export_gp5_btn.setEnabled(False)
            self.export_xml_btn.setEnabled(False)

    def _start_processing(self):
        if not self.audio_path:
            return
        self.process_btn.setEnabled(False)
        self.export_gp5_btn.setEnabled(False)
        self.export_xml_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.notes_list.clear()
        self.fretboard.clear()
        self.key_label.setText("Тональность: анализ...")

        self.worker = ProcessingWorker(self.audio_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, value, message):
        self.progress.setValue(value)
        self.statusBar().showMessage(message)

    def _on_finished(self, notes, key):
        self.progress.setVisible(False)
        self.process_btn.setEnabled(True)
        self.tab_events = notes
        self.notes_list.clear()
        for start, end, string, fret in notes:
            self.notes_list.addItem(
                f"Струна {string}, лад {fret}  |  "
                f"{start:.2f}s – {end:.2f}s"
            )
        self.key_label.setText(f"Тональность: {key}")
        self.fretboard.display_tab_notes(notes)
        has_notes = bool(notes)
        self.export_gp5_btn.setEnabled(has_notes)
        self.export_xml_btn.setEnabled(has_notes)

    def _on_error(self, msg):
        self.progress.setVisible(False)
        self.process_btn.setEnabled(True)
        self.key_label.setText("Тональность: —")
        QMessageBox.critical(self, "Ошибка", msg)

    def _export_gp5(self):
        if not self.tab_events:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить GP5", "", "Guitar Pro 5 (*.gp5)"
        )
        if path:
            try:
                export_gp5(self.tab_events, path)
                QMessageBox.information(self, "Готово", f"Сохранено:\\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка экспорта", str(e))

    def _export_musicxml(self):
        if not self.tab_events:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить MusicXML",
            "", "MusicXML (*.musicxml *.xml)"
        )
        if path:
            try:
                export_musicxml(self.tab_events, path)
                QMessageBox.information(self, "Готово", f"Сохранено:\\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка экспорта", str(e))
''',
}


def main():
    root = Path.cwd() / PROJECT_NAME
    print(f"Создаю проект в: {root}\\n")
    for rel_path, content in FILES.items():
        file_path = root / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        print(f"  [+] {rel_path}")

    print(f"\\nГотово! Создано файлов: {len(FILES)}")
    print("\\nДальнейшие шаги:")
    print(f"  cd {PROJECT_NAME}")
    print("  python -m venv .venv")
    print("  .venv\\\\Scripts\\\\Activate.ps1     # PowerShell")
    print("  pip install --upgrade pip")
    print("  pip install -r requirements.txt")
    print("  python main.py")


if __name__ == "__main__":
    main()