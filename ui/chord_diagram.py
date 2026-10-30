# ui/chord_diagram.py
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QMouseEvent

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

class ChordDiagramWidget(QWidget):
    noteClicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.root_pc = -1
        self.chord_pcs = set()
        self.pcs_to_degree = {}
        self.chord_name = ""
        self.notes_list = []
        
        self.setMinimumHeight(150)
        
        self.setMouseTracking(True)

        self.cx = 0
        self.cy = 0
        self.r_inner = 0
        self.r_outer = 0
        self.hover_pc = -1

    def set_chord(self, root_pc, chord_pcs, pcs_to_degree, chord_name, notes_list):
        self.root_pc = root_pc
        self.chord_pcs = chord_pcs
        self.pcs_to_degree = pcs_to_degree
        self.chord_name = chord_name
        self.notes_list = notes_list
        self.update()

    def _get_pc_from_pos(self, x, y):
        dx = x - self.cx
        dy = self.cy - y
        r = math.sqrt(dx*dx + dy*dy)
        
        if self.r_inner <= r <= self.r_outer:
            angle = math.degrees(math.atan2(dy, dx))
            return round((90 - angle) / 30) % 12
        return -1

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.root_pc != -1:
            pc = self._get_pc_from_pos(event.position().x(), event.position().y())
            if pc != self.hover_pc:
                self.hover_pc = pc
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hover_pc = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.root_pc != -1:
            pc = self._get_pc_from_pos(event.position().x(), event.position().y())
            if pc != -1:
                self.noteClicked.emit(60 + pc)

    def paintEvent(self, event):
        if self.root_pc == -1 or not self.chord_pcs:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # 1. Фон карточки
        painter.setBrush(QBrush(QColor("#212a3b")))
        painter.setPen(QPen(QColor("#3d5a8a"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        # 2. Геометрия (Жестко 110)
        size = 110
        self.cx = 15 + size / 2
        self.cy = self.height() / 2
        
        rect = QRectF(self.cx - size/2, self.cy - size/2, size, size)
        self.r_inner = size * 0.15
        self.r_outer = size / 2

        # 3. Круг
        painter.setBrush(QBrush(QColor("#141a24")))
        painter.setPen(QPen(QColor("#3d5a8a"), 2))
        painter.drawEllipse(rect)

        for i in range(12):
            pc = i
            start_angle = 90 - (i * 30) + 15
            span_angle = -30 

            is_hovered = (pc == self.hover_pc)
            is_active = (pc in self.chord_pcs)

            if is_active:
                color = QColor("#00BCD4") if pc == self.root_pc else QColor("#FFFFFF")
                if is_hovered: color = color.lighter(120)
            else:
                color = QColor("#2C446A") if is_hovered else QColor("#1c2331")

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#2C446A"), 1))
            painter.drawPie(rect, int(start_angle * 16), int(span_angle * 16))

        inner_rect = QRectF(self.cx - self.r_inner, self.cy - self.r_inner, self.r_inner * 2, self.r_inner * 2)
        painter.setBrush(QBrush(QColor("#1c2331")))
        painter.setPen(QPen(QColor("#3d5a8a"), 1))
        painter.drawEllipse(inner_rect)

        # 4. Текст в круге
        for i in range(12):
            pc = i
            center_angle_rad = math.radians(90 - (i * 30))
            text_radius = (self.r_inner + self.r_outer) / 2
            tx = self.cx + text_radius * math.cos(center_angle_rad)
            ty = self.cy - text_radius * math.sin(center_angle_rad)

            if pc in self.chord_pcs:
                painter.setPen(QColor("#000000"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            elif pc == self.hover_pc:
                painter.setPen(QColor("#FFFFFF"))
                painter.setFont(QFont("Segoe UI", 8))
            else:
                painter.setPen(QColor("#5a6a8a"))
                painter.setFont(QFont("Segoe UI", 8))

            text_rect = QRectF(tx - 15, ty - 8, 30, 16)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, NOTES[pc])

        # 5. Текст справа (Жестко фиксированные координаты)
        start_x = 145 # Начинаем текст всегда с этого X
        name_h = 30
        notes_h = 25
        deg_h = 20
        total_h = name_h + notes_h + deg_h
        
        # Центрируем блок относительно круга
        start_y = self.cy - (total_h / 2)

        # Название
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.drawText(QRectF(start_x, start_y, self.width() - start_x, name_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.chord_name)

        # Ноты и ступени
        col_width = 38
        note_start_y = start_y + name_h

        for i, (note_name, degree) in enumerate(self.notes_list):
            col_x = start_x + i * col_width
            
            # Нота
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Medium))
            painter.drawText(QRectF(col_x, note_start_y, col_width, notes_h), Qt.AlignmentFlag.AlignCenter, note_name)
            
            # Ступень
            painter.setPen(QColor("#a0b4d0"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(QRectF(col_x, note_start_y + notes_h, col_width, deg_h), Qt.AlignmentFlag.AlignCenter, degree)