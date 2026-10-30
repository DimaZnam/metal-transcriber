# ui/fretboard.py
from __future__ import annotations
from typing import List, Optional, Set, Tuple
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget, QToolTip
import time

from core.theory import TheoryAnalyzer, pc_to_name
from ui.fretboard_geometry import BOARD_HEIGHT, BOARD_WIDTH, FretboardGeometry
from ui.fretboard_state import FretboardState, TUNINGS
from ui.theme import (
    ACCENT_COLOR, BG_COLOR, PLAYED_COLOR, ROOT_BORDER_COLOR,
    get_chord_color, get_octave_color
)

NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

class _FretboardCanvas(QWidget):
    noteClicked = Signal(int)
    def __init__(self, owner: "FretboardWidget"):
        super().__init__()
        self.owner = owner
        self.setMouseTracking(True)

    def paintEvent(self, event): self.owner._paint(self)
    def mousePressEvent(self, event): self.owner._on_click(event)
    def mouseMoveEvent(self, event): self.owner._on_hover(event)
    def leaveEvent(self, event): self.owner._on_leave(event)

class FretboardWidget(QWidget):
    noteClicked = Signal(int)

    def __init__(self, mini: bool = False):
        super().__init__()
        self.mini = mini
        self._state = FretboardState()
        self._geom = FretboardGeometry(self._state.tuning, self._state.fret_range)
        
        self._static_image: Optional[QImage] = None
        self._cache_key: Optional[Tuple] = None
        
        self._transcribed: List[Tuple[float, float, int, int]] = []
        self._active: Set[int] = set()
        self._hover: Optional[Tuple[int, int]] = None
        self._last_scroll_time = 0.0

        self.setMinimumSize(500, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.canvas = _FretboardCanvas(self)
        self.canvas.noteClicked.connect(self.noteClicked.emit)
        
        if self.mini:
            self.canvas.setFixedSize(500, 100)
        else:
            self.canvas.setFixedSize(int(BOARD_WIDTH * self._state.zoom), int(BOARD_HEIGHT * self._state.zoom))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll)

    def set_state(self, state: FretboardState) -> None:
        self._state = state
        self._geom = FretboardGeometry(state.tuning, state.fret_range)
        if not self.mini:
            self.canvas.setFixedSize(int(BOARD_WIDTH * state.zoom), int(BOARD_HEIGHT * state.zoom))
        
        self._cache_key = None 
        self.canvas.update()

    def get_state(self) -> FretboardState: return self._state

    def display_tab_notes(self, notes, current_pos=None):
        new_active = set()
        if current_pos is not None:
            for i, (s, e, _, _) in enumerate(notes or []):
                if s - 0.05 <= current_pos <= e + 0.05: 
                    new_active.add(i)
        
        notes_changed = self._transcribed != notes
        
        if notes_changed:
            self._transcribed = notes or []
            self._cache_key = None

        if self._active != new_active or notes_changed:
            self._active = new_active
            self.canvas.update()
            
            # Авто-скролл, чтобы не дергать его слишком часто (раз в 0.5 сек)
            if self._active and not self.mini and time.perf_counter() - self._last_scroll_time > 0.5:
                self._scroll_to_active()

    def _scroll_to_active(self):
        if not self._active: return
        frets = [self._transcribed[i][3] for i in self._active if i < len(self._transcribed)]
        if not frets: return
        
        avg_fret = sum(frets) / len(frets)
        g = self._geom
        target_x = g.fret_x(int(avg_fret))
        target_pixel = target_x * self._state.zoom
        
        scrollbar = self.scroll.horizontalScrollBar()
        view_width = self.scroll.viewport().width()
        
        target_scroll = int(target_pixel - view_width / 2)
        target_scroll = max(0, min(target_scroll, scrollbar.maximum()))
        
        if abs(scrollbar.value() - target_scroll) > 100:
            scrollbar.setValue(target_scroll)
            self._last_scroll_time = time.perf_counter()

    def clear(self):
        self._transcribed = []
        self._active = set()
        self._cache_key = None
        self.canvas.update()

    def _ensure_static(self) -> None:
        key = (self._state, self._geom, len(self._transcribed))
        
        if self._static_image is None or self._cache_key != key:
            w = self.canvas.width()
            h = self.canvas.height()
            self._static_image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            self._static_image.fill(QColor(BG_COLOR))
            
            p = QPainter(self._static_image)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            
            scale = min(w / BOARD_WIDTH, h / BOARD_HEIGHT)
            p.scale(scale, scale)
            
            self._draw_board(p)
            self._draw_layers(p)
            self._draw_transcribed_static(p)
            p.end()
            self._cache_key = key

    def _paint(self, canvas: QWidget) -> None:
        self._ensure_static()
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.drawImage(0, 0, self._static_image)
        
        w = canvas.width()
        h = canvas.height()
        scale = min(w / BOARD_WIDTH, h / BOARD_HEIGHT)
        p.scale(scale, scale)
        
        if not self.mini:
            self._paint_dynamic(p)
        p.end()

    def _draw_board(self, p: QPainter) -> None:
        g = self._geom
        s = self._state

        p.setBrush(QColor("#2a2221"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(g.nut_x, 40, g.board_width, g.board_height))

        p.setBrush(QColor("#d0d0d0"))
        p.setPen(Qt.PenStyle.NoPen)
        
        for f in {3, 5, 7, 9, 15, 17, 19, 21}:
            if f > s.fret_range: continue
            x = g.nut_x + (f - 1) * g.fret_spacing + g.fret_spacing / 2
            y = 40 + g.board_height / 2
            p.drawEllipse(QRectF(x - 6, y - 6, 12, 12))
            
        for f in (12, 24):
            if f > s.fret_range: continue
            x = g.nut_x + (f - 1) * g.fret_spacing + g.fret_spacing / 2
            y1 = 40 + g.board_height / 3
            y2 = 40 + g.board_height * 2 / 3
            p.drawEllipse(QRectF(x - 6, y1 - 6, 12, 12))
            p.drawEllipse(QRectF(x - 6, y2 - 6, 12, 12))

        for f in range(s.fret_range + 1):
            x = g.nut_x + f * g.fret_spacing
            p.setPen(QPen(QColor("#e0e0e0") if f == 0 else QColor("#a0a0a0"), 4 if f == 0 else 1))
            p.drawLine(int(x), 40, int(x), int(40 + g.board_height))
            
            if 1 <= f <= s.fret_range:
                p.setPen(QColor("#a0b4d0"))
                p.setFont(QFont("Segoe UI", 11))
                text_center_x = g.fret_x(f)
                p.drawText(QRectF(text_center_x - 15, 40 - 35, 30, 18), Qt.AlignmentFlag.AlignCenter, str(f))

        for i in range(g.num_strings):
            y = g.string_y(i)
            p.setPen(QPen(QColor("#c0c0c0"), 1 + (g.num_strings - 1 - i) * 0.5))
            p.drawLine(int(g.nut_x), int(y), int(g.nut_x + g.board_width), int(y))
            p.setPen(QColor("#a0b4d0"))
            p.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            
            string_names = ["E","B","G","D","A","E"] if g.num_strings == 6 else ["G","D","A","E"]
            p.drawText(QRectF(5, y - 10, 20, 20), Qt.AlignmentFlag.AlignCenter, string_names[i])

    def _get_text_to_draw(self, midi: int, in_chord: bool, in_scale: bool) -> str:
        s = self._state
        pc = midi % 12
        
        if in_chord:
            c_info = TheoryAnalyzer.get_chord_info(s.chord_root, s.chord_type)
            if s.display == "notes":
                return c_info.get("pcs_to_spelling", {}).get(pc, NOTES[pc])
            else:
                deg = c_info.get("pcs_to_degree", {}).get(pc, "")
                return deg if deg else pc_to_name(pc, s.chord_root)
                
        if in_scale:
            s_info = TheoryAnalyzer.get_scale_info(s.scale_root, s.scale_type)
            if s.display == "notes":
                return s_info.get("pcs_to_spelling", {}).get(pc, NOTES[pc])
            else:
                deg = s_info.get("pcs_to_degree", {}).get(pc, "")
                return deg if deg else pc_to_name(pc, s.chord_root)
                
        return pc_to_name(pc, s.chord_root)

    def _color_for(self, midi: int, degree: str) -> str:
        s = self._state
        if s.color_mode == "degrees":
            return get_chord_color(degree)
        else:
            return get_octave_color(midi // 12 - 1)

    def _draw_layers(self, p: QPainter) -> None:
        s = self._state
        g = self._geom
        
        s_info = TheoryAnalyzer.get_scale_info(s.scale_root, s.scale_type) if s.show_scale else {}
        c_info = TheoryAnalyzer.get_chord_info(s.chord_root, s.chord_type) if s.show_chord else {}
        
        scale_pcs = s_info.get("scale_pcs", set())
        chord_pcs = c_info.get("chord_pcs", set())
        
        scale_root_pc = s_info.get("tonic_pc", -1)
        chord_root_pc = c_info.get("root_pc", -1)

        for string_idx in range(g.num_strings):
            for fret in range(0, s.fret_range + 1):
                midi = g.midi_at(string_idx, fret)
                pc = midi % 12
                
                in_scale = pc in scale_pcs
                in_chord = pc in chord_pcs
                
                if not in_scale and not in_chord:
                    continue

                x, y = g.fret_x(fret), g.string_y(string_idx)
                
                is_root = (in_chord and pc == chord_root_pc) or (not in_chord and in_scale and pc == scale_root_pc)
                
                if in_scale and in_chord and s.show_scale and s.show_chord:
                    s_deg = s_info["pcs_to_degree"].get(pc, "R")
                    s_color = self._color_for(midi, s_deg)
                    p.setBrush(QColor(s_color))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(QRectF(x - 14, y - 14, 28, 28))
                    
                    c_deg = c_info["pcs_to_degree"].get(pc, "R")
                    c_color = self._color_for(midi, c_deg)
                    p.setBrush(QColor(c_color))
                    p.setPen(QPen(QColor(0, 0, 0, 120), 1))
                    p.drawEllipse(QRectF(x - 8, y - 8, 16, 16))
                    
                else:
                    if in_chord:
                        deg = c_info["pcs_to_degree"].get(pc, "R")
                    else:
                        deg = s_info["pcs_to_degree"].get(pc, "R")
                    color = self._color_for(midi, deg)
                    p.setBrush(QColor(color))
                    p.setPen(QPen(QColor(0, 0, 0, 120), 1))
                    p.drawEllipse(QRectF(x - 12, y - 12, 24, 24))

                if is_root:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(QColor(ROOT_BORDER_COLOR), 2))
                    p.drawRoundedRect(QRectF(x - 15, y - 15, 30, 30), 4, 4)

                if not self.mini:
                    text = self._get_text_to_draw(midi, in_chord, in_scale)
                    if text:
                        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        p.setPen(QColor(0, 0, 0, 220))
                        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)]:
                            p.drawText(QRectF(x - 15 + dx, y - 8 + dy, 30, 16), Qt.AlignmentFlag.AlignCenter, text)
                        p.setPen(QColor("#FFFFFF"))
                        p.drawText(QRectF(x - 15, y - 8, 30, 16), Qt.AlignmentFlag.AlignCenter, text)

    def _draw_transcribed_static(self, p: QPainter) -> None:
        s = self._state
        g = self._geom
        if not s.show_transcribed or not self._transcribed:
            return

        for i, (start_t, end_t, string_num, fret) in enumerate(self._transcribed):
            if i in self._active: continue
            
            string_idx = string_num - 1
            if not (0 <= string_idx < g.num_strings) or not (0 <= fret <= s.fret_range): 
                continue
            
            x, y = g.fret_x(fret), g.string_y(string_idx)
            midi = g.midi_at(string_idx, fret)
            pc = midi % 12
            
            text = self._get_text_to_draw(midi, False, False)
            
            # ИСПОЛЬЗУЕМ НЕОНОВО-ГОЛУБОЙ (CYAN) ВМЕСТО ФИОЛЕТОВОГО
            p.setBrush(QColor(0, 229, 255, 150)) 
            p.setPen(QPen(QColor("#00E5FF"), 1.5))
            p.drawEllipse(QRectF(x - 10, y - 10, 20, 20))
            
            if not self.mini:
                p.setPen(QColor("#000000"))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                p.drawText(QRectF(x - 10, y - 6, 20, 12), Qt.AlignmentFlag.AlignCenter, text)

    def _paint_dynamic(self, p: QPainter) -> None:
        s = self._state
        g = self._geom
        
        s_info = TheoryAnalyzer.get_scale_info(s.scale_root, s.scale_type) if s.show_scale else {}
        c_info = TheoryAnalyzer.get_chord_info(s.chord_root, s.chord_type) if s.show_chord else {}
        
        # 1. Наведение мыши
        if self._hover is not None:
            h_string, h_fret = self._hover
            x, y = g.fret_x(h_fret), g.string_y(h_string)
            midi = g.midi_at(h_string, h_fret)
            
            is_visible = (midi % 12 in s_info.get("scale_pcs", set())) or (midi % 12 in c_info.get("chord_pcs", set()))
            
            if not is_visible:
                p.setBrush(QColor(255, 255, 255, 30))
                p.setPen(QPen(QColor(255, 255, 255, 100), 1, Qt.PenStyle.DashLine))
                p.drawEllipse(QRectF(x - 12, y - 12, 24, 24))
                
                p.setPen(QColor(255, 255, 255))
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                pc = midi % 12
                if s.display == "notes":
                    text = pc_to_name(pc, s.chord_root)
                else:
                    s_info_local = TheoryAnalyzer.get_scale_info(s.scale_root, s.scale_type)
                    text = s_info_local.get("pcs_to_degree", {}).get(pc, NOTES[pc])
                p.drawText(QRectF(x - 15, y - 8, 30, 16), Qt.AlignmentFlag.AlignCenter, text)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#FFFFFF"), 2.5))
                p.drawEllipse(QRectF(x - 16, y - 16, 32, 32))

        # 2. Активные ноты (сейчас играют)
        if s.show_transcribed and self._active:
            for i in self._active:
                if i >= len(self._transcribed): continue
                _, _, string_num, fret = self._transcribed[i]
                string_idx = string_num - 1
                if not (0 <= string_idx < g.num_strings) or not (0 <= fret <= s.fret_range): 
                    continue
                
                x, y = g.fret_x(fret), g.string_y(string_idx)
                midi = g.midi_at(string_idx, fret)
                pc = midi % 12
                
                text = self._get_text_to_draw(midi, pc in c_info.get("chord_pcs", set()), pc in s_info.get("scale_pcs", set()))
                if not text: text = pc_to_name(pc, s.chord_root)
                
                # ЗОЛОТАЯ НОТА С БЕЛОЙ ОБВОДКОЙ
                p.setBrush(QColor("#FFC107")) 
                p.setPen(QPen(QColor("#FFFFFF"), 2))
                p.drawEllipse(QRectF(x - 13, y - 13, 26, 26))
                
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 193, 7, 120), 4))
                p.drawEllipse(QRectF(x - 16, y - 16, 32, 32))
                
                p.setPen(QColor("#000000"))
                p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                p.drawText(QRectF(x - 15, y - 8, 30, 16), Qt.AlignmentFlag.AlignCenter, text)

        # 3. Клик по грифу
        if s.clicked_pos is not None:
            string_idx, fret = s.clicked_pos
            x, y = g.fret_x(fret), g.string_y(string_idx)
            midi = g.midi_at(string_idx, fret)
            
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(QColor("#000000"), 2))
            p.drawEllipse(QRectF(x - 14, y - 14, 28, 28))
            
            p.setPen(QColor("#000000"))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            pc = midi % 12
            note_name = pc_to_name(pc, s.chord_root)
            p.drawText(QRectF(x - 15, y - 9, 30, 18), Qt.AlignmentFlag.AlignCenter, note_name)

    def _logical(self, event) -> Tuple[float, float]:
        w = self.canvas.width()
        h = self.canvas.height()
        scale = min(w / BOARD_WIDTH, h / BOARD_HEIGHT)
        return (event.position().x() / scale, event.position().y() / scale)

    def _on_click(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton: return
        x, y = self._logical(event)
        
        hit = self._geom.get_midi_from_pos(x, y)
        if hit is not None:
            string_idx, fret, midi = hit
            self._state = self._state.replace(clicked_pos=(string_idx, fret))
            
            print(f"[{time.perf_counter():.4f}] Fretboard: Клик по струне {string_idx+1}, лад {fret} (MIDI {midi})")
            self.noteClicked.emit(midi)
            
        self.canvas.update()
        QTimer.singleShot(1500, self._clear_pin)

    def _clear_pin(self) -> None:
        self._state = self._state.replace(clicked_pos=None)
        self.canvas.update()

    def _on_hover(self, event) -> None:
        x, y = self._logical(event)
        hit = self._geom.get_midi_from_pos(x, y)
        if hit is None:
            if self._hover is not None:
                self._hover = None
                self.canvas.update()
            return
        
        string_idx, fret, midi = hit
        if (string_idx, fret) != self._hover:
            self._hover = (string_idx, fret)
            self.canvas.update()
            
        if not self.mini:
            pc = midi % 12
            note_name = pc_to_name(pc, self._state.chord_root)
            octave = midi // 12 - 1
            
            lines = [f"{note_name}{octave}"]
            
            s_info = TheoryAnalyzer.get_scale_info(self._state.scale_root, self._state.scale_type)
            if s_info and pc in s_info["scale_pcs"]:
                lines.append(f"Гамма: {s_info['pcs_to_degree'][pc]}")
                
            c_info = TheoryAnalyzer.get_chord_info(self._state.chord_root, self._state.chord_type)
            if c_info and pc in c_info["chord_pcs"]:
                lines.append(f"Аккорд: {c_info['pcs_to_degree'][pc]}")
                
            QToolTip.showText(
                event.globalPosition().toPoint(),
                "\n".join(lines),
                self.canvas
            )

    def _on_leave(self, event) -> None:
        self._hover = None
        self.canvas.update()