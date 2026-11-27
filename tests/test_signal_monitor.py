import unittest

from citroen_monitor.signal_monitor import (
    SignalDefinition, decode_signal_value, validate_definition,
)


class SignalMonitorTests(unittest.TestCase):
    def test_decode_single_bit(self):
        self.assertEqual(decode_signal_value("04 00", 2, 1), 1)
        self.assertEqual(decode_signal_value("00 00", 2, 1), 0)

    def test_decode_multibyte_little_endian_with_scaling(self):
        self.assertEqual(decode_signal_value("10 27", 0, 16, factor=0.1), 1000.0)

    def test_decode_signed_value(self):
        self.assertEqual(decode_signal_value("FF", 0, 8, signed=True), -1)

    def test_reject_out_of_payload_range(self):
        with self.assertRaises(ValueError):
            decode_signal_value("00", 7, 2)

    def test_validate_normalizes_can_id(self):
        definition = validate_definition(SignalDefinition(
            "RPM", "00123", 0, 16, factor=0.25, unit="rpm"
        ))
        self.assertEqual(definition.can_id, "123")
        self.assertEqual(definition.name, "RPM")

    def test_validate_rejects_invalid_can_id(self):
        with self.assertRaises(ValueError):
            validate_definition(SignalDefinition("bad", "xyz", 0, 1))


if __name__ == "__main__":
    unittest.main()
