# ui/track_lane.py
import numpy as np
import librosa
import pyqtgraph as pg

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QSlider, QPushButton, QFrame
)
from PySide6.QtCore import QThread, Signal, Qt

class _WaveformWorker(QThread):
    ready = Signal(np.ndarray, float)
    def __init__(self, path: str, start_sec: float, num_points=2000):
        super().__init__()
        self.path = path
        self.start_sec = start_sec
        self.num_points = num_points

    def run(self):
        try:
            y, sr = librosa.load(self.path, sr=22050, mono=True)
            
            if len(y) > self.num_points:
                step = len(y) // self.num_points
                y = y[:step * self.num_points].reshape(-1, step)
                y_env = np.max(np.abs(y), axis=1)
                for i in range(len(y_env)):
                    if np.mean(y[i]) < 0:
                        y_env[i] = -y_env[i]
            else:
                y_env = y
                
            self.ready.emit(y_env, self.start_sec)
        except Exception as e:
            print(f"Ошибка загрузки волны: {e}")

class TrackLaneWidget(QFrame):
    seek_requested = Signal(float)
    region_changed = Signal(float, float)

    def __init__(self, name: str, path: str, mixer, timeline_widget, is_master=False, start_sec=0.0, end_sec=0.0, total_duration=0.0, color="#569FFF", parent=None):
        super().__init__(parent)
        self.name = name
        self.mixer = mixer
        self.timeline = timeline_widget
        self.is_master = is_master
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.total_duration = total_duration
        self.color = color
        self.num_points = 3000
        
        self.setMinimumHeight(90)
        self.setStyleSheet("""
            TrackLaneWidget {
                background-color: #1c2331;
                border-bottom: 1px solid #2C446A;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        controls = QWidget()
        controls.setFixedWidth(110) 
        c_layout = QVBoxLayout(controls)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        label = QLabel(name.capitalize())
        label.setStyleSheet(f"color: {self.color}; font-weight: bold; font-size: 13px;")
        c_layout.addWidget(label)

        bottom_controls = QHBoxLayout()
        
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        
        mute_btn = QPushButton("M")
        mute_btn.setFixedSize(24, 24)
        mute_btn.setCheckable(True)
        mute_btn.setStyleSheet(self._btn_style("#FF5E5E"))
        mute_btn.toggled.connect(lambda c: self.mixer.set_mute(self.name, c))
        btn_col.addWidget(mute_btn)

        solo_btn = QPushButton("S")
        solo_btn.setFixedSize(24, 24)
        solo_btn.setCheckable(True)
        solo_btn.setStyleSheet(self._btn_style("#569FFF"))
        solo_btn.toggled.connect(lambda c: self.mixer.set_solo(self.name, c))
        btn_col.addWidget(solo_btn)
        
        btn_col.addStretch()
        bottom_controls.addLayout(btn_col)

        vol_slider = QSlider(Qt.Orientation.Vertical)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(100)
        vol_slider.valueChanged.connect(lambda v: self.mixer.set_volume(self.name, v / 100.0))
        bottom_controls.addWidget(vol_slider, 1)

        c_layout.addLayout(bottom_controls)
        layout.addWidget(controls)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#0f1720")
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")
        self.plot.setMenuEnabled(False)
        
        self.plot.setMouseEnabled(x=True, y=False) 
        self.plot.getPlotItem().vb.setAcceptedMouseButtons(Qt.MouseButton.RightButton)
        
        self.plot.getPlotItem().vb.disableAutoRange()
        self.plot.getPlotItem().vb.setAspectLocked(False)
        
        self.plot.setXLink(self.timeline.plot)

        self.curve = pg.PlotDataItem(pen=pg.mkPen(color=self.color, width=1))
        self.curve.setDownsampling(auto=True, method='peak')
        self.curve.setClipToView(True)
        self.plot.addItem(self.curve)
        
        self.playhead = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#FFC107', width=2))
        self.playhead.setZValue(100)
        self.plot.addItem(self.playhead)
        self.playhead.setPos(0)

        if self.is_master:
            self.region = pg.LinearRegionItem(
                brush=(86, 159, 255, 50), 
                pen=pg.mkPen((255, 255, 255, 200), width=2)
            )
            self.region.setZValue(10)
            self.region.setMovable(True)
            
            for line in self.region.lines:
                line.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
                
            self.region.sigRegionChanged.connect(self._on_region_changed)
            self.plot.addItem(self.region)

        self.plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        layout.addWidget(self.plot, 1)

        if self.is_master:
            self.worker = _WaveformWorker(path, self.start_sec, self.num_points)
            self.worker.ready.connect(self._on_waveform_ready)
            self.worker.start()

    def _on_waveform_ready(self, data: np.ndarray, offset: float):
        if not self.is_master:
            return 
            
        duration = self.timeline._duration if self.timeline._duration > 0 else 1.0
        x = np.linspace(0, duration, len(data))
        
        qcolor = pg.mkColor(self.color)
        brush_color = (qcolor.red(), qcolor.green(), qcolor.blue(), 80)
        self.curve.setData(x, data, fillLevel=0, brush=brush_color)

    def update_waveform_data(self, data: np.ndarray, total_duration: float):
        if len(data) == 0: return
        
        y = data[:, 0] if data.ndim > 1 else data
            
        if len(y) > self.num_points:
            step = len(y) // self.num_points
            y_reshaped = y[:step * self.num_points].reshape(-1, step)
            y_env = np.max(np.abs(y_reshaped), axis=1)
            
            means = np.mean(y_reshaped, axis=1)
            y_env = np.where(means < 0, -y_env, y_env)
        else:
            y_env = y
            
        x = np.linspace(0, total_duration, len(y_env))
        qcolor = pg.mkColor(self.color)
        brush_color = (qcolor.red(), qcolor.green(), qcolor.blue(), 80)
        self.curve.setData(x, y_env, fillLevel=0, brush=brush_color)

    def _on_region_changed(self):
        if self.is_master:
            min_x, max_x = self.region.getRegion()
            self.region_changed.emit(min_x, max_x)

    def _on_plot_clicked(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.scenePos()
            if self.plot.sceneBoundingRect().contains(pos):
                mouse_point = self.plot.getPlotItem().vb.mapSceneToView(pos)
                self.seek_requested.emit(mouse_point.x())

    def update_playhead(self, time_sec: float):
        self.playhead.setPos(time_sec)

    def _btn_style(self, checked_color):
        return f"""
            QPushButton {{
                background-color: #2C446A; color: #a0b4d0;
                border: 1px solid #3d5a8a; border-radius: 4px;
                padding: 0px; font-weight: bold; font-size: 11px;
            }}
            QPushButton:hover {{ background-color: #3d5a8a; }}
            QPushButton:checked {{
                background-color: {checked_color}; color: white;
                border: 1px solid {checked_color};
            }}
        """