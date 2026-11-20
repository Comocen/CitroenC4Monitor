import unittest

from citroen_monitor.analyzer import CanAnalyzer, compare_capture_rows


class CanAnalyzerTests(unittest.TestCase):
    def test_counts_ids_and_frame_share(self):
        analyzer = CanAnalyzer()
        analyzer.add({"can_id": "123", "frame_type": "STD", "data": "00 01"})
        analyzer.add({"can_id": "123", "frame_type": "STD", "data": "00 02"})
        analyzer.add({"can_id": "456", "frame_type": "EXT", "data": "AA"})

        summary = analyzer.summary()
        self.assertEqual(summary["total_frames"], 3)
        self.assertEqual(summary["unique_ids"], 2)
        rows = {row["can_id"]: row for row in analyzer.snapshot()}
        self.assertEqual(rows["123"]["count"], 2)
        self.assertAlmostEqual(rows["123"]["share"], 200 / 3)
        self.assertEqual(rows["123"]["changed_bytes"], "1")
        self.assertEqual(rows["123"]["transitions"], 1)

    def test_reset_clears_statistics(self):
        analyzer = CanAnalyzer()
        analyzer.add({"can_id": "123", "frame_type": "STD", "data": "01"})
        analyzer.reset()
        self.assertEqual(analyzer.summary()["total_frames"], 0)
        self.assertEqual(analyzer.snapshot(), [])

    def test_compare_capture_rows_finds_new_payloads(self):
        baseline = [{"can_id": "123", "data": "00 01"}]
        experiment = [
            {"can_id": "123", "data": "00 01"},
            {"can_id": "123", "data": "00 02"},
        ]
        result = compare_capture_rows(baseline, experiment)
        self.assertEqual(result[0]["new_payloads"], ["00 02"])
        self.assertEqual(result[0]["baseline_frames"], 1)
        self.assertEqual(result[0]["experiment_frames"], 2)


if __name__ == "__main__":
    unittest.main()
