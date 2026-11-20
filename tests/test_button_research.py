import unittest

from citroen_monitor.button_research import (
    analyze_button_bits,
    analyze_button_trials,
    analyze_button_transitions,
    ButtonTrialRecorder,
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


    def test_press_bit_flips_and_restores_after_release(self):
        def rows(value):
            return [{"can_id": "100", "data": "%02X" % value} for _ in range(3)]
        trials = [
            {"released_before": rows(0), "pressed": rows(1), "released_after": rows(0)},
            {"released_before": rows(0), "pressed": rows(1), "released_after": rows(0)},
            {"released_before": rows(0), "pressed": rows(1), "released_after": rows(0)},
        ]
        result = analyze_button_transitions(trials)
        bit = next(item for item in result if item["bit_index"] == 0)
        self.assertEqual(bit["released_value"], 0)
        self.assertEqual(bit["pressed_value"], 1)
        self.assertEqual(bit["changed_trials"], 3)
        self.assertTrue(bit["candidate"])

    def test_transition_rejected_when_release_does_not_restore(self):
        def rows(value):
            return [{"can_id": "100", "data": "%02X" % value} for _ in range(3)]
        trials = [
            {"released_before": rows(0), "pressed": rows(1), "released_after": rows(1)},
            {"released_before": rows(0), "pressed": rows(1), "released_after": rows(1)},
        ]
        self.assertEqual(analyze_button_transitions(trials), [])

    def test_transition_rejects_ambiguous_window(self):
        trials = [{
            "released_before": [{"can_id": "100", "data": "00"}, {"can_id": "100", "data": "01"}],
            "pressed": [{"can_id": "100", "data": "01"}],
            "released_after": [{"can_id": "100", "data": "00"}],
        }]
        self.assertEqual(analyze_button_transitions(trials), [])


    def test_trial_recorder_requires_windows_in_order_and_minimum_frames(self):
        recorder = ButtonTrialRecorder(min_frames_per_window=2)
        recorder.begin()
        with self.assertRaises(ValueError):
            recorder.start_window("pressed")
        recorder.start_window("released_before")
        recorder.add_frame({"can_id": "100", "data": "00"})
        with self.assertRaises(ValueError):
            recorder.start_window("released_after")
        recorder.add_frame({"can_id": "100", "data": "00"})
        recorder.start_window("pressed")
        recorder.add_frame({"can_id": "100", "data": "01"})
        recorder.add_frame({"can_id": "100", "data": "01"})
        recorder.start_window("released_after")
        recorder.add_frame({"can_id": "100", "data": "00"})
        recorder.add_frame({"can_id": "100", "data": "00"})
        result = recorder.finish()
        self.assertEqual(len(result["released_before"]), 2)
        self.assertEqual(len(result["pressed"]), 2)
        self.assertEqual(len(result["released_after"]), 2)
        self.assertIsNone(recorder.active)

    def test_trial_recorder_rejects_short_or_incomplete_windows(self):
        recorder = ButtonTrialRecorder(min_frames_per_window=2)
        recorder.begin()
        recorder.start_window("released_before")
        recorder.add_frame({"can_id": "100", "data": "00"})
        with self.assertRaises(ValueError):
            recorder.start_window("pressed")
        with self.assertRaises(RuntimeError):
            recorder.finish()

    def test_trial_recorder_cancel_resets_state(self):
        recorder = ButtonTrialRecorder()
        recorder.begin()
        self.assertTrue(recorder.cancel())
        self.assertFalse(recorder.cancel())
        recorder.begin()
        recorder.start_window("released_before")

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
