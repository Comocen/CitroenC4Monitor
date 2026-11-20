"""Helpers for comparing passive CAN captures around a labeled button action.

Results are candidates for manual investigation, not decoded vehicle signals.
"""
from .analyzer import compare_capture_rows


def analyze_button_experiment(baseline, experiment):
    """Return per-ID differences, prioritizing IDs with new payload variants."""
    comparisons = compare_capture_rows(baseline, experiment)
    results = []
    for item in comparisons:
        new_payloads = item["new_payloads"]
        variant_delta = item["experiment_variants"] - item["baseline_variants"]
        results.append({
            **item,
            "variant_delta": variant_delta,
            "candidate": bool(new_payloads or variant_delta > 0),
        })
    return sorted(
        results,
        key=lambda item: (
            not item["candidate"],
            -len(item["new_payloads"]),
            -item["variant_delta"],
            item["can_id"],
        ),
    )
