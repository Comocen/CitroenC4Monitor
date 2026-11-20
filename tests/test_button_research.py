import unittest

from citroen_monitor.button_research import analyze_button_experiment


class ButtonResearchTests(unittest.TestCase):
    def test_prioritizes_id_with_new_payload(self):
        baseline = [
            {"can_id": "100", "data": "00"},
            {"can_id": "200", "data": "AA"},
        ]
        experiment = [
            {"can_id": "100", "data": "00"},
            {"can_id": "100", "data": "01"},
            {"can_id": "200", "data": "AA"},
        ]
        results = analyze_button_experiment(baseline, experiment)
        self.assertEqual(results[0]["can_id"], "100")
        self.assertTrue(results[0]["candidate"])
        self.assertEqual(results[0]["new_payloads"], ["01"])
        self.assertFalse(results[1]["candidate"])

    def test_empty_captures(self):
        self.assertEqual(analyze_button_experiment([], []), [])


if __name__ == "__main__":
    unittest.main()
