# ui/fretboard_window.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from ui.fretboard import FretboardWidget

class FretboardWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Гриф — отдельное окно")
        self.resize(1200, 450)
        self.setStyleSheet("background-color: #1c2331;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.fretboard = FretboardWidget()
        layout.addWidget(self.fretboard)