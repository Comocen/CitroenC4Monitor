"""Repeated-trial and bit-level analysis for passive CAN experiments.

Results are statistical candidates only; they are not decoded vehicle signals.
"""
from collections import Counter, defaultdict


def _payload_bytes(value):
    text = str(value or "").replace(" ", "").replace("-", "").upper()
    if len(text) % 2 or any(char not in "0123456789ABCDEF" for char in text):
        return None
    try:
        return bytes.fromhex(text)
    except ValueError:
        return None


def analyze_button_trials(baseline, trials, min_repeats=2):
    """Find non-baseline payloads repeated across independent experiment trials."""
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
            -max((entry["repeat_count"] for entry in item["candidate_payloads"]), default=0),
            item["can_id"],
        ),
    )


def analyze_button_bits(baseline, trials, min_repeats=2):
    """Find bits whose per-trial modal value differs from the baseline mode.

    Bit numbering is byte_index * 8 + bit_index, where bit_index 0 is the
    least-significant bit of each byte. Tied baseline/trial modes are skipped.
    """
    if min_repeats < 1:
        raise ValueError("min_repeats must be at least 1")

    baseline_values = defaultdict(lambda: defaultdict(Counter))
    trial_values = []
    all_ids = set()

    for row in baseline:
        can_id = str(row.get("can_id", "")).upper()
        payload = _payload_bytes(row.get("data", ""))
        if payload is None:
            continue
        all_ids.add(can_id)
        for byte_index, byte in enumerate(payload):
            for bit_index in range(8):
                baseline_values[can_id][byte_index * 8 + bit_index][
                    (byte >> bit_index) & 1
                ] += 1

    for trial in trials:
        values = defaultdict(lambda: defaultdict(Counter))
        for row in trial:
            can_id = str(row.get("can_id", "")).upper()
            payload = _payload_bytes(row.get("data", ""))
            if payload is None:
                continue
            all_ids.add(can_id)
            for byte_index, byte in enumerate(payload):
                for bit_index in range(8):
                    values[can_id][byte_index * 8 + bit_index][
                        (byte >> bit_index) & 1
                    ] += 1
        trial_values.append(values)

    results = []
    for can_id in sorted(all_ids):
        bit_indexes = set(baseline_values[can_id])
        for values in trial_values:
            bit_indexes.update(values[can_id])
        for bit_index in sorted(bit_indexes):
            base_counts = baseline_values[can_id][bit_index]
            if not base_counts or base_counts[0] == base_counts[1]:
                continue
            base_value = 0 if base_counts[0] > base_counts[1] else 1
            changed_trials = Counter()
            eligible_trials = 0
            for values in trial_values:
                counts = values[can_id][bit_index]
                if not counts or counts[0] == counts[1]:
                    continue
                eligible_trials += 1
                mode = 0 if counts[0] > counts[1] else 1
                if mode != base_value:
                    changed_trials[mode] += 1
            for changed_value, count in sorted(changed_trials.items()):
                results.append({
                    "can_id": can_id,
                    "bit_index": bit_index,
                    "byte_index": bit_index // 8,
                    "bit_in_byte": bit_index % 8,
                    "baseline_value": base_value,
                    "candidate_value": changed_value,
                    "changed_trials": count,
                    "eligible_trials": eligible_trials,
                    "repeat_ratio": count / eligible_trials if eligible_trials else 0.0,
                    "candidate": count >= min_repeats,
                })

    return sorted(
        results,
        key=lambda item: (
            not item["candidate"],
            -item["changed_trials"],
            item["can_id"],
            item["bit_index"],
        ),
    )
