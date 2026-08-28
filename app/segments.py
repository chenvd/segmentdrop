from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


TICKS_PER_MS = 10_000
SIGNED_CHAPTER = re.compile(
    r"^(Credits End|Recap|Recap End|Preview|Preview End) \(TheIntroDB\) "
    r"\[TheIntroDB:([^\]]+)\]$"
)


def ticks_to_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value >= 0:
        return round(value / TICKS_PER_MS)
    return None


def parse_emby_segments(chapters: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in ("intro", "recap", "credits", "preview")}
    native: dict[str, list[int]] = defaultdict(list)
    signed: dict[str, dict[str, list[int]]] = {
        "recap": {"start": [], "end": []},
        "preview": {"start": [], "end": []},
    }
    credit_ends: list[int] = []

    for chapter in sorted(chapters or [], key=lambda c: c.get("StartPositionTicks") or 0):
        position = ticks_to_ms(chapter.get("StartPositionTicks"))
        if position is None:
            continue
        marker = chapter.get("MarkerType")
        if marker in {"IntroStart", "IntroEnd", "CreditsStart"}:
            native[marker].append(position)
            continue
        match = SIGNED_CHAPTER.fullmatch(str(chapter.get("Name") or ""))
        if not match:
            continue
        label, _marker_id = match.groups()
        if label == "Credits End":
            credit_ends.append(position)
        elif label.startswith("Recap"):
            signed["recap"]["end" if label.endswith("End") else "start"].append(position)
        elif label.startswith("Preview"):
            signed["preview"]["end" if label.endswith("End") else "start"].append(position)

    result["intro"] = _pair_ordered(native["IntroStart"], native["IntroEnd"])
    result["credits"] = _pair_ordered(native["CreditsStart"], credit_ends)
    for kind in ("recap", "preview"):
        result[kind] = _pair_ordered(signed[kind]["start"], signed[kind]["end"])
    return result


def _pair_ordered(starts: list[int], ends: list[int]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    remaining_ends = list(ends)
    for start in starts:
        end_index = next((i for i, end in enumerate(remaining_ends) if end >= start), None)
        end = remaining_ends.pop(end_index) if end_index is not None else None
        pairs.append({"start_ms": start, "end_ms": end, "source": "emby"})
    pairs.extend({"start_ms": None, "end_ms": end, "source": "emby"} for end in remaining_ends)
    return sorted(
        pairs,
        key=lambda value: value["start_ms"] if value["start_ms"] is not None else value["end_ms"] or 0,
    )
