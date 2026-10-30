# ui/timeline.py
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt, Signal

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

class TimelineWidget(QWidget):
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(35) 
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0) 
        layout.setSpacing(10)

        spacer = QWidget()
        spacer.setFixedWidth(110) 
        layout.addWidget(spacer)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#1c2331")
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.setMenuEnabled(False)
        self.plot.hideButtons()
        self.plot.setYRange(0, 1, padding=0)
        
        self.plot.getPlotItem().vb.disableAutoRange()
        self.plot.getPlotItem().vb.setAspectLocked(False)
        
        self.plot.hideAxis('left')
        self.plot.setAxisItems({'bottom': TimeAxis(orientation='bottom')})
        
        self.playhead = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#FFC107', width=2))
        self.playhead.setZValue(100)
        self.plot.addItem(self.playhead)
        
        self.plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        
        layout.addWidget(self.plot, 1)
        self._duration = 0.0

    def set_duration(self, duration: float):
        self._duration = duration
        self.plot.getPlotItem().vb.setLimits(xMin=0, xMax=self._duration)
        self.plot.setXRange(0, self._duration, padding=0)

    def set_playhead(self, time_sec: float):
        self.playhead.setPos(time_sec)

    def _on_plot_clicked(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.scenePos()
            if self.plot.sceneBoundingRect().contains(pos):
                mouse_point = self.plot.getPlotItem().vb.mapSceneToView(pos)
                self.seek_requested.emit(mouse_point.x())