from typing import List
from music21 import stream, note, meter, tempo, articulations


TabEvent = tuple  # (start, end, string, fret)


def export_musicxml(tab_events: List[TabEvent], path: str, bpm: int = 120):
    """Экспорт в MusicXML — файл открывается в Guitar Pro 6/7/8."""
    score = stream.Score()
    part = stream.Part()
    part.append(meter.TimeSignature("4/4"))
    part.append(tempo.MetronomeMark(number=bpm))

    for start, end, string, fret in sorted(tab_events, key=lambda x: x[0]):
        n = note.Note()
        n.quarterLength = max(0.25, (end - start) * (bpm / 60.0))
        n.articulations.append(articulations.Fret(fret))
        n.articulations.append(articulations.String(string))
        part.append(n)

    score.append(part)
    score.write("musicxml", fp=path)
