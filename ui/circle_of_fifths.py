# ui/circle_of_fifths.py
import math
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QMouseEvent
from core.theory import CIRCLE_MAJOR, CIRCLE_MINOR, TheoryAnalyzer

class CircleOfFifthsWidget(QWidget):
    key_selected = Signal(str, str) # (root, mode)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 400)
        self.current_index = 0
        self.hover_index = -1

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#1c2331"))

        center = self.rect().center()
        radius = min(self.width(), self.height()) / 2 - 20
        inner_radius = radius * 0.6

        for i in range(12):
            angle_start = i * 30 - 90
            angle_span = 30
            mid_angle = math.radians(angle_start + angle_span / 2)

            # Внешнее кольцо (мажор)
            if i == self.current_index:
                color_major = QColor("#569FFF")
            elif i == self.hover_index:
                color_major = QColor("#7ab3ff")
            else:
                color_major = QColor("#2C446A")

            painter.setBrush(QBrush(color_major))
            painter.setPen(QPen(QColor("#1c2331"), 1))
            rect_outer = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
            painter.drawPie(rect_outer, int(-angle_start * 16 - 480), int(-angle_span * 16))

            # Внутреннее кольцо (минор)
            if i == self.current_index:
                color_minor = QColor("#9C27B0")
            elif i == self.hover_index:
                color_minor = QColor("#BA68C8")
            else:
                color_minor = QColor("#1c2331")

            painter.setBrush(QBrush(color_minor))
            painter.setPen(QPen(QColor("#1c2331"), 1))
            rect_inner = QRectF(center.x() - inner_radius, center.y() - inner_radius, inner_radius * 2, inner_radius * 2)
            painter.drawPie(rect_inner, int(-angle_start * 16 - 480), int(-angle_span * 16))

            # Текст мажор
            text_radius = (radius + inner_radius) / 2
            tx = center.x() + text_radius * math.cos(mid_angle)
            ty = center.y() + text_radius * math.sin(mid_angle)

            painter.setPen(QColor("#FFFFFF") if i == self.current_index else QColor("#a0b4d0"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            text_rect = QRectF(tx - 25, ty - 10, 50, 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, CIRCLE_MAJOR[i])

            # Текст минор
            text_radius_minor = inner_radius * 0.7
            tx_m = center.x() + text_radius_minor * math.cos(mid_angle)
            ty_m = center.y() + text_radius_minor * math.sin(mid_angle)
            painter.setPen(QColor("#FFFFFF") if i == self.current_index else QColor("#a0b4d0"))
            painter.setFont(QFont("Segoe UI", 8))
            text_rect_m = QRectF(tx_m - 20, ty_m - 8, 40, 16)
            painter.drawText(text_rect_m, Qt.AlignmentFlag.AlignCenter, CIRCLE_MINOR[i])

            # Ключевые знаки
            sig, sig_str = TheoryAnalyzer.get_key_signature(CIRCLE_MAJOR[i])
            painter.setPen(QColor("#FFC107"))
            painter.setFont(QFont("Segoe UI", 7))
            text_rect_sig = QRectF(tx - 15, ty + 12, 30, 12)
            painter.drawText(text_rect_sig, Qt.AlignmentFlag.AlignCenter, sig_str)

    def mouseMoveEvent(self, event: QMouseEvent):
        center = self.rect().center()
        dx = event.position().x() - center.x()
        dy = event.position().y() - center.y()
        r = math.sqrt(dx*dx + dy*dy)
        radius = min(self.width(), self.height()) / 2 - 20
        inner_radius = radius * 0.6

        if inner_radius <= r <= radius:
            angle = math.degrees(math.atan2(dy, dx))
            index = round((90 - angle) / 30) % 12
            if index != self.hover_index:
                self.hover_index = index
                self.update()
        else:
            if self.hover_index != -1:
                self.hover_index = -1
                self.update()

    def leaveEvent(self, event):
        self.hover_index = -1
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.hover_index != -1:
            self.current_index = self.hover_index
            root_major = CIRCLE_MAJOR[self.current_index]
            root_minor = CIRCLE_MINOR[self.current_index].replace("m", "")
            self.key_selected.emit(root_major, "major")
            self.key_selected.emit(root_minor, "minor")
            self.update()

class CircleOfFifthsWindow(QWidget):
    key_selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Квинтовый круг")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(450, 500)
        self.setStyleSheet("background-color: #1c2331;")

        layout = QVBoxLayout(self)
        self.circle = CircleOfFifthsWidget()
        self.circle.key_selected.connect(self.key_selected.emit)
        layout.addWidget(self.circle)

        legend = QLabel(
            "Цвета: синий — мажор, фиолетовый — минор.\n"
            "Цифры — количество диезов (#) или бемолей (b).\n"
            "Клик по сектору выбирает тональность."
        )
        legend.setStyleSheet("color: #a0b4d0; font-size: 11px; padding: 10px;")
        layout.addWidget(legend)

    def update_key(self, root, mode):
        pass