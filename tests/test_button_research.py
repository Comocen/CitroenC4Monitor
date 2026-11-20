import unittest

from citroen_monitor.button_research import (
    analyze_button_bits,
    analyze_button_trials,
)


class ButtonResearchTests(unittest.TestCase):
    def test_payload_repeated_across_independent_trials_is_candidate(self):
        baseline = [{"can_id": "100", "data": "00"}]
        trials = [
            [{"can_id": "100", "data": "01"}, {"can_id": "100", "data": "01"}],
            [{"can_id": "100", "data": "01"}],
            [{"can_id": "100", "data": "02"}],
        ]
        result = analyze_button_trials(baseline, trials)
        self.assertEqual(result[0]["can_id"], "100")
        payloads = {item["payload"]: item for item in result[0]["candidate_payloads"]}
        self.assertEqual(payloads["01"]["repeat_count"], 2)
        self.assertTrue(payloads["01"]["candidate"])
        self.assertFalse(payloads["02"]["candidate"])
        self.assertTrue(result[0]["candidate"])

    def test_payload_already_in_baseline_is_not_candidate(self):
        baseline = [{"can_id": "123", "data": "AA"}]
        trials = [
            [{"can_id": "123", "data": "AA"}],
            [{"can_id": "123", "data": "AA"}],
        ]
        result = analyze_button_trials(baseline, trials)
        self.assertFalse(result[0]["candidate"])
        self.assertEqual(result[0]["candidate_payloads"], [])

    def test_empty_trials(self):
        self.assertEqual(analyze_button_trials([], []), [])

    def test_min_repeats_must_be_positive(self):
        with self.assertRaises(ValueError):
            analyze_button_trials([], [], min_repeats=0)

    def test_bit_change_repeats_across_trials(self):
        baseline = [{"can_id": "321", "data": "00"} for _ in range(4)]
        trials = [
            [{"can_id": "321", "data": "01"} for _ in range(3)],
            [{"can_id": "321", "data": "01"} for _ in range(2)],
            [{"can_id": "321", "data": "00"} for _ in range(2)],
        ]
        result = analyze_button_bits(baseline, trials, min_repeats=2)
        bit_zero = next(item for item in result if item["bit_index"] == 0)
        self.assertEqual(bit_zero["baseline_value"], 0)
        self.assertEqual(bit_zero["candidate_value"], 1)
        self.assertEqual(bit_zero["changed_trials"], 2)
        self.assertTrue(bit_zero["candidate"])

    def test_bit_numbering_is_lsb_first(self):
        baseline = [{"can_id": "100", "data": "00"}]
        trials = [
            [{"can_id": "100", "data": "80"}],
            [{"can_id": "100", "data": "80"}],
        ]
        result = analyze_button_bits(baseline, trials)
        bit = next(item for item in result if item["candidate_value"] == 1)
        self.assertEqual(bit["bit_index"], 7)
        self.assertEqual(bit["byte_index"], 0)
        self.assertEqual(bit["bit_in_byte"], 7)

    def test_ambiguous_baseline_bit_is_skipped(self):
        baseline = [
            {"can_id": "100", "data": "00"},
            {"can_id": "100", "data": "01"},
        ]
        trials = [[{"can_id": "100", "data": "01"}] for _ in range(2)]
        self.assertEqual(analyze_button_bits(baseline, trials), [])


if __name__ == "__main__":
    unittest.main()
