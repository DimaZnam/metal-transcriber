# ui/main_window.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import tempfile
from typing import Dict, List

import numpy as np
import soundfile as sf
import psutil
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, 
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, 
    QSlider, QSplitter, QVBoxLayout, QWidget, QAbstractItemView
)
from PySide6.QtGui import QColor

from core.audio_engine import MultiTrackMixer
from core.audio_loader import cut_audio_segment, load_audio_native
from core.audio_processor import AudioProcessor
from core.arranger import arrange_with_dp
from core.exporter_gp5 import export_gp5
from core.exporter_musicxml import export_musicxml
from core.synth import play_midi_note
from core.theory import (
    CHORD_INTERVALS, SCALES, SHARP_NAMES, FLAT_NAMES, TheoryAnalyzer,
)
from core.transcriber import DemucsOnnxSeparator, MuScriptorTranscriber, check_models_available, clean_notes

from ui.chord_diagram import ChordDiagramWidget
from ui.scale_diagram import ScaleDiagramWidget
from ui.circle_of_fifths import CircleOfFifthsWindow
from ui.fretboard import FretboardWidget
from ui.fretboard_state import FretboardState, TUNINGS
from ui.timeline import TimelineWidget
from ui.track_lane import TrackLaneWidget
from ui.vu_meter import VUMeter

NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

STEM_COLORS = {
    "master": "#569FFF",
    "guitar": "#FF9800",
    "bass": "#9C27B0",
    "drums": "#4CAF50",
    "piano": "#F44336",
    "vocals": "#00BCD4",
    "other": "#9E9E9E"
}

GUITAR_PRO_QSS = """
QMainWindow, QWidget { background-color: #1c2331; color: #e8e8e8; font-family: "Segoe UI", sans-serif; font-size: 13px; }
QPushButton { background-color: #569FFF; color: white; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background-color: #7ab3ff; }
QPushButton:disabled { background-color: #3a4458; color: #8e9bb0; }
QPushButton:checked { background-color: #2C446A; border: 1px solid #569FFF; color: #569FFF; }
QComboBox, QListWidget { background-color: #2C446A; border: 1px solid #3d5a8a; border-radius: 6px; padding: 6px; color: white; }
QListWidget::item:selected { background-color: #569FFF; color: white; }
QProgressBar { border: none; border-radius: 4px; background-color: #2C446A; text-align: center; color: white; }
QProgressBar::chunk { background-color: #569FFF; border-radius: 4px; }
QGroupBox { border: 1px solid #3d5a8a; border-radius: 8px; margin-top: 12px; padding-top: 10px; font-weight: 600; color: #569FFF; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QSlider::groove:horizontal { height: 4px; background: #3d5a8a; border-radius: 2px; }
QSlider::handle:horizontal { background: #569FFF; width: 14px; margin: -6px 0; border-radius: 7px; }
QSplitter::handle { background-color: #3d5a8a; }
QScrollArea { border: none; background: transparent; }
QSplitter::handle:vertical { height: 4px; background: #3d5a8a; }

QSlider::groove:vertical { width: 4px; background: #3d5a8a; border-radius: 2px; }
QSlider::handle:vertical { background: #569FFF; height: 14px; margin: 0 -6px; border-radius: 7px; }

QPushButton#playerBtn {
    background-color: #2C446A;
    border: 1px solid #3d5a8a;
    border-radius: 4px;
    padding: 0px;
    font-size: 16px;
}
QPushButton#playerBtn:hover {
    background-color: #3d5a8a;
}
"""

ORDERED_CHORD_TYPES = [
    "5", "major", "minor", "dim", "aug", "sus2", "sus4",
    "maj7", "min7", "7", "m7b5", "dim7", "mMaj7", "6", "m6", "7b5", "7#5", "7sus4",
    "9", "min9", "maj9", "7b9", "7#9", "7#11", "7b13", "maj7#11", "6/9",
    "11", "min11", "13", "min13", "maj13"
]

