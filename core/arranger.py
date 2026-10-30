# core/arranger.py
from typing import List, Tuple, Dict, Any
import math

NoteEvent = Tuple[float, float, int]
TabEvent = Tuple[float, float, int, int]

TUNINGS = {
    "guitar": [40, 45, 50, 55, 59, 64],
    "bass":   [28, 33, 38, 43]
}

MAX_FRET = 24
MAX_STRETCH = 7 # Увеличен для соло

def _playable_configs(midis: List[int], tuning: List[int]) -> List[Tuple[Tuple[int, int], ...]]:
    per_note = []
    for midi in midis:
        opts = []
        for s_idx, open_midi in enumerate(tuning):
            fret = midi - open_midi
            if 0 <= fret <= MAX_FRET:
                opts.append((s_idx, fret))
        if not opts:
            return []
        per_note.append(opts)

    configs = []

    def backtrack(i: int, used_strings: set, current: list):
        if i == len(per_note):
            frets = [f for _, f in current]
            if not frets or max(frets) - min(frets) <= MAX_STRETCH:
                configs.append(tuple(current))
            return
        for s, f in per_note[i]:
            if s in used_strings:
                continue
            used_strings.add(s)
            current.append((s, f))
            backtrack(i + 1, used_strings, current)
            current.pop()
            used_strings.remove(s)

    backtrack(0, set(), [])
    return configs

def _transition_cost(prev, curr) -> float:
    prev_frets = [f for _, f in prev]
    curr_frets = [f for _, f in curr]
    center_prev = sum(prev_frets) / len(prev_frets) if prev_frets else 0
    center_curr = sum(curr_frets) / len(curr_frets) if curr_frets else 0

    move = abs(center_curr - center_prev)
    
    # Штраф за большие скачки (больше 7 ладов) смягчен, чтобы соло могло уходить на высокие лады
    zone_penalty = 0 if move <= 7 else 1.0 * move
    
    stretch_curr = max(curr_frets) - min(curr_frets) if curr_frets else 0
    stretch_penalty = max(0, stretch_curr - 5) * 1.0
    
    open_bonus = -1.0 * sum(1 for f in curr_frets if f == 0)

    return move + zone_penalty + stretch_penalty + open_bonus

def arrange_with_dp(notes: List[NoteEvent], instrument: str = "guitar") -> List[TabEvent]:
    if not notes:
        return []
    
    tuning = TUNINGS.get(instrument, TUNINGS["guitar"])
    num_strings = len(tuning)

    groups: Dict[float, List[int]] = {}
    for start, _end, midi in notes:
        groups.setdefault(round(start, 3), []).append(midi)

    sorted_times = sorted(groups.keys())
    filtered_times: List[float] = []
    filtered_configs: List[List[Tuple[Tuple[int, int], ...]]] = []

    for t in sorted_times:
        cfgs = _playable_configs(groups[t], tuning)
        if cfgs:
            filtered_times.append(t)
            filtered_configs.append(cfgs)

    if not filtered_configs:
        return []

    dp: List[Dict[Any, float]] = [{cfg: 0.0 for cfg in filtered_configs[0]}]
    parent: List[Dict[Any, Any]] = [{cfg: None for cfg in filtered_configs[0]}]

    for i in range(1, len(filtered_configs)):
        curr_dp = {}
        curr_parent = {}
        for cfg_curr in filtered_configs[i]:
            best_cost = math.inf
            best_prev = None
            for cfg_prev, cost_prev in dp[i - 1].items():
                total = cost_prev + _transition_cost(cfg_prev, cfg_curr)
                if total < best_cost:
                    best_cost = total
                    best_prev = cfg_prev
            curr_dp[cfg_curr] = best_cost
            curr_parent[cfg_curr] = best_prev
        dp.append(curr_dp)
        parent.append(curr_parent)

    best_last = min(dp[-1], key=dp[-1].get)
    path = [best_last]
    for i in range(len(dp) - 1, 0, -1):
        prev = parent[i][path[-1]]
        if prev is None: break
        path.append(prev)
    path.reverse()

    result: List[TabEvent] = []
    onset_to_duration = {}
    for start, end, _ in notes:
        onset_to_duration.setdefault(round(start, 3), end - start)

    for t, config in zip(filtered_times, path):
        if not config: continue
        dur = onset_to_duration.get(t, 0.1)
        for s_idx, fret in config:
            string_number = num_strings - s_idx
            result.append((t, t + dur, string_number, fret))

    return result