"""Repeated-trial analysis for passive CAN button experiments.

A repeated payload is a candidate for investigation, not a decoded signal.
"""
from collections import Counter, defaultdict


def analyze_button_trials(baseline, trials, min_repeats=2):
    """Find non-baseline payloads repeated across independent experiment trials.

    Each trial is an iterable of CAN frame dictionaries. A payload counts at
    most once per trial, regardless of how many frames carried that value.
    """
    if min_repeats < 1:
        raise ValueError("min_repeats must be at least 1")

    baseline_payloads = defaultdict(set)
    baseline_counts = Counter()
    for row in baseline:
        can_id = str(row.get("can_id", "")).upper()
        payload = str(row.get("data", "")).upper().strip()
        baseline_payloads[can_id].add(payload)
        baseline_counts[can_id] += 1

    trial_payloads = []
    frame_counts = Counter()
    all_ids = set(baseline_payloads)
    for trial in trials:
        observed = defaultdict(set)
        for row in trial:
            can_id = str(row.get("can_id", "")).upper()
            payload = str(row.get("data", "")).upper().strip()
            observed[can_id].add(payload)
            frame_counts[can_id] += 1
            all_ids.add(can_id)
        trial_payloads.append(observed)

    results = []
    trial_count = len(trial_payloads)
    for can_id in sorted(all_ids):
        occurrences = Counter()
        for observed in trial_payloads:
            for payload in observed.get(can_id, set()):
                if payload not in baseline_payloads.get(can_id, set()):
                    occurrences[payload] += 1

        candidates = [
            {
                "payload": payload,
                "repeat_count": count,
                "repeat_ratio": count / trial_count if trial_count else 0.0,
                "candidate": count >= min_repeats,
            }
            for payload, count in sorted(
                occurrences.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        results.append({
            "can_id": can_id,
            "baseline_frames": baseline_counts[can_id],
            "trial_count": trial_count,
            "experiment_frames": frame_counts[can_id],
            "baseline_variants": len(baseline_payloads.get(can_id, set())),
            "candidate_payloads": candidates,
            "candidate": any(item["candidate"] for item in candidates),
        })

    return sorted(
        results,
        key=lambda item: (
            not item["candidate"],
            -max(
                (entry["repeat_count"] for entry in item["candidate_payloads"]),
                default=0,
            ),
            item["can_id"],
        ),
    )
