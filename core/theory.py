"""Музыкальная теория: лады, аккорды, энгармонизм, степени."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Set, Tuple

# ---------- Ноты и буквы ----------------------------------------------

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Интервал (в полутонах) -> (сдвиг буквы, метка ступени)
INTERVAL_TO_DEGREE: Dict[int, Tuple[int, str]] = {
    0: (0, "R"),
    1: (1, "b2"), 2: (1, "2"),
    3: (2, "b3"), 4: (2, "3"),
    5: (3, "4"),
    6: (4, "b5"), 7: (4, "5"), 8: (4, "#5"),
    8: (5, "b6"), 9: (5, "6"),
    10: (6, "b7"), 11: (6, "7"),
    12: (0, "8"),
    13: (1, "b9"), 14: (1, "9"), 15: (1, "#9"),
    17: (3, "11"), 18: (3, "#11"),
    20: (5, "b13"), 21: (5, "13"),
}


def pc_from_name(name: str) -> int:
    """'C' -> 0, 'Bb' -> 10, 'F#' -> 6."""
    if name in SHARP_NAMES:
        return SHARP_NAMES.index(name)
    if name in FLAT_NAMES:
        return FLAT_NAMES.index(name)
    raise ValueError(f"Unknown note: {name}")


def spell_note(root: str, semitones: int, context: str = "chord") -> str:
    """
    Возвращает энгармонически корректное имя ноты.
    spell_note("Bb", 3) → "Db"; spell_note("A", 4) → "C#".
    context используется для выбора (но реально всё решает буква + акциденталь).
    """
    root_letter = root[0].upper()
    if root_letter not in LETTER_PC:
        # Совсем экзотика — возвращаем sharp-нотацию
        return SHARP_NAMES[(pc_from_name(root) + semitones) % 12]

    root_idx = LETTERS.index(root_letter)
    letter_offset, _ = INTERVAL_TO_DEGREE.get(semitones, (0, "?"))
    target_idx = (root_idx + letter_offset) % 7
    target_letter = LETTERS[target_idx]

    target_pc = (pc_from_name(root) + semitones) % 12
    natural_pc = LETTER_PC[target_letter]
    diff = (target_pc - natural_pc) % 12
    if diff > 6:
        diff -= 12

    suffix = {0: "", 1: "#", -1: "b", 2: "##", -2: "bb"}.get(diff)
    if suffix is None:
        return SHARP_NAMES[target_pc]
    return target_letter + suffix


def pc_to_name(pc: int, root: str) -> str:
    """Диез или бемоль — по тональности корня."""
    is_flat = root == "F" or root.endswith("b")
    return FLAT_NAMES[pc] if is_flat else SHARP_NAMES[pc]


def get_degree_name(semitones: int) -> str:
    return INTERVAL_TO_DEGREE.get(semitones, f"({semitones})")[1]


# ---------- Лады -------------------------------------------------------

SCALES: Dict[str, List[int]] = {
    "Major (Ionian)":           [0, 2, 4, 5, 7, 9, 11],
    "Natural Minor (Aeolian)":  [0, 2, 3, 5, 7, 8, 10],
    "Harmonic Minor":           [0, 2, 3, 5, 7, 8, 11],
    "Melodic Minor":            [0, 2, 3, 5, 7, 9, 11],
    "Dorian":                   [0, 2, 3, 5, 7, 9, 10],
    "Phrygian":                 [0, 1, 3, 5, 7, 8, 10],
    "Lydian":                   [0, 2, 4, 6, 7, 9, 11],
    "Mixolydian":               [0, 2, 4, 5, 7, 9, 10],
    "Locrian":                  [0, 1, 3, 5, 6, 8, 10],
    "Phrygian Dominant":        [0, 1, 4, 5, 7, 8, 10],
    "Pentatonic Major":         [0, 2, 4, 7, 9],
    "Pentatonic Minor":         [0, 3, 5, 7, 10],
    "Blues":                    [0, 3, 5, 6, 7, 10],
}


# ---------- Аккорды ----------------------------------------------------

# (полутоны от корня, метки ступеней)
CHORD_INTERVALS: Dict[str, Tuple[List[int], List[str]]] = {
    # Triads
    "major":   ([0, 4, 7], ["R", "3", "5"]),
    "minor":   ([0, 3, 7], ["R", "b3", "5"]),
    "dim":     ([0, 3, 6], ["R", "b3", "b5"]),
    "aug":     ([0, 4, 8], ["R", "3", "#5"]),
    # Sevenths
    "maj7":    ([0, 4, 7, 11], ["R", "3", "5", "7"]),
    "min7":    ([0, 3, 7, 10], ["R", "b3", "5", "b7"]),
    "7":       ([0, 4, 7, 10], ["R", "3", "5", "b7"]),
    "m7b5":    ([0, 3, 6, 10], ["R", "b3", "b5", "b7"]),
    "dim7":    ([0, 3, 6, 9], ["R", "b3", "b5", "bb7"]),
    "mMaj7":   ([0, 3, 7, 11], ["R", "b3", "5", "7"]),
    # Extended
    "9":       ([0, 4, 7, 10, 14], ["R", "3", "5", "b7", "9"]),
    "min9":    ([0, 3, 7, 10, 14], ["R", "b3", "5", "b7", "9"]),
    "maj9":    ([0, 4, 7, 11, 14], ["R", "3", "5", "7", "9"]),
    "11":      ([0, 4, 7, 10, 14, 17], ["R", "3", "5", "b7", "9", "11"]),
    "min11":   ([0, 3, 7, 10, 14, 17], ["R", "b3", "5", "b7", "9", "11"]),
    "13":      ([0, 4, 7, 10, 14, 21], ["R", "3", "5", "b7", "9", "13"]),
    "min13":   ([0, 3, 7, 10, 14, 21], ["R", "b3", "5", "b7", "9", "13"]),
    "maj13":   ([0, 4, 7, 11, 14, 21], ["R", "3", "5", "7", "9", "13"]),
    # Altered
    "7b5":     ([0, 4, 6, 10], ["R", "3", "b5", "b7"]),
    "7#5":     ([0, 4, 8, 10], ["R", "3", "#5", "b7"]),
    "7b9":     ([0, 4, 7, 10, 13], ["R", "3", "5", "b7", "b9"]),
    "7#9":     ([0, 4, 7, 10, 15], ["R", "3", "5", "b7", "#9"]),
    "7#11":    ([0, 4, 7, 10, 18], ["R", "3", "5", "b7", "#11"]),
    "7b13":    ([0, 4, 7, 10, 20], ["R", "3", "5", "b7", "b13"]),
    # Suspended
    "sus2":    ([0, 2, 7], ["R", "2", "5"]),
    "sus4":    ([0, 5, 7], ["R", "4", "5"]),
    "7sus4":   ([0, 5, 7, 10], ["R", "4", "5", "b7"]),
    # Power
    "5":       ([0, 7], ["R", "5"]),
}

CHORD_CATEGORIES: Dict[str, List[str]] = {
    "triads":    ["major", "minor", "dim", "aug"],
    "sevenths":  ["maj7", "min7", "7", "m7b5", "dim7", "mMaj7"],
    "extended":  ["9", "min9", "maj9", "11", "min11", "13", "min13", "maj13"],
    "altered":   ["7b5", "7#5", "7b9", "7#9", "7#11", "7b13"],
    "suspended": ["sus2", "sus4", "7sus4", "5"],
}


# ---------- Квинтовый круг ---------------------------------------------

CIRCLE_MAJOR = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]
CIRCLE_MINOR = ["Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "Bbm", "Fm", "Cm", "Gm", "Dm"]

KEY_SIGNATURES: Dict[str, int] = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6,
    "Db": -5, "Ab": -4, "Eb": -3, "Bb": -2, "F": -1,
    "Am": 0, "Em": 1, "Bm": 2, "F#m": 3, "C#m": 4, "G#m": 5, "D#m": 6,
    "Bbm": -5, "Fm": -4, "Cm": -3, "Gm": -2, "Dm": -1,
}


# ---------- CAGED ------------------------------------------------------

CAGED_SHAPES = {
    "C": {"root_string": 5, "shape": {5: 0, 4: 1, 3: 0, 2: 2, 1: 3}},
    "A": {"root_string": 5, "shape": {5: 0, 4: 2, 3: 2, 2: 2, 1: 0}},
    "G": {"root_string": 6, "shape": {6: 0, 5: 2, 4: 0, 3: 0, 2: 0, 1: 3}},
    "E": {"root_string": 6, "shape": {6: 0, 5: 2, 4: 2, 3: 1, 2: 0, 1: 0}},
    "D": {"root_string": 4, "shape": {4: 0, 3: 2, 2: 3, 1: 2}},
}


# ---------- Анализ -----------------------------------------------------

class TheoryAnalyzer:
    @staticmethod
    def estimate_key(midi_notes: List[int]) -> str:
        if not midi_notes:
            return "C major"
        pcs = [n % 12 for n in midi_notes]
        tonic_pc = Counter(pcs).most_common(1)[0][0]
        tonic = SHARP_NAMES[tonic_pc]
        if (tonic_pc + 3) % 12 in pcs and (tonic_pc + 4) % 12 not in pcs:
            mode = "minor"
        else:
            mode = "major"
        return f"{tonic} {mode}"

    @staticmethod
    def get_scale_info(root_note: str, scale_name: str) -> Dict:
        if root_note not in SHARP_NAMES + FLAT_NAMES or scale_name not in SCALES:
            return {}
        root_pc = pc_from_name(root_note)
        intervals = SCALES[scale_name]
        scale_pcs: Set[int] = set()
        pcs_to_degree: Dict[int, str] = {}
        pcs_to_spelling: Dict[int, str] = {}
        for semitones in intervals:
            pc = (root_pc + semitones) % 12
            scale_pcs.add(pc)
            pcs_to_degree[pc] = get_degree_name(semitones)
            pcs_to_spelling[pc] = spell_note(root_note, semitones, "scale")
        return {
            "scale_pcs": scale_pcs,
            "pcs_to_degree": pcs_to_degree,
            "pcs_to_spelling": pcs_to_spelling,
            "tonic_pc": root_pc,
        }

    @staticmethod
    def get_chord_info(root_note: str, chord_type: str) -> Dict:
        if root_note not in SHARP_NAMES + FLAT_NAMES or chord_type not in CHORD_INTERVALS:
            return {}
        root_pc = pc_from_name(root_note)
        intervals, degrees = CHORD_INTERVALS[chord_type]
        chord_pcs: Set[int] = set()
        pcs_to_degree: Dict[int, str] = {}
        pcs_to_spelling: Dict[int, str] = {}
        for semitones, degree in zip(intervals, degrees):
            pc = (root_pc + semitones) % 12
            chord_pcs.add(pc)
            if pc not in pcs_to_degree:
                pcs_to_degree[pc] = degree
                pcs_to_spelling[pc] = spell_note(root_note, semitones, "chord")
        return {
            "chord_pcs": chord_pcs,
            "pcs_to_degree": pcs_to_degree,
            "pcs_to_spelling": pcs_to_spelling,
            "root_pc": root_pc,
        }

    @staticmethod
    def get_caged_positions(root_note: str, tuning: List[int]) -> List[Tuple[str, Dict[int, int]]]:
        if root_note not in SHARP_NAMES + FLAT_NAMES:
            return []
        root_pc = pc_from_name(root_note)
        positions = []
        for shape_name, data in CAGED_SHAPES.items():
            root_string = data["root_string"]
            open_string_pc = tuning[root_string - 1] % 12
            root_fret = (root_pc - open_string_pc) % 12
            pos_dict = {s: f + root_fret for s, f in data["shape"].items()}
            positions.append((shape_name, pos_dict))
        return positions

    @staticmethod
    def get_diatonic_chords(root_note: str, scale_name: str) -> List[Tuple[str, str, str]]:
        if root_note not in SHARP_NAMES + FLAT_NAMES:
            return []
        root_pc = pc_from_name(root_note)
        if "Major" in scale_name or "Lydian" in scale_name:
            formula = [("I",0,"major"),("ii",2,"minor"),("iii",4,"minor"),
                       ("IV",5,"major"),("V",7,"major"),("vi",9,"minor"),("vii°",11,"dim")]
        elif "Minor" in scale_name or "Aeolian" in scale_name:
            formula = [("i",0,"minor"),("ii°",2,"dim"),("III",3,"major"),
                       ("iv",5,"minor"),("v",7,"minor"),("VI",8,"major"),("VII",10,"major")]
        else:
            formula = [("I",0,"major"),("ii",2,"minor"),("iii",4,"minor"),
                       ("IV",5,"major"),("V",7,"major"),("vi",9,"minor"),("vii°",11,"dim")]
        out = []
        for degree, semitones, ctype in formula:
            pc = (root_pc + semitones) % 12
            out.append((degree, pc_to_name(pc, root_note), ctype))
        return out

    @staticmethod
    def get_key_signature(key: str) -> Tuple[int, str]:
        sig = KEY_SIGNATURES.get(key, 0)
        if sig == 0:
            return 0, "0"
        return sig, (f"{sig}#" if sig > 0 else f"{-sig}b")