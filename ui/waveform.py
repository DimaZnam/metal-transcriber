# ui/waveform.py
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget, QScrollBar
from PySide6.QtCore import Signal, Qt
import librosa

class TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            if v < 0:
                strings.append("")
                continue
            m, s = divmod(v, 60)
            if spacing < 1.0:
                strings.append(f"{int(m)}:{s:06.3f}")
            else:
                strings.append(f"{int(m)}:{int(s):02d}")
        return strings

class CustomPlotWidget(pg.PlotWidget):
    seek_requested = Signal(float)
    region_changed = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setBackground("#1c2331")
        self.showGrid(x=True, y=False, alpha=0.3)
        self.setMouseEnabled(x=False, y=False)
        self.getPlotItem().getAxis('left').setWidth(40)
        
        self.setMenuEnabled(False)
        self.hideButtons()

        self.getPlotItem().vb.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.setAxisItems({'bottom': TimeAxis(orientation='bottom')})
        self.setYRange(-1, 1, padding=0)

        self.curve = pg.PlotDataItem(pen=pg.mkPen(color='#569FFF', width=1))
        self.curve.setDownsampling(auto=True, method='peak')
        self.curve.setClipToView(True)
        self.addItem(self.curve)
        
        self.playhead = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#000000', width=3))
        self.playhead.setZValue(20)
        self.addItem(self.playhead)
        
        self.region = pg.LinearRegionItem(
            brush=(86, 159, 255, 50), 
            pen=pg.mkPen((255, 255, 255, 200), width=2)
        )
        self.region.setZValue(10)
        self.region.setMovable(False)
        self.region.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        for line in self.region.lines:
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        
        self.addItem(self.region)
        
        self._press_pos = None
        self._is_dragging = False
        self._drag_mode = None
        self._start_x = 0.0
        self._duration = 0.0

        self.region.sigRegionChanged.connect(self._on_region_changed)

    def wheelEvent(self, event):
        x_range = self.getPlotItem().viewRange()[0]
        x_min, x_max = x_range
        x_center = (x_min + x_max) / 2
        width = x_max - x_min

        if event.angleDelta().y() > 0:
            scale = 0.8
        else:
            scale = 1.25

        new_width = width * scale
        
        if new_width < 0.05 or new_width > self._duration * 1.5:
            return

        new_min = max(0, x_center - new_width / 2)
        new_max = min(self._duration, x_center + new_width / 2)

        self.setXRange(new_min, new_max, padding=0)
        event.accept()

    def set_duration(self, duration):
        self._duration = duration
        self.getPlotItem().vb.setLimits(xMin=0, xMax=self._duration)
        self.setXRange(0, self._duration, padding=0)

    def _get_x_from_event(self, event):
        scene_pos = self.mapToScene(event.pos())
        view_pos = self.getPlotItem().vb.mapSceneToView(scene_pos)
        return view_pos.x()

    def _get_threshold(self):
        x_min, x_max = self.getPlotItem().viewRange()[0]
        width = self.getPlotItem().vb.width()
        if width <= 0:
            return 0.1
        units_per_pixel = (x_max - x_min) / width
        return 10 * units_per_pixel

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            x_val = self._get_x_from_event(event)
            threshold = self._get_threshold()
            min_x, max_x = self.region.getRegion()
            min_x, max_x = min(min_x, max_x), max(max_x, min_x)
            
            self._press_pos = event.pos()
            self._is_dragging = False
            self._start_x = x_val

            if abs(x_val - min_x) < threshold:
                self._drag_mode = 'left'
                self.region.lines[0].setPen(pg.mkPen('#FFC107', width=4))
            elif abs(x_val - max_x) < threshold:
                self._drag_mode = 'right'
                self.region.lines[1].setPen(pg.mkPen('#FFC107', width=4))
            else:
                self._drag_mode = 'new'
            
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_pos is not None:
            if (event.pos() - self._press_pos).manhattanLength() > 3:
                self._is_dragging = True
            
            if self._is_dragging:
                x_val = self._get_x_from_event(event)
                min_x, max_x = self.region.getRegion()
                
                if self._drag_mode == 'new':
                    self.region.setRegion([self._start_x, x_val])
                elif self._drag_mode == 'left':
                    self.region.setRegion([min(x_val, max_x), max(x_val, max_x)])
                elif self._drag_mode == 'right':
                    self.region.setRegion([min(min_x, x_val), max(min_x, x_val)])
        else:
            x_val = self._get_x_from_event(event)
            threshold = self._get_threshold()
            min_x, max_x = self.region.getRegion()
            min_x, max_x = min(min_x, max_x), max(max_x, min_x)
            
            self.region.lines[0].setPen(pg.mkPen((255, 255, 255, 200), width=2))
            self.region.lines[1].setPen(pg.mkPen((255, 255, 255, 200), width=2))

            if abs(x_val - min_x) < threshold:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.region.lines[0].setPen(pg.mkPen('#FFC107', width=4))
            elif abs(x_val - max_x) < threshold:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.region.lines[1].setPen(pg.mkPen('#FFC107', width=4))
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            x_val = self._get_x_from_event(event)
            
            self.region.lines[0].setPen(pg.mkPen((255, 255, 255, 200), width=2))
            self.region.lines[1].setPen(pg.mkPen((255, 255, 255, 200), width=2))

            if not self._is_dragging:
                self.region.setRegion([x_val, x_val])
                self.seek_requested.emit(x_val)
            
            self._press_pos = None
            self._is_dragging = False
            self._drag_mode = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _on_region_changed(self):
        min_x, max_x = self.region.getRegion()
        self.region_changed.emit(min_x, max_x)