class ProcessingWorker(QThread):
    finished = Signal(dict, str, dict)
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, audio_path, output_dir, guitar_channel, start_sec, end_sec, prefix=""):
        super().__init__()
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.guitar_channel = guitar_channel
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.prefix = prefix

    def run(self):
        try:
            self.progress.emit(5, "Обрезка...")
            cropped = tempfile.mktemp(suffix=".wav")
            cut_audio_segment(self.audio_path, cropped, self.start_sec, self.end_sec)
            
            self.progress.emit(15, "Demucs...")
            stems = DemucsOnnxSeparator().separate_stems(cropped)
            stem_files = {}
            for name, data in stems.items():
                if name not in ["drums", "bass", "other", "vocals", "guitar", "piano"]: continue
                out = data.T if data.ndim > 1 else data
                safe_name = f"{self.prefix}_{name}" if self.prefix else name
                fp = os.path.join(self.output_dir, f"{safe_name}.wav")
                sf.write(fp, out, 44100)
                stem_files[safe_name] = fp

            audio, sr = load_audio_native(cropped)
            transcriber = MuScriptorTranscriber(model_size="small")
            
            all_guitar_notes = []
            all_bass_notes = []

            tags_for_stem = {
                "guitar": ["distorted_electric_guitar", "clean_electric_guitar", "acoustic_guitar"],
                "other": ["distorted_electric_guitar", "clean_electric_guitar", "acoustic_guitar"],
                "bass": ["electric_bass", "acoustic_bass"]
            }

            for stem_name, tags in tags_for_stem.items():
                if stem_name not in stems:
                    continue
                
                self.progress.emit(30, f"Анализ стема: {stem_name}...")
                stem_data = stems[stem_name]
                
                if stem_data.ndim > 1 and len(stem_data) >= 2:
                    if stem_name in ["guitar", "other"]:
                        if self.guitar_channel == "Левая (L)": mono = stem_data[0]
                        elif self.guitar_channel == "Правая (R)": mono = stem_data[1]
                        elif self.guitar_channel == "Центр (M)": mono = (stem_data[0] + stem_data[1]) / 2
                        elif self.guitar_channel == "Разность (S)": mono = (stem_data[0] - stem_data[1]) / 2
                        else: mono = np.mean(stem_data, axis=0)
                    else:
                        mono = np.mean(stem_data, axis=0)
                else:
                    mono = np.mean(stem_data, axis=0) if stem_data.ndim > 1 else stem_data
                
                import librosa
                if abs(len(mono) / sr - len(audio) / sr) > 0.5:
                    mono = librosa.resample(mono, orig_sr=44100, target_sr=sr)
                
                for tag in tags:
                    notes = transcriber.transcribe(mono, sr, tag)
                    if not notes:
                        continue
                    
                    if stem_name == "bass":
                        all_bass_notes.extend(notes)
                    else:
                        all_guitar_notes.extend(notes)

            all_guitar_notes = clean_notes(all_guitar_notes)
            all_bass_notes = clean_notes(all_bass_notes)

            tab_electric = arrange_with_dp(all_guitar_notes, instrument="guitar") if all_guitar_notes else []
            tab_bass = arrange_with_dp(all_bass_notes, instrument="bass") if all_bass_notes else []

            if not tab_electric and not tab_bass:
                raise RuntimeError("Не удалось распознать ноты гитары или баса.")

            key = TheoryAnalyzer.estimate_key([])

            self.finished.emit(
                {"electric": tab_electric, "acoustic": tab_electric, "bass": tab_bass}, 
                key, 
                stem_files
            )
            if os.path.exists(cropped): os.unlink(cropped)
        except Exception as e: self.error.emit(str(e))

class AudioProcessWorker(QThread):
    processed = Signal(str)
    failed = Signal(str)
    def __init__(self, path, rate, semitones):
        super().__init__()
        self.path = path; self.rate = rate; self.semitones = semitones
    def run(self):
        try:
            out = tempfile.mktemp(suffix=".wav")
            AudioProcessor.process(self.path, out, self.rate, self.semitones)
            self.processed.emit(out)
        except Exception as e: self.failed.emit(str(e))

class StemSpeedWorker(QThread):
    finished = Signal()
    def __init__(self, mixer, rate):
        super().__init__()
        self.mixer = mixer
        self.rate = rate
        
    def run(self):
        import librosa
        with self.mixer.lock:
            for name, track in self.mixer.tracks.items():
                if 'original_data' not in track:
                    track['original_data'] = track['data'].copy()
                
                if self.rate == 1.0:
                    track['data'] = track['original_data']
                else:
                    orig = track['original_data']
                    if orig.ndim == 2:
                        stretched = np.column_stack([
                            librosa.effects.time_stretch(orig[:, ch], rate=self.rate) 
                            for ch in range(orig.shape[1])
                        ])
                    else:
                        stretched = librosa.effects.time_stretch(orig, rate=self.rate)
                    track['data'] = stretched.astype(np.float32)
            
            self.mixer._total_frames = max((len(t['data']) for t in self.mixer.tracks.values()), default=0)
            self.mixer._play_end_frame = self.mixer._total_frames
            self.mixer._position_frames = 0
        
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metal Transcriber — DAW Edition")
        self.resize(1600, 950)
        self.setStyleSheet(GUITAR_PRO_QSS)

        self.audio_path = None
        self.processed_audio_path = None
        self.tab_tracks: Dict[str, list] = {"electric": [], "acoustic": [], "bass": []}
        self.note_items: List[QListWidgetItem] = []
        self.worker = None
        self.audio_worker = None
        self.speed_worker = None
        self.track_widgets = []
        self.circle_window = None
        self.is_processed = False
        self.selection_start = 0.0
        self.selection_end = 0.0
        self.transcription_count = 0

        self.mixer = MultiTrackMixer(sample_rate=44100, channels=2)
        
        self.position_timer = QTimer()
        self.position_timer.setInterval(30)
        self.position_timer.timeout.connect(self._update_playhead)
        self.position_timer.start()

        self.cpu_timer = QTimer()
        self.cpu_timer.setInterval(1000)
        self.cpu_timer.timeout.connect(self._update_cpu_usage)
        self.cpu_timer.start()

        self.fretboard_state = FretboardState.load()
        self._build_ui()
        self._sync_controls_from_state()

        ok, msg = check_models_available()
        self.transcribe_btn.setEnabled(ok)
        self.status_label.setText("Готов" if ok else f"⚠ {msg}")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        tb = QHBoxLayout()
        self.load_btn = QPushButton("📂"); self.load_btn.setObjectName("playerBtn"); self.load_btn.setFixedSize(40, 30); self.load_btn.clicked.connect(self._load_audio); tb.addWidget(self.load_btn)
        
        self.stop_btn = QPushButton("⏹"); self.stop_btn.setObjectName("playerBtn"); self.stop_btn.setFixedSize(40, 30); self.stop_btn.clicked.connect(self._stop_play); tb.addWidget(self.stop_btn)
        self.step_back_1s = QPushButton("⏪"); self.step_back_1s.setObjectName("playerBtn"); self.step_back_1s.setFixedSize(40, 30); self.step_back_1s.clicked.connect(lambda: self._step_playhead(-1.0)); tb.addWidget(self.step_back_1s)
        self.step_back_01s = QPushButton("◀"); self.step_back_01s.setObjectName("playerBtn"); self.step_back_01s.setFixedSize(40, 30); self.step_back_01s.clicked.connect(lambda: self._step_playhead(-0.1)); tb.addWidget(self.step_back_01s)
        
        self.play_btn = QPushButton("▶"); self.play_btn.setObjectName("playerBtn"); self.play_btn.setFixedSize(40, 30); self.play_btn.clicked.connect(self._toggle_play); tb.addWidget(self.play_btn)
        
        self.step_fwd_01s = QPushButton("▶"); self.step_fwd_01s.setObjectName("playerBtn"); self.step_fwd_01s.setFixedSize(40, 30); self.step_fwd_01s.clicked.connect(lambda: self._step_playhead(0.1)); tb.addWidget(self.step_fwd_01s)
        self.step_fwd_1s = QPushButton("⏩"); self.step_fwd_1s.setObjectName("playerBtn"); self.step_fwd_1s.setFixedSize(40, 30); self.step_fwd_1s.clicked.connect(lambda: self._step_playhead(1.0)); tb.addWidget(self.step_fwd_1s)
        
        self.play_sel_btn = QPushButton("▶|"); self.play_sel_btn.setObjectName("playerBtn"); self.play_sel_btn.setFixedSize(40, 30); self.play_sel_btn.clicked.connect(self._play_from_selection_start); tb.addWidget(self.play_sel_btn)
        
        self.transcribe_btn = QPushButton("🎸 Транскрибировать"); self.transcribe_btn.clicked.connect(self._start_processing); tb.addWidget(self.transcribe_btn)

        self.sync_btn = QPushButton("🔄 Синхронизировать")
        self.sync_btn.setToolTip("Выровнять все дорожки по длине Master-трека")
        self.sync_btn.clicked.connect(self._sync_tracks)
        tb.addWidget(self.sync_btn)

        # ВЫБОР КАНАЛА С ПОДСКАЗКАМИ
        tb.addWidget(QLabel("Канал гитары:"))
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["Микс (L+R)", "Центр (M) Соло", "Разность (S) Ритм", "Левая (L)", "Правая (R)"])
        self.channel_combo.setToolTip(
            "Выберите, какую гитару искать:\n"
            "• Микс (L+R) — все гитары сразу\n"
            "• Центр (M) — обычно соло-гитара\n"
            "• Разность (S) — обычно ритм-гитары (разведены по панораме)"
        )
        tb.addWidget(self.channel_combo)

        tb.addWidget(QLabel("Скорость:"))
        self.speed_combo = QComboBox(); self.speed_combo.addItems(["1.0x", "0.75x", "0.5x", "0.25x"]); self.speed_combo.currentTextChanged.connect(self._on_speed_changed); tb.addWidget(self.speed_combo)

        tb.addWidget(QLabel("Тон:"))
        self.pitch_combo = QComboBox(); self.pitch_combo.addItems(["0", "-1", "-2", "+1", "+2"]); self.pitch_combo.currentTextChanged.connect(self._on_pitch_changed); tb.addWidget(self.pitch_combo)

        self.position_slider = QSlider(Qt.Orientation.Horizontal); self.position_slider.sliderMoved.connect(self._on_slider_moved); tb.addWidget(self.position_slider, 1)
        self.time_label = QLabel("00:00.000 / 00:00.000"); self.time_label.setStyleSheet("color:#a0b4d0;font-weight:bold;font-family:Consolas,monospace;"); tb.addWidget(self.time_label)
        self.vu_meter = VUMeter(); tb.addWidget(self.vu_meter)
        root.addLayout(tb)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(True) 
        self.main_splitter.setHandleWidth(4)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        track_group = QGroupBox("Мультитрек")
        track_layout = QVBoxLayout(track_group)
        track_layout.setContentsMargins(0, 5, 0, 0)
        track_layout.setSpacing(0)

        self.timeline = TimelineWidget()
        self.timeline.seek_requested.connect(self._seek)
        track_layout.addWidget(self.timeline)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.tracks_container = QWidget(); 
        self.tracks_layout = QVBoxLayout(self.tracks_container); 
        self.tracks_layout.setContentsMargins(0,0,0,0)
        
        self.tracks_splitter = QSplitter(Qt.Orientation.Vertical)
        self.tracks_splitter.setHandleWidth(4)
        self.tracks_splitter.setChildrenCollapsible(False)
        self.tracks_layout.addWidget(self.tracks_splitter)
        self.tracks_layout.addStretch()
        
        scroll.setWidget(self.tracks_container)
        track_layout.addWidget(scroll)
        
        left_layout.addWidget(track_group)
        self.main_splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.circle_btn = QPushButton("🎡 Круг"); self.circle_btn.clicked.connect(self._toggle_circle_window); top.addWidget(self.circle_btn)
        self.copy_btn = QPushButton("📋 Copy"); self.copy_btn.clicked.connect(self._copy_state); top.addWidget(self.copy_btn)
        top.addStretch()
        rl.addLayout(top)

        scale_group = QGroupBox("Гамма")
        scale_layout = QHBoxLayout(scale_group)
        scale_layout.setContentsMargins(10, 15, 10, 10)
        scale_form = QFormLayout()
        combo_w = 190
        self.scale_root_combo = QComboBox(); self.scale_root_combo.addItems(SHARP_NAMES)
        self.scale_root_combo.setFixedWidth(combo_w)
        self.scale_root_combo.currentTextChanged.connect(self._on_state_changed)
        scale_form.addRow("Тоника:", self.scale_root_combo)
        self.scale_combo = QComboBox(); self.scale_combo.addItems(list(SCALES.keys()))
        self.scale_combo.setFixedWidth(combo_w)
        self.scale_combo.currentTextChanged.connect(self._on_state_changed)
        scale_form.addRow("Тип лада:", self.scale_combo)
        scale_layout.addLayout(scale_form)
        self.scale_diagram = ScaleDiagramWidget()
        self.scale_diagram.noteClicked.connect(play_midi_note)
        scale_layout.addWidget(self.scale_diagram, 1)
        rl.addWidget(scale_group)

        chord_group = QGroupBox("Аккорд")
        chord_layout = QHBoxLayout(chord_group)
        chord_layout.setContentsMargins(10, 15, 10, 10)
        chord_form = QFormLayout()
        self.chord_root_combo = QComboBox(); self.chord_root_combo.addItems(SHARP_NAMES)
        self.chord_root_combo.setFixedWidth(combo_w)
        self.chord_root_combo.currentTextChanged.connect(self._on_state_changed)
        chord_form.addRow("Тоника:", self.chord_root_combo)
        self.chord_type_combo = QComboBox()
        self.chord_type_combo.setFixedWidth(combo_w)
        self.chord_type_combo.addItems(ORDERED_CHORD_TYPES)
        self.chord_type_combo.currentTextChanged.connect(self._on_state_changed)
        chord_form.addRow("Тип:", self.chord_type_combo)
        self.caged_combo = QComboBox(); self.caged_combo.addItems(["All", "C", "A", "G", "E", "D"])
        self.caged_combo.setFixedWidth(combo_w)
        self.caged_combo.currentTextChanged.connect(self._on_state_changed)
        chord_form.addRow("CAGED:", self.caged_combo)
        chord_layout.addLayout(chord_form)
        self.chord_diagram = ChordDiagramWidget()
        self.chord_diagram.noteClicked.connect(play_midi_note)
        chord_layout.addWidget(self.chord_diagram, 1)
        rl.addWidget(chord_group)

        controls = QHBoxLayout()
        
        controls.addWidget(QLabel("Просмотр:"))
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Электрогитара", "Акустика", "Бас"])
        self.view_combo.setFixedWidth(130)
        self.view_combo.currentTextChanged.connect(self._on_view_changed)
        controls.addWidget(self.view_combo)
        
        controls.addSpacing(10)
        self.btn_display = QPushButton("Ноты")
        self.btn_display.clicked.connect(self._cycle_display)
        controls.addWidget(QLabel("Текст:"))
        controls.addWidget(self.btn_display)
        controls.addSpacing(10)
        self.btn_color = QPushButton("Октавы")
        self.btn_color.setCheckable(True)
        self.btn_color.toggled.connect(self._on_color_toggled)
        controls.addWidget(self.btn_color)
        controls.addSpacing(20)
        self.chk_scale = QCheckBox("Гамма"); self.chk_scale.toggled.connect(self._on_state_changed)
        self.chk_chord = QCheckBox("Аккорд"); self.chk_chord.toggled.connect(self._on_state_changed)
        self.chk_notes = QCheckBox("Ноты"); self.chk_notes.toggled.connect(self._on_state_changed)
        controls.addWidget(self.chk_scale); controls.addWidget(self.chk_chord); controls.addWidget(self.chk_notes)
        controls.addStretch()
        self.zoom_out_btn = QPushButton("Zoom -"); self.zoom_out_btn.setFixedWidth(70); self.zoom_out_btn.clicked.connect(self._zoom_out); controls.addWidget(self.zoom_out_btn)
        self.zoom_in_btn = QPushButton("Zoom +"); self.zoom_in_btn.setFixedWidth(70); self.zoom_in_btn.clicked.connect(self._zoom_in); controls.addWidget(self.zoom_in_btn)
        rl.addLayout(controls)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.setHandleWidth(4)

        self.fretboard = FretboardWidget()
        self.fretboard.noteClicked.connect(play_midi_note)
        right_splitter.addWidget(self.fretboard)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        notes_g = QGroupBox("Все распознанные ноты")
        notes_v = QVBoxLayout(notes_g)
        self.notes_list = QListWidget()
        self.notes_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        notes_v.addWidget(self.notes_list)
        bottom_layout.addWidget(notes_g, 1)

        exp = QHBoxLayout()
        self.export_gp5_btn = QPushButton("GP5")
        self.export_gp5_btn.setFixedHeight(30)
        self.export_gp5_btn.clicked.connect(self._export_gp5)
        self.export_gp5_btn.setEnabled(False)
        exp.addWidget(self.export_gp5_btn)
        
        self.export_xml_btn = QPushButton("MusicXML")
        self.export_xml_btn.setFixedHeight(30)
        self.export_xml_btn.clicked.connect(self._export_musicxml)
        self.export_xml_btn.setEnabled(False)
        exp.addWidget(self.export_xml_btn)
        bottom_layout.addLayout(exp)

        self.key_label = QLabel("Тональность: —"); self.key_label.setStyleSheet("font-size:14px;font-weight:bold;color:#569FFF;")
        bottom_layout.addWidget(self.key_label)

        right_splitter.addWidget(bottom_widget)
        right_splitter.setSizes([600, 300])

        rl.addWidget(right_splitter, 1)

        self.main_splitter.addWidget(right)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([1000, 600])
        root.addWidget(self.main_splitter, 1)

        status = QHBoxLayout()
        self.status_label = QLabel("Готов"); self.status_label.setStyleSheet("color:#a0b4d0;"); status.addWidget(self.status_label, 1)
        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setFixedWidth(200); status.addWidget(self.progress)
        
        self.cpu_label = QLabel("CPU: 0%")
        self.cpu_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding-right: 10px;")
        status.addWidget(self.cpu_label)
        
        root.addLayout(status)

    def _update_cpu_usage(self):
        try:
            cpu = psutil.cpu_percent()
            self.cpu_label.setText(f"CPU: {cpu}%")
            if cpu > 80:
                self.cpu_label.setStyleSheet("color: #FF5E5E; font-weight: bold; padding-right: 10px;")
            elif cpu > 50:
                self.cpu_label.setStyleSheet("color: #FFC107; font-weight: bold; padding-right: 10px;")
            else:
                self.cpu_label.setStyleSheet("color: #4CAF50; font-weight: bold; padding-right: 10px;")
        except Exception:
            self.cpu_label.setText("CPU: N/A")
            self.cpu_timer.stop()

    def _sync_tracks(self):
        if not self.mixer.tracks:
            return
            
        success = self.mixer.sync_tracks()
        if success:
            self.status_label.setText("Дорожки синхронизированы по Master-треку.")
            for tw in self.track_widgets:
                if tw.name in self.mixer.tracks:
                    tw.update_waveform_data(self.mixer.tracks[tw.name]['data'], self.timeline._duration)
            
            total_dur = self.mixer.get_duration()
            self.timeline.set_duration(total_dur)
            self.position_slider.setMaximum(int(total_dur * 1000))
            self._seek(self.mixer.get_position())
        else:
            self.status_label.setText("Не удалось синхронизировать (Master-трек не найден).")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            step = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.1
            self._step_playhead(-step)
        elif event.key() == Qt.Key.Key_Right:
            step = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.1
            self._step_playhead(step)
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        else:
            super().keyPressEvent(event)

    def _step_playhead(self, delta: float):
        current_global = self.timeline.playhead.value()
        self._seek(current_global + delta)

    def _on_view_changed(self, text):
        if text == "Бас":
            self.fretboard_state = self.fretboard_state.replace(tuning="bass")
        else:
            self.fretboard_state = self.fretboard_state.replace(tuning="standard")
            
        self.fretboard.set_state(self.fretboard_state)
        self._rebuild_notes_list()
        self._update_ui_from_position(self.mixer.get_position())

    def _rebuild_notes_list(self):
        if not self.tab_tracks: return
        view = self.view_combo.currentText()
        key = "electric" if view == "Электрогитара" else ("acoustic" if view == "Акустика" else "bass")
        
        notes = self.tab_tracks.get(key, [])
        
        self.notes_list.clear()
        self.note_items.clear()
        
        groups = {}
        for s, e, string, fret in notes:
            key_t = round(s, 2)
            if key_t not in groups: groups[key_t] = []
            groups[key_t].append((string, fret))

        sorted_times = sorted(groups.keys())
        for i, t in enumerate(sorted_times):
            parts = [f"Стр.{string} Лад.{fret}" for string, fret in groups[t]]
            text = f"{t:.2f}s | " + " | ".join(parts)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, t)
            item.setBackground(QColor("#212a3b") if i % 2 == 0 else QColor("#1c2331"))
            self.notes_list.addItem(item)
            self.note_items.append(item)

    def _sync_controls_from_state(self):
        s = self.fretboard_state
        self.chord_root_combo.setCurrentText(s.chord_root)
        self.scale_root_combo.setCurrentText(s.scale_root)
        display = s.display if s.display in ("notes", "intervals") else "notes"
        self.btn_display.setText("Ноты" if display == "notes" else "Интервалы")
        self.btn_color.blockSignals(True)
        self.btn_color.setChecked(s.color_mode == "degrees")
        self.btn_color.setText("Ступени" if s.color_mode == "degrees" else "Октавы")
        self.btn_color.blockSignals(False)
        self.chord_type_combo.setCurrentText(s.chord_type)
        self.caged_combo.setCurrentText(s.caged_shape)
        self.scale_combo.setCurrentText(s.scale_type)
        self.chk_scale.setChecked(s.show_scale)
        self.chk_chord.setChecked(s.show_chord)
        self.chk_notes.setChecked(s.show_transcribed)
        
        self.fretboard.set_state(s)
        self._update_scale_diagram()
        self._update_chord_diagram()

    def _cycle_display(self):
        new_display = "intervals" if self.fretboard_state.display == "notes" else "notes"
        self.fretboard_state = self.fretboard_state.replace(display=new_display)
        self.btn_display.setText("Ноты" if new_display == "notes" else "Интервалы")
        self._on_state_changed()

    def _on_color_toggled(self, checked):
        new_mode = "degrees" if checked else "octaves"
        self.fretboard_state = self.fretboard_state.replace(color_mode=new_mode)
        self.btn_color.setText("Ступени" if checked else "Октавы")
        self._on_state_changed()

    def _on_state_changed(self, *_):
        s = self.fretboard_state.replace(
            chord_root=self.chord_root_combo.currentText(),
            scale_root=self.scale_root_combo.currentText(),
            chord_type=self.chord_type_combo.currentText() or self.fretboard_state.chord_type,
            caged_shape=self.caged_combo.currentText(),
            scale_type=self.scale_combo.currentText(),
            show_scale=self.chk_scale.isChecked(),
            show_chord=self.chk_chord.isChecked(),
            show_transcribed=self.chk_notes.isChecked(),
        )
        self.fretboard_state = s
        self.fretboard.set_state(s)
        self._update_scale_diagram()
        self._update_chord_diagram()
        self.fretboard_state.save()

    def _update_scale_diagram(self):
        root = self.fretboard_state.scale_root
        stype = self.fretboard_state.scale_type
        info = TheoryAnalyzer.get_scale_info(root, stype)
        if not info:
            self.scale_diagram.set_scale(-1, set(), {}, "", [])
            return
            
        root_pc = info["tonic_pc"]
        scale_pcs = info["scale_pcs"]
        pcs_to_degree = info["pcs_to_degree"]
        
        notes_list = []
        intervals = SCALES[stype]
        for semitones in intervals:
            pc = (root_pc + semitones) % 12
            spelled = info["pcs_to_spelling"].get(pc, SHARP_NAMES[pc])
            deg = info["pcs_to_degree"].get(pc, "")
            notes_list.append((spelled, deg))
            
        self.scale_diagram.set_scale(root_pc, scale_pcs, pcs_to_degree, f"{root} {stype}", notes_list)

    def _update_chord_diagram(self):
        root = self.fretboard_state.chord_root
        ctype = self.fretboard_state.chord_type
        info = TheoryAnalyzer.get_chord_info(root, ctype)
        if not info:
            self.chord_diagram.set_chord(-1, set(), {}, "", [])
            return
        root_pc = info["root_pc"]
        chord_pcs = info["chord_pcs"]
        pcs_to_degree = info["pcs_to_degree"]
        
        name_map = {"major": "", "minor": "m", "dim": "dim", "aug": "aug", "maj7": "maj7", "min7": "m7", "7": "7", "m7b5": "m7b5", "dim7": "dim7", "mMaj7": "mMaj7", "9": "9", "min9": "m9", "maj9": "maj9"}
        chord_name = f"{root}{name_map.get(ctype, ctype)}"
        
        notes_list = []
        if "pcs_to_spelling" in info:
            for pc, spelled in info["pcs_to_spelling"].items():
                notes_list.append((spelled, pcs_to_degree[pc]))
        self.chord_diagram.set_chord(root_pc, chord_pcs, pcs_to_degree, chord_name, notes_list)

    def _zoom_in(self): self._change_zoom(0.2)
    def _zoom_out(self): self._change_zoom(-0.2)
    def _change_zoom(self, delta: float):
        z = max(0.5, min(2.0, self.fretboard_state.zoom + delta))
        self.fretboard_state = self.fretboard_state.replace(zoom=z)
        self.fretboard.set_state(self.fretboard_state)

    def _copy_state(self):
        QApplication.clipboard().setText(self.fretboard_state.to_query_string())
        self.status_label.setText("State скопирован в буфер.")

    def _load_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Аудио", "", "Аудио (*.mp3 *.wav *.flac *.ogg)")
        if not path: return
        self.audio_path = path; self.processed_audio_path = path; self.is_processed = False
        self.speed_combo.setCurrentText("1.0x"); self.pitch_combo.setCurrentText("0")
        self.tab_tracks = {"electric": [], "acoustic": [], "bass": []}
        self.note_items.clear(); self.notes_list.clear()
        self.transcription_count = 0
        self.status_label.setText(f"Загружен: {os.path.basename(path)}")
        
        self.mixer.stop(); self.mixer = MultiTrackMixer(sample_rate=44100, channels=2); self.mixer.load_stem("master", path)
        total_dur = self.mixer.get_duration()
        self.timeline.set_duration(total_dur)
        self.mixer.set_play_range(0, total_dur); self._seek(0)
        
        for i in reversed(range(self.tracks_splitter.count())): 
            self.tracks_splitter.widget(i).deleteLater()
        self.track_widgets.clear()
        
        lane = TrackLaneWidget("master", path, self.mixer, self.timeline, is_master=True, start_sec=0.0, end_sec=total_dur, total_duration=total_dur, color=STEM_COLORS["master"])
        lane.seek_requested.connect(self._seek)
        lane.region_changed.connect(self._on_region_changed)
        
        self.tracks_splitter.addWidget(lane)
        self.track_widgets.append(lane)

    def _toggle_play(self):
        if self.mixer._playing: self.mixer.pause(); self.play_btn.setText("▶")
        else: self.mixer.play(); self.play_btn.setText("⏸")

    def _stop_play(self):
        self.mixer.stop(); self.play_btn.setText("▶"); self._update_playhead()

    def _play_from_selection_start(self):
        self._seek(self.selection_start)
        if not self.mixer._playing: self.mixer.play(); self.play_btn.setText("⏸")

    def _on_slider_moved(self, v): self._seek(v / 1000.0)
    
    def _seek(self, t_global):
        t_global = max(0.0, min(t_global, self.timeline._duration))
        
        self.mixer.seek(t_global)
        
        self.position_slider.blockSignals(True)
        self.position_slider.setMaximum(int(self.timeline._duration * 1000))
        self.position_slider.setValue(int(t_global * 1000))
        self.position_slider.blockSignals(False)
        
        self.timeline.set_playhead(t_global)
        for tw in self.track_widgets:
            tw.update_playhead(t_global)
            
        self._update_ui_from_position(t_global)

    def _on_region_changed(self, s, e):
        self.selection_start = s
        self.selection_end = e
        # ТОЧКА ЗАПУСКА БОЛЬШЕ НЕ ОГРАНИЧЕНА РАМКОЙ

    def _format_time(self, t):
        m = int(t // 60); s = t % 60
        return f"{m:02d}:{s:06.3f}"

    def _update_playhead(self):
        if not self.mixer.tracks: return
        pos = self.mixer.get_position()
        dur = self.timeline._duration
        
        if dur > 0:
            new_val = int(pos * 1000)
            if self.position_slider.value() != new_val:
                self.position_slider.blockSignals(True)
                self.position_slider.setMaximum(int(dur * 1000))
                self.position_slider.setValue(new_val)
                self.position_slider.blockSignals(False)
                
            self.timeline.set_playhead(pos)
            for tw in self.track_widgets:
                tw.update_playhead(pos)
            
            self.time_label.setText(f"{self._format_time(pos)} / {self._format_time(dur)}")
            self.vu_meter.set_levels(self.mixer.get_levels())
            self._update_ui_from_position(pos)
            
        if not self.mixer._playing and self.play_btn.text() == "⏸": 
            self.play_btn.setText("▶")

    def _update_ui_from_position(self, pos: float):
        if not self.tab_tracks: return

        view = self.view_combo.currentText()
        if view == "Электрогитара":
            key = "electric"
        elif view == "Акустика":
            key = "acoustic"
        else:
            key = "bass"

        notes = self.tab_tracks.get(key, [])
        
        self.fretboard.display_tab_notes(notes, current_pos=pos)
        
        active_times = set()
        for i, (s, e, string_num, fret) in enumerate(notes):
            if s - 0.05 <= pos <= e + 0.05:
                active_times.add(round(s, 2))
                
        self.notes_list.blockSignals(True)
        self.notes_list.clearSelection()
        
        first_selected_item = None
        for i, item in enumerate(self.note_items):
            item_time = item.data(Qt.UserRole)
            if item_time in active_times:
                item.setSelected(True)
                if first_selected_item is None:
                    first_selected_item = item
                    
        if first_selected_item:
            self.notes_list.scrollToItem(first_selected_item, QAbstractItemView.ScrollHint.PositionAtCenter)
            
        self.notes_list.blockSignals(False)

    def _on_speed_changed(self, text):
        rate = float(text.replace("x", ""))
        
        if self.is_processed:
            self.status_label.setText("Изменение скорости стемов...")
            self.speed_combo.setEnabled(False)
            self.play_btn.setEnabled(False)
            
            self.speed_worker = StemSpeedWorker(self.mixer, rate)
            self.speed_worker.finished.connect(lambda: self._on_speed_stems_finished(rate))
            self.speed_worker.start()
        else:
            self._apply_audio_processing(rate=rate, semitones=0.0)
            
    def _on_speed_stems_finished(self, rate):
        self.speed_combo.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.status_label.setText("Готов")
        
        if self.tab_tracks:
            for key in self.tab_tracks:
                new_notes = []
                for s, e, string, fret in self.tab_tracks[key]:
                    new_notes.append((s / rate, e / rate, string, fret))
                self.tab_tracks[key] = new_notes
                
            self._rebuild_notes_list()
            
        total_dur = self.mixer.get_duration()
        self.timeline.set_duration(total_dur)
        self.position_slider.setMaximum(int(total_dur * 1000))
        
        for tw in self.track_widgets:
            if tw.name in self.mixer.tracks:
                tw.update_waveform_data(self.mixer.tracks[tw.name]['data'], self.timeline._duration)
        
        self._seek(0)
        self._on_state_changed()

    def _on_pitch_changed(self, text):
        if self.is_processed:
            self.pitch_combo.blockSignals(True)
            self.pitch_combo.setCurrentText("0")
            self.pitch_combo.blockSignals(False)
            QMessageBox.warning(self, "Внимание", "Сбросьте распознавание, чтобы изменить тон.")
            return
        try: st = float(text)
        except ValueError: return
        self._apply_audio_processing(rate=1.0, semitones=st)

    def _apply_audio_processing(self, rate, semitones):
        if not self.audio_path: return
        self.status_label.setText("Обработка аудио..."); self.play_btn.setEnabled(False)
        self.audio_worker = AudioProcessWorker(self.audio_path, rate, semitones)
        self.audio_worker.processed.connect(self._on_audio_processed)
        self.audio_worker.failed.connect(self._on_audio_err)
        self.audio_worker.start()

    def _on_audio_processed(self, path):
        self.processed_audio_path = path; self.play_btn.setEnabled(True)
        self.mixer.stop(); self.mixer = MultiTrackMixer(sample_rate=44100, channels=2); self.mixer.load_stem("master", path)
        
        total_dur = self.mixer.get_duration()
        self.timeline.set_duration(total_dur)
        
        for i in reversed(range(self.tracks_splitter.count())): 
            self.tracks_splitter.widget(i).deleteLater()
        self.track_widgets.clear()
        
        lane = TrackLaneWidget("master", path, self.mixer, self.timeline, is_master=True, start_sec=0.0, end_sec=total_dur, total_duration=total_dur, color=STEM_COLORS["master"])
        lane.seek_requested.connect(self._seek)
        lane.region_changed.connect(self._on_region_changed)
        
        self.tracks_splitter.addWidget(lane)
        self.track_widgets.append(lane)
        
        self.mixer.set_play_range(0, self.mixer.get_duration()); self._seek(0); 

    def _on_audio_err(self, msg): self.play_btn.setEnabled(True); QMessageBox.critical(self, "Ошибка", msg)

    def _toggle_circle_window(self):
        if self.circle_window is None:
            self.circle_window = CircleOfFifthsWindow(self); self.circle_window.key_selected.connect(self._on_circle_key_selected)
        if self.circle_window.isVisible(): self.circle_window.hide(); self.circle_btn.setText("🎡 Круг")
        else: self.circle_window.show(); self.circle_btn.setText("🎡 Скрыть")

    def _on_circle_key_selected(self, root, mode):
        self.scale_root_combo.setCurrentText(root)
        self.chord_root_combo.setCurrentText(root)
        if mode == "major": self.scale_combo.setCurrentText("Major (Ionian)")
        else: self.scale_combo.setCurrentText("Natural Minor (Aeolian)")
        self._on_state_changed()

    def _start_processing(self):
        if not self.audio_path: return
        ok, msg = check_models_available()
        if not ok: QMessageBox.warning(self, "Модели не найдены", msg); return
        
        path = self.processed_audio_path or self.audio_path
        
        s, e = self.selection_start, self.selection_end
        if e <= s:
            QMessageBox.warning(self, "Внимание", "Выделите фрагмент на дорожке Master.")
            return
            
        self.is_processed = False
        self.transcribe_btn.setEnabled(False); self.progress.setVisible(True); self.progress.setValue(0)
        
        self.transcription_count += 1
        prefix = f"t{self.transcription_count}"
        
        out_dir = os.path.join(os.path.dirname(path), "stems"); os.makedirs(out_dir, exist_ok=True)
        channel = self.channel_combo.currentText()
        
        self.worker = ProcessingWorker(path, out_dir, channel, s, e, prefix)
        
        self.worker.progress.connect(lambda v, m: (self.progress.setValue(v), self.status_label.setText(m)))
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(lambda m: QMessageBox.critical(self, "Ошибка", m))
        self.worker.start()

    def _on_finished(self, tracks, key, stem_files):
        self.progress.setVisible(False); self.transcribe_btn.setEnabled(True); self.is_processed = True
        self.key_label.setText(f"Тональность: {key}")
        
        offset = self.selection_start
        
        for key_name, new_notes in tracks.items():
            if key_name not in self.tab_tracks:
                self.tab_tracks[key_name] = []
            for s, e, string, fret in new_notes:
                self.tab_tracks[key_name].append((s + offset, e + offset, string, fret))
        
        for key_name in self.tab_tracks:
            self.tab_tracks[key_name].sort(key=lambda x: x[0])
            
        self._rebuild_notes_list()
        
        base_names = set()
        for name in stem_files.keys():
            base_name = name.split("_")[-1] if "_" in name else name
            base_names.add(base_name)
            
        for base_name in base_names:
            if base_name == "master": continue
            file_path = next(p for n, p in stem_files.items() if (n.split("_")[-1] if "_" in n else n) == base_name)
            
            self.mixer.append_stem(base_name, file_path, offset, self.timeline._duration)
            
            existing_lane = next((w for w in self.track_widgets if w.name == base_name), None)
            if not existing_lane:
                lane = TrackLaneWidget(
                    base_name, file_path, self.mixer, self.timeline, 
                    is_master=False, 
                    start_sec=0.0, end_sec=0.0, 
                    total_duration=self.timeline._duration,
                    color=STEM_COLORS.get(base_name, "#9E9E9E")
                )
                lane.seek_requested.connect(self._seek)
                self.tracks_splitter.addWidget(lane)
                self.track_widgets.append(lane)
                existing_lane = lane
                
            if base_name in self.mixer.tracks:
                existing_lane.update_waveform_data(self.mixer.tracks[base_name]['data'], self.timeline._duration)
        
        if self.transcription_count == 1:
            self.mixer.set_mute("master", True)
            
        self.mixer.set_play_range(0, self.timeline._duration)
        self._seek(self.selection_start) 
        if not self.mixer._playing:
            self.mixer.play(); self.play_btn.setText("⏸")
        
        self._on_view_changed(self.view_combo.currentText())
        self._on_state_changed()

    def _export_gp5(self):
        view = self.view_combo.currentText()
        key = "electric" if view == "Электрогитара" else ("acoustic" if view == "Акустика" else "bass")
        notes = self.tab_tracks.get(key, []) if self.tab_tracks else []
        
        if not notes: 
            QMessageBox.warning(self, "Внимание", "Нет нот для экспорта.")
            return
            
        path, _ = QFileDialog.getSaveFileName(self, "Save GP5", "", "Guitar Pro 5 (*.gp5)")
        if path:
            try: 
                inst = "bass" if key == "bass" else "guitar"
                export_gp5(notes, path, instrument=inst)
                QMessageBox.information(self, "OK", "Сохранено")
            except Exception as e: QMessageBox.critical(self, "Ошибка", str(e))

    def _export_musicxml(self):
        view = self.view_combo.currentText()
        key = "electric" if view == "Электрогитара" else ("acoustic" if view == "Акустика" else "bass")
        notes = self.tab_tracks.get(key, []) if self.tab_tracks else []
        
        if not notes: 
            QMessageBox.warning(self, "Внимание", "Нет нот для экспорта.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save MusicXML", "", "MusicXML (*.musicxml *.xml)")
        if path:
            try: export_musicxml(notes, path); QMessageBox.information(self, "OK", "Сохранено")
            except Exception as e: QMessageBox.critical(self, "Ошибка", str(e))

    def _reset_to_original(self):
        if not self.audio_path: return
        self.is_processed = False; self.tab_tracks = {"electric": [], "acoustic": [], "bass": []}
        self.note_items.clear(); self.notes_list.clear()
        self.transcription_count = 0
        
        self.mixer.stop(); self.mixer = MultiTrackMixer(sample_rate=44100, channels=2); self.mixer.load_stem("master", self.processed_audio_path or self.audio_path)
        
        total_dur = self.mixer.get_duration()
        self.timeline.set_duration(total_dur)
        
        for i in reversed(range(self.tracks_splitter.count())): 
            self.tracks_splitter.widget(i).deleteLater()
        self.track_widgets.clear()
        
        lane = TrackLaneWidget("master", self.processed_audio_path or self.audio_path, self.mixer, self.timeline, is_master=True, start_sec=0.0, end_sec=total_dur, total_duration=total_dur, color=STEM_COLORS["master"])
        lane.seek_requested.connect(self._seek)
        lane.region_changed.connect(self._on_region_changed)
        
        self.tracks_splitter.addWidget(lane)
        self.track_widgets.append(lane)
        
        self.mixer.set_play_range(0, self.mixer.get_duration())