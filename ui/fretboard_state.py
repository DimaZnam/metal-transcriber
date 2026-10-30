# ui/fretboard_state.py
from __future__ import annotations
import json
import os
from dataclasses import asdict, dataclass, replace
from typing import Optional, Tuple

TUNINGS: dict[str, list[int]] = {
    "standard":   [64, 59, 55, 50, 45, 40],
    "bass":       [43, 38, 33, 28], # Стандартный бас (G D A E)
    "drop_d":     [64, 59, 55, 50, 45, 38],
    "dadgad":     [62, 57, 55, 50, 45, 38],
    "half_down":  [63, 58, 54, 49, 44, 39],
}

TUNING_LABELS = {
    "standard": "Standard (E)",
    "bass": "Bass (E)",
    "drop_d": "Drop D",
    "dadgad": "DADGAD",
    "half_down": "Half-step Down",
}

FRET_RANGES = (12, 15, 24)

@dataclass(frozen=True)
class FretboardState:
    chord_root: str = "C"
    scale_root: str = "C"
    display: str = "notes"
    color_mode: str = "octaves"
    chord_type: str = "major"
    scale_type: str = "Major (Ionian)"
    tuning: str = "standard"
    fret_range: int = 24
    show_transcribed: bool = True
    show_scale: bool = True
    show_chord: bool = True
    caged_shape: str = "All"
    zoom: float = 1.0
    clicked_pos: Optional[Tuple[int, int]] = None

    def to_query_string(self) -> str:
        return (
            f"chordRoot={self.chord_root}&scaleRoot={self.scale_root}"
            f"&display={self.display}&colorMode={self.color_mode}"
            f"&chord={self.chord_type}&scale={self.scale_type}"
            f"&tuning={self.tuning}&range={self.fret_range}"
        )

    @classmethod
    def from_query_string(cls, s: str) -> "FretboardState":
        params = dict(p.split("=", 1) for p in s.split("&") if "=" in p)
        mapping = {
            "chordRoot": "chord_root", "scaleRoot": "scale_root",
            "display": "display", "colorMode": "color_mode", "chord": "chord_type",
            "scale": "scale_type", "tuning": "tuning",
        }
        kwargs = {dst: params[src] for src, dst in mapping.items() if src in params}
        if "range" in params:
            try: kwargs["fret_range"] = int(params["range"])
            except ValueError: pass
        return cls(**kwargs)

    STATE_PATH = os.path.expanduser("~/.metal_transcriber/fretboard.json")

    def save(self, path: str | None = None) -> None:
        path = path or self.STATE_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str | None = None) -> "FretboardState":
        path = path or cls.STATE_PATH
        if not os.path.exists(path): return cls()
        try:
            with open(path, encoding="utf-8") as f: data = json.load(f)
            valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**valid)
        except Exception:
            return cls()

    def replace(self, **kwargs) -> "FretboardState":
        return replace(self, **kwargs)