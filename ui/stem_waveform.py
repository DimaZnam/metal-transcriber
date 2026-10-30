# ui/stem_waveform.py
import numpy as np
import librosa
import pyqtgraph as pg

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QThread, Signal


class _StemWaveformWorker(QThread):
    """Считает форму волны в фоне."""
    ready = Signal(np.ndarray)
    failed = Signal(str)

    def __init__(self, path: str, num_points: int = 2000):
        super().__init__()
        self.path = path
        self.num_points = num_points

    def run(self):
        try:
            y, sr = librosa.load(self.path, sr=22050, mono=True)
            
            # Прореживаем данные для быстрой отрисовки (берем пики)
            if len(y) > self.num_points:
                step = len(y) // self.num_points
                y = y[:step * self.num_points].reshape(-1, step)
                # Берем максимальное отклонение от нуля в каждом блоке
                y_max = np.max(np.abs(y), axis=1)
                y_env = np.zeros_like(y_max)
                for i in range(len(y_max)):
                    # Сохраняем знак (чтобы волна была двусторонней)
                    y_env[i] = y_max[i] if np.mean(y[i]) > 0 else -y_max[i]
            else:
                y_env = y
                
            self.ready.emit(y_env)
        except Exception as e:
            self.failed.emit(str(e))


class StemWaveform(QWidget):
    """Виджет осциллограммы (как в Audacity) для отдельного стема."""
    def __init__(self, path: str, height: int = 80):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0f1720")
        self.plot.setFixedHeight(height)
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.setMenuEnabled(False)
        self.plot.setXRange(0, 2000, padding=0)
        self.plot.setYRange(-1, 1, padding=0)

        # Рисуем волну
        self.curve = pg.PlotCurveItem(pen=pg.mkPen(color='#569FFF', width=1))
        self.plot.addItem(self.curve)
        
        # Бегунок (Playhead)
        self.playhead = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#FFC107', width=2))
        self.plot.addItem(self.playhead)
        self.playhead.setPos(0)

        layout.addWidget(self.plot)

        self.worker = _StemWaveformWorker(path)
        self.worker.ready.connect(self._on_ready)
        self.worker.failed.connect(lambda msg: print(f"[StemWaveform] {msg}"))
        self.worker.start()

    def _on_ready(self, data: np.ndarray):
        x = np.arange(len(data))
        self.curve.setData(x, data)
        self.total_points = len(data)
        
    def set_position(self, progress_0_to_1: float):
        """Двигает бегунок (progress от 0.0 до 1.0)."""
        if hasattr(self, 'total_points') and self.total_points > 0:
            x_pos = progress_0_to_1 * self.total_points
            self.playhead.setPos(x_pos)