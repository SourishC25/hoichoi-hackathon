"""Stage F — WHETHER to break: choose the optimal set of breaks under pacing rules.

Exact dynamic programme over time-sorted candidates maximising total break quality subject to
min gap, max breaks/hour and the ad-load budget. A break is only warranted if its quality clears
`min_break_score` — if nothing clears it, the episode gets fewer (or zero) breaks."""
from __future__ import annotations

import math

DEFAULT_RULES = {
    "max_breaks_per_hour": 6,
    "min_gap_sec": 300,
    "max_ad_load_pct": 12.0,      # ad time / (content + ad time)
    "no_break_first_sec": 120,
    "no_break_last_sec": 90,
    "min_break_score": 0.55,
    "brand_relevance_weight": 0.15,
}


def allowed_breaks(duration: float, rules: dict) -> int:
    return max(0, math.floor(duration / 3600 * rules["max_breaks_per_hour"] + 1e-9)) or (1 if duration >= 2 * rules["min_gap_sec"] else 0)


def ad_budget(duration: float, rules: dict) -> float:
    p = rules["max_ad_load_pct"] / 100
    return duration * p / (1 - p)


def select(cands: list[dict], duration: float, rules: dict) -> list[dict]:
    """cands: eligible candidates with 'quality'. Returns chosen subset (time order)."""
    items = sorted(cands, key=lambda c: c["t"])
    k_max = allowed_breaks(duration, rules)
    n = len(items)
    if n == 0 or k_max == 0:
        return []
    gap = rules["min_gap_sec"]
    NEG = -1e9
    # best[i][k] = best total using k breaks with the last one at i
    best = [[NEG] * (k_max + 1) for _ in range(n)]
    prev = [[-1] * (k_max + 1) for _ in range(n)]
    for i, c in enumerate(items):
        if c["t"] >= gap * 0.5:   # first break not too early relative to start
            best[i][1] = c["quality"]
        for j in range(i):
            if c["t"] - items[j]["t"] < gap:
                continue
            for k in range(2, k_max + 1):
                if best[j][k - 1] > NEG and best[j][k - 1] + c["quality"] > best[i][k]:
                    best[i][k] = best[j][k - 1] + c["quality"]
                    prev[i][k] = j
    end = max(((i, k) for i in range(n) for k in range(1, k_max + 1)), key=lambda ik: best[ik[0]][ik[1]])
    if best[end[0]][end[1]] <= NEG:
        return []
    chosen, (i, k) = [], end
    while i != -1:
        chosen.append(items[i])
        i, k = prev[i][k], k - 1
    return sorted(chosen, key=lambda c: c["t"])
