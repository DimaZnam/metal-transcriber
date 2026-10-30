# ui/fretboard_geometry.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
from ui.fretboard_state import TUNINGS

BOARD_WIDTH = 1550
BOARD_HEIGHT = 280
MARGIN_LEFT = 60
MARGIN_RIGHT = 30
MARGIN_TOP = 40
MARGIN_BOTTOM = 40
NUT_ZONE_WIDTH = 40

@dataclass(frozen=True)
class FretboardGeometry:
    tuning_key: str
    fret_range: int

    @property
    def tuning(self) -> list[int]:
        return TUNINGS.get(self.tuning_key, TUNINGS["standard"])

    @property
    def num_strings(self) -> int:
        return len(self.tuning)

    @property
    def board_width(self) -> float:
        return BOARD_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

    @property
    def board_height(self) -> float:
        return BOARD_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    @property
    def fret_spacing(self) -> float:
        return self.board_width / self.fret_range

    @property
    def string_spacing(self) -> float:
        return self.board_height / (self.num_strings - 1)

    @property
    def nut_x(self) -> float:
        return MARGIN_LEFT

    @property
    def nut_zone_left(self) -> float:
        return MARGIN_LEFT - NUT_ZONE_WIDTH

    def fret_x(self, fret: int) -> float:
        if fret == 0:
            return self.nut_zone_left + NUT_ZONE_WIDTH / 2
        return MARGIN_LEFT + (fret - 1) * self.fret_spacing + self.fret_spacing / 2

    def string_y(self, string_idx: int) -> float:
        return MARGIN_TOP + string_idx * self.string_spacing

    def open_string_y(self, string_idx: int) -> float:
        return self.string_y(string_idx)

    def midi_at(self, string_idx: int, fret: int) -> int:
        return self.tuning[string_idx] + fret

    def get_midi_from_pos(self, x: float, y: float) -> Optional[Tuple[int, int, int]]:
        """
        Возвращает (string_idx, fret, midi) или None.
        Клики чуть выше/ниже струн или правее последнего лада зажимаются к границам.
        """
        # Строка: округляем к ближайшей
        string_idx = round((y - MARGIN_TOP) / self.string_spacing)
        if not (0 <= string_idx < self.num_strings):
            if y < MARGIN_TOP:
                string_idx = 0
            elif y > MARGIN_TOP + self.board_height:
                string_idx = self.num_strings - 1
            else:
                return None

        # Лад: если клик левее порожка - это открытая струна
        if x < self.nut_x:
            if self.nut_zone_left - 10 <= x <= self.nut_x + 5:
                fret = 0
            else:
                return None
        else:
            fret = int((x - self.nut_x) / self.fret_spacing) + 1
            if not (1 <= fret <= self.fret_range):
                if x > self.nut_x + self.fret_range * self.fret_spacing:
                    fret = self.fret_range
                else:
                    return None

        return (string_idx, fret, self.midi_at(string_idx, fret))