# ui/mini_fretboard.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.fretboard import FretboardWidget

class MiniFretboardWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Мини-гриф")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 130)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.fretboard = FretboardWidget(mini=True)
        layout.addWidget(self.fretboard)
        self.setStyleSheet("background-color: #1c2331;")