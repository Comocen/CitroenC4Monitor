import unittest

from citroen_monitor.slcan import parse_line


class SlcanParserTests(unittest.TestCase):
    def test_standard_data_frame(self):
        frame = parse_line("t1232A1B2\\r")
        self.assertEqual(frame["can_id"], "123")
        self.assertEqual(frame["frame_type"], "STD")
        self.assertEqual(frame["dlc"], 2)
        self.assertEqual(frame["data"], "A1 B2")

    def test_extended_data_frame(self):
        frame = parse_line("T0000012381122334455667788")
        self.assertEqual(frame["can_id"], "00000123")
        self.assertEqual(frame["frame_type"], "EXT")
        self.assertEqual(frame["dlc"], 8)

    def test_remote_frame(self):
        frame = parse_line("r1230")
        self.assertEqual(frame["frame_type"], "RTR")
        self.assertEqual(frame["data"], "")

    def test_invalid_lines_are_ignored(self):
        invalid = [
            "not a frame", "t1239", "tXYZ0", "t8000", "T200000000",
            "t1231GG", "t12310000", "r1231AA", "T200000001AA",
        ]
        for line in invalid:
            with self.subTest(line=line):
                self.assertIsNone(parse_line(line))

    def test_empty_data_frame(self):
        frame = parse_line("t1230")
        self.assertEqual(frame["data"], "")
