import unittest

from citroen_monitor.button_research import analyze_button_trials


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


if __name__ == "__main__":
    unittest.main()
