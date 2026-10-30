# ui/fretboard_legend.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtGui import QColor, QPixmap, QPainter

from ui.fretboard_state import FretboardState
from ui.theme import DEGREE_COLORS, BORDER_COLOR

def _dot(color: str, size: int = 12) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(QColor("transparent"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QColor(BORDER_COLOR))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix

class FretboardLegend(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(6)

    def set_state(self, state: FretboardState) -> None:
        # Очистить старые элементы
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Так как режим октав удален, всегда показываем ступени
        items = [(deg, color) for deg, color in DEGREE_COLORS.items()]

        for label, color in items:
            dot = QLabel()
            dot.setPixmap(_dot(color))
            self._layout.addWidget(dot)
            
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #e8e8e8; font-size: 11px;")
            self._layout.addWidget(lbl)

        self._layout.addStretch()