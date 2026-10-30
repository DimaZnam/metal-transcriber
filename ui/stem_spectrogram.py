# ui/stem_spectrogram.py
import numpy as np
import librosa
import pyqtgraph as pg

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QThread, Signal


class _StemSpectrogramWorker(QThread):
    """Считает mel-спектрограмму в фоне, чтобы не блокировать UI."""
    ready = Signal(np.ndarray)
    failed = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            y, sr = librosa.load(self.path, sr=22050, mono=True)
            S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64)
            S_db = librosa.power_to_db(S, ref=np.max)
            # pyqtgraph ожидает (rows=mel, cols=frames) → транспонируем
            self.ready.emit(S_db.T)
        except Exception as e:
            self.failed.emit(str(e))


class MiniSpectrogram(QWidget):
    """
    Маленькая спектрограмма для отдельного стема.
    Ширина подстраивается под родительский контейнер,
    высота фиксированная (~70 px).
    """
    def __init__(self, path: str, height: int = 70):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0f1720")
        self.plot.setFixedHeight(height)
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setMenuEnabled(False)

        self.img = pg.ImageItem()
        self.plot.addItem(self.img)
        # Красивая цветовая карта (тёмно-фиолетовый → жёлтый)
        self.img.setColorMap(pg.colormap.get("inferno"))

        layout.addWidget(self.plot)

        self.worker = _StemSpectrogramWorker(path)
        self.worker.ready.connect(self._on_ready)
        self.worker.failed.connect(
            lambda msg: print(f"[MiniSpectrogram] {msg}")
        )
        self.worker.start()

    def _on_ready(self, data: np.ndarray):
        self.img.setImage(data, autoLevels=True)