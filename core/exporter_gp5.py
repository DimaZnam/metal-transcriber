# core/exporter_gp5.py
from typing import List
import guitarpro
from guitarpro.models import (
    Song, Track, Measure, MeasureHeader, Voice, Beat, Note,
    Duration, TimeSignature, GuitarString,
    BeatStatus, NoteType,
)

TabEvent = tuple  # (start, end, string, fret)

TICKS_PER_QUARTER = 960
BEATS_PER_MEASURE = 4
MEASURE_TICKS = TICKS_PER_QUARTER * BEATS_PER_MEASURE

# Строи (1-я струна - самая тонкая)
TUNINGS = {
    "guitar": [64, 59, 55, 50, 45, 40],  # E4 B3 G3 D3 A2 E2
    "bass":   [43, 38, 33, 28]           # G2 D2 A1 E1
}

def _duration_value(ticks: int) -> int:
    """Преобразует длительность в тиках в value для Duration (1, 2, 4, 8, 16, 32)."""
    if ticks >= 3840: return 1     # целая
    if ticks >= 1920: return 2     # половинная
    if ticks >= 960:  return 4     # четвертная
    if ticks >= 480:  return 8     # восьмая
    if ticks >= 240:  return 16    # шестнадцатая
    return 32                      # тридцать вторая


def export_gp5(
    tab_events: List[TabEvent],
    path: str,
    tempo: int = 120,
    title: str = "Transcribed by Metal Transcriber",
    instrument: str = "guitar",
):
    """
    Экспорт табулатуры в Guitar Pro 5 (.gp5).
    Ноты автоматически разбиваются на такты 4/4.
    """
    song = Song(tempo=tempo, title=title)
    song.measureHeaders = []
    song.tracks = []

    tuning = TUNINGS.get(instrument, TUNINGS["guitar"])
    track_name = "Guitar" if instrument == "guitar" else "Bass"

    track = Track(
        song=song,
        number=1,
        name=track_name,
        strings=[
            GuitarString(number=i, value=v)
            for i, v in enumerate(tuning, start=1)
        ],
    )
    song.tracks.append(track)
    track.measures = []

    measure_duration = BEATS_PER_MEASURE * 60.0 / tempo  # секунд в такте

    # 1. Группируем ноты по тактам
    measures_data = {}
    for start, end, string, fret in sorted(tab_events, key=lambda x: x[0]):
        measure_idx = int(start // measure_duration)
        rel_sec = start - measure_idx * measure_duration
        rel_tick = int(round(rel_sec * TICKS_PER_QUARTER * tempo / 60.0))
        rel_tick = min(max(rel_tick, 0), MEASURE_TICKS - 1)

        dur_sec = max(0.05, end - start)
        dur_ticks = int(round(dur_sec * TICKS_PER_QUARTER * tempo / 60.0))

        measures_data.setdefault(measure_idx, []).append(
            (rel_tick, _duration_value(dur_ticks), string, fret)
        )

    max_measure = max(measures_data.keys()) if measures_data else 0

    # 2. Создаём такты и наполняем их нотами
    for idx in range(max_measure + 1):
        # ИСПРАВЛЕНИЕ: number теперь передаётся в MeasureHeader
        header = MeasureHeader(
            number=idx + 1,
            start=idx * MEASURE_TICKS,
            timeSignature=TimeSignature(BEATS_PER_MEASURE, Duration(4)),
        )
        song.measureHeaders.append(header)

        # ИСПРАВЛЕНИЕ: Measure принимает header, а не number
        measure = Measure(track=track, header=header)
        track.measures.append(measure)

        voice = Voice(measure=measure)
        measure.voices.append(voice)

        for rel_tick, dur_val, string, fret in sorted(
            measures_data.get(idx, []), key=lambda x: x[0]
        ):
            beat = Beat(
                voice=voice,
                start=rel_tick,
                duration=Duration(value=dur_val),
                status=BeatStatus.normal,
            )
            note = Note(
                beat=beat,
                value=fret,
                string=string,
                type=NoteType.normal,
            )
            beat.notes.append(note)
            voice.beats.append(beat)

    guitarpro.write(song, path)