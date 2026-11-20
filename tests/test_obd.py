import unittest

from citroen_monitor.obd import decode_pid, parse_mode01_response, supported_pids


class ObdPidTests(unittest.TestCase):
    def test_rpm(self):
        self.assertEqual(decode_pid(0x0C, "1A F8")["value"], 1726.0)

    def test_coolant_temperature(self):
        self.assertEqual(decode_pid(0x05, [90])["value"], 50)

    def test_speed(self):
        self.assertEqual(decode_pid(0x0D, "2A")["value"], 42)

    def test_throttle_percentage(self):
        self.assertAlmostEqual(decode_pid(0x11, "FF")["value"], 100.0)

    def test_trim(self):
        self.assertAlmostEqual(decode_pid(0x06, "80")["value"], 0.0)

    def test_voltage(self):
        self.assertAlmostEqual(decode_pid(0x42, "34 2A")["value"], 13.354)

    def test_parse_elm_response_with_header(self):
        result = parse_mode01_response("7E8 04 41 0C 1A F8\r>")
        self.assertEqual(result["pid"], "010C")
        self.assertEqual(result["value"], 1726.0)

    def test_parse_rejects_unrelated_or_short_response(self):
        self.assertIsNone(parse_mode01_response("NO DATA"))
        self.assertIsNone(parse_mode01_response("41 0C 1A"))

    def test_requested_pid_filter(self):
        self.assertIsNone(parse_mode01_response("41 0D 20", requested_pid=0x0C))

    def test_unsupported_pid_and_bad_length(self):
        with self.assertRaises(ValueError):
            decode_pid(0x99, "00")
        with self.assertRaises(ValueError):
            decode_pid(0x0C, "01")

    def test_supported_pid_bitmap(self):
        # Bitmap bits announce PID 04 and PID 0C in the 0100 response.
        result = supported_pids("10 10 00 00")
        self.assertIn(4, result)
        self.assertIn(12, result)


if __name__ == "__main__":
    unittest.main()