class WaveformWidget(QWidget):
    region_changed = Signal(float, float)
    seek_requested = Signal(float)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot_widget = CustomPlotWidget()
        self.plot_widget.seek_requested.connect(self.seek_requested.emit)
        self.plot_widget.region_changed.connect(self.region_changed.emit)
        
        layout.addWidget(self.plot_widget)
        
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        layout.addWidget(self.scrollbar)
        
        self._duration = 0
        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        self.plot_widget.getPlotItem().vb.sigXRangeChanged.connect(self._on_view_changed)

    def load_audio(self, path: str):
        y, sr = librosa.load(path, sr=22050, mono=True)
        self._duration = len(y) / sr
        
        num_points = 15000
        if len(y) > num_points:
            step = len(y) // num_points
            y_plot = y[:step * num_points].reshape(-1, step)
            y_plot = np.max(np.abs(y_plot), axis=1) * np.sign(np.mean(y_plot, axis=1))
        else:
            y_plot = y
            
        x = np.linspace(0, self._duration, len(y_plot))
        self.plot_widget.curve.setData(x, y_plot, fillLevel=0, brush=(86, 159, 255, 100))
        self.plot_widget.set_duration(self._duration)
        
        self.plot_widget.region.setRegion((0, self._duration))
        self._update_scrollbar()

    def set_playhead(self, time_sec: float):
        self.plot_widget.playhead.setPos(time_sec)

    def get_region(self) -> tuple:
        min_x, max_x = self.plot_widget.region.getRegion()
        start = max(0.0, min(min_x, max_x))
        end = min(self._duration, max(max_x, min_x))
        return start, end

    def _on_view_changed(self, *args):
        self._update_scrollbar()

    def _update_scrollbar(self):
        if self._duration <= 0: return
        x_range = self.plot_widget.getPlotItem().vb.viewRange()[0]
        x_min, x_max = x_range
        visible = x_max - x_min
        
        self.scrollbar.blockSignals(True)
        self.scrollbar.setMinimum(0)
        
        if visible >= self._duration - 0.1:
            self.scrollbar.setMaximum(0)
            self.scrollbar.setPageStep(0)
            self.scrollbar.setValue(0)
            self.scrollbar.setEnabled(False)
        else:
            self.scrollbar.setEnabled(True)
            self.scrollbar.setMaximum(int(self._duration * 1000))
            self.scrollbar.setPageStep(int(visible * 1000))
            self.scrollbar.setValue(int(x_min * 1000))
            
        self.scrollbar.blockSignals(False)

    def _on_scrollbar_changed(self, value):
        if self._duration <= 0 or not self.scrollbar.isEnabled(): return
        visible = self.scrollbar.pageStep() / 1000.0
        x_min = value / 1000.0
        x_max = x_min + visible
        self.plot_widget.setXRange(x_min, x_max, padding=0)