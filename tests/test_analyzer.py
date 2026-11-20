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



    def test_host_receive_intervals_are_reported_per_can_id(self):
        analyzer = CanAnalyzer()
        analyzer.add({"can_id": "100", "data": "00", "frame_type": "STD", "host_rx_monotonic_ns": 1_000_000})
        analyzer.add({"can_id": "200", "data": "00", "frame_type": "STD", "host_rx_monotonic_ns": 2_000_000})
        analyzer.add({"can_id": "100", "data": "01", "frame_type": "STD", "host_rx_monotonic_ns": 4_000_000})
        row = next(item for item in analyzer.snapshot() if item["can_id"] == "100")
        self.assertEqual(row["interval_count"], 1)
        self.assertEqual(row["mean_interval_ms"], 3.0)
        self.assertEqual(row["min_interval_ms"], 3.0)
        self.assertEqual(row["max_interval_ms"], 3.0)

    def test_missing_or_non_monotonic_receive_time_is_ignored(self):
        analyzer = CanAnalyzer()
        analyzer.add({"can_id": "100", "data": "00", "frame_type": "STD", "host_rx_monotonic_ns": 5})
        analyzer.add({"can_id": "100", "data": "01", "frame_type": "STD"})
        analyzer.add({"can_id": "100", "data": "02", "frame_type": "STD", "host_rx_monotonic_ns": 4})
        row = analyzer.snapshot()[0]
        self.assertEqual(row["interval_count"], 0)
        self.assertIsNone(row["mean_interval_ms"])


if __name__ == "__main__":
    unittest.main()
