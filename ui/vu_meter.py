# ui/vu_meter.py
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor
from PySide6.QtCore import Qt


class VUMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 20)
        self.level_l = 0.0
        self.level_r = 0.0
        self.level_l_smooth = 0.0
        self.level_r_smooth = 0.0

    def set_levels(self, levels: list):
        self.level_l = levels[0]
        self.level_r = levels[1]
        
        # Плавное затухание для красивого визуального эффекта
        self.level_l_smooth = max(self.level_l, self.level_l_smooth * 0.85)
        self.level_r_smooth = max(self.level_r, self.level_r_smooth * 0.85)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Фон VU-метра
        painter.setBrush(QColor("#0f1720"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, self.width(), self.height())

        # Функция отрисовки одной полоски (канала)
        def draw_bar(y, level):
            max_w = self.width() - 4
            w = int(max_w * min(level, 1.0))
            if w > 0:
                # Цвет от зеленого к красному (по мере роста громкости)
                if w < max_w * 0.7: 
                    color = QColor("#4CAF50") # Зеленый
                elif w < max_w * 0.9: 
                    color = QColor("#FFC107") # Желтый
                else: 
                    color = QColor("#F44336") # Красный
                
                painter.setBrush(color)
                painter.drawRect(2, y, w, 6)

        # Рисуем два канала (L и R)
        draw_bar(2, self.level_l_smooth)
        draw_bar(11, self.level_r_smooth)