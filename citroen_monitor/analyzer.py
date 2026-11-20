"""Incremental, passive CAN traffic statistics.

This module does not decode vehicle signals. It only summarizes observed frames.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


def _payload(data: str) -> bytes:
    parts = data.split()
    try:
        return bytes(int(part, 16) for part in parts)
    except ValueError:
        return b""


@dataclass
class IdStats:
    count: int = 0
    last_data: str = ""
    last_payload: bytes = b""
    changed_bytes: Counter = field(default_factory=Counter)
    transitions: int = 0


class CanAnalyzer:
    """Collect frame and per-ID statistics without transmitting anything."""

    def __init__(self) -> None:
        self.total_frames = 0
        self.by_id: Dict[str, IdStats] = {}
        self._frame_types = Counter()

    def reset(self) -> None:
        self.total_frames = 0
        self.by_id.clear()
        self._frame_types.clear()

    def add(self, frame: dict) -> None:
        can_id = str(frame.get("can_id", "")).upper()
        data = str(frame.get("data", "")).upper().strip()
        frame_type = str(frame.get("frame_type", ""))
        payload = _payload(data)

        stats = self.by_id.setdefault(can_id, IdStats())
        if stats.count and stats.last_payload != payload:
            stats.transitions += 1
            width = max(len(stats.last_payload), len(payload))
            for index in range(width):
                old = stats.last_payload[index] if index < len(stats.last_payload) else None
                new = payload[index] if index < len(payload) else None
                if old != new:
                    stats.changed_bytes[index] += 1

        stats.count += 1
        stats.last_data = data
        stats.last_payload = payload
        self.total_frames += 1
        self._frame_types[frame_type] += 1

    def snapshot(self) -> List[dict]:
        """Return rows sorted by observed frame count, highest first."""
        rows = []
        for can_id, stats in self.by_id.items():
            changed = ", ".join(str(i) for i, _ in stats.changed_bytes.most_common())
            rows.append({
                "can_id": can_id,
                "count": stats.count,
                "share": (100.0 * stats.count / self.total_frames) if self.total_frames else 0.0,
                "transitions": stats.transitions,
                "changed_bytes": changed or "—",
                "last_data": stats.last_data,
            })
        return sorted(rows, key=lambda row: (-row["count"], row["can_id"]))

    def summary(self) -> dict:
        return {
            "total_frames": self.total_frames,
            "unique_ids": len(self.by_id),
            "frame_types": dict(self._frame_types),
        }


def compare_capture_rows(baseline: Iterable[dict], experiment: Iterable[dict]) -> List[dict]:
    """Compare payload variation per CAN ID between two CSV-like row iterables.

    This is a descriptive comparison, not proof that a frame belongs to an action.
    """
    def collect(rows):
        result = {}
        for row in rows:
            can_id = str(row.get("can_id", "")).upper()
            payload = str(row.get("data", "")).upper().strip()
            result.setdefault(can_id, Counter())[payload] += 1
        return result

    left, right = collect(baseline), collect(experiment)
    output = []
    for can_id in sorted(set(left) | set(right)):
        before, after = left.get(can_id, Counter()), right.get(can_id, Counter())
        output.append({
            "can_id": can_id,
            "baseline_frames": sum(before.values()),
            "experiment_frames": sum(after.values()),
            "baseline_variants": len(before),
            "experiment_variants": len(after),
            "new_payloads": sorted(set(after) - set(before)),
            "missing_payloads": sorted(set(before) - set(after)),
        })
    return output
