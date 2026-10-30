# ui/theme.py
from typing import Dict

BG_COLOR = "#1c2331"
ACCENT_COLOR = "#569FFF"
PANEL_COLOR = "#2C446A"
BORDER_COLOR = "#3d5a8a"
PLAYED_COLOR = "#FFC107"
ROOT_BORDER_COLOR = "#FBC02D"

DEGREE_COLORS: Dict[str, str] = {
    "R":   "#E57373", "b2":  "#BA68C8", "2":  "#BA68C8",
    "b9":  "#BA68C8", "9":  "#BA68C8", "#9": "#BA68C8",
    "b3":  "#64B5F6", "3":  "#64B5F6",
    "4":   "#FFB74D", "11": "#FFB74D", "#11": "#FFB74D",
    "b5":  "#81C784", "5":  "#81C784", "#5": "#81C784",
    "b6":  "#F06292", "6":  "#F06292",
    "b13": "#F06292", "13": "#F06292",
    "b7":  "#FFD54F", "7":  "#FFD54F",
}
_DEFAULT_DEGREE_COLOR = "#E24A4A"

# Приглушенные цвета для октав
OCTAVE_COLORS: Dict[int, str] = {
    1: "#B39DDB",   # лавандовый
    2: "#90CAF9",   # голубой
    3: "#A5D6A7",   # мятный
    4: "#FFE082",   # желтый
    5: "#F48FB1",   # розовый
    6: "#EF9A9A",   # красный
}

def get_chord_color(degree: str) -> str:
    return DEGREE_COLORS.get(degree, _DEFAULT_DEGREE_COLOR)

def get_octave_color(octave: int) -> str:
    return OCTAVE_COLORS.get(octave, "#90A4AE")