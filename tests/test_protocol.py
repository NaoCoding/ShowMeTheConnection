import unittest

from protocol import (
    ProtocolError,
    make_read_command, make_remote_mode, parse_register_response,
)
from drivers.barracuda_x import BarracudaXDriver, REG_BATTERY, REG_CHARGING, REG_CONNECTION


def response(register, value, marker=0, major=1, minor=1):
    packet = bytearray(64)
    packet[:5] = bytes((0x02, 0x0E, 0x50, 0x49, 0x08))
    packet[9:16] = bytes((marker, 0x04, 0x00, register, major, minor, value))
    return bytes(packet)


class ProtocolTests(unittest.TestCase):
    def test_commands_are_exact_size_and_read_only(self):
        command = make_read_command(REG_CONNECTION)
        self.assertEqual(len(command), 64)
        self.assertEqual(command[:11], bytes((2, 0x80, 8, 0, 0, 0x50, 0x41, 8, 0, 3, 0x20)))
        self.assertEqual(make_remote_mode(True)[11], 1)
        with self.assertRaises(ValueError):
            make_read_command(0x100)

    def test_verified_register_values(self):
        connection = bytes.fromhex("02 0E 50 49 08 D9 A3 92 6B 01 04 00 20 01 01 01")
        battery = bytes.fromhex("02 0E 50 49 08 DA D0 02 33 00 04 00 21 01 01 34")
        charging = bytes.fromhex("02 0E 50 49 08 DB AD 03 33 00 04 00 2A 01 01 00")
        self.assertEqual(parse_register_response(connection, REG_CONNECTION), 1)
        self.assertEqual(parse_register_response(battery, REG_BATTERY), 52)
        self.assertEqual(parse_register_response(charging, REG_CHARGING), 0)

    def test_all_observed_markers(self):
        for marker in (0, 1, 2):
            self.assertEqual(parse_register_response(response(0x20, 1, marker), REG_CONNECTION), 1)

    def test_invalid_truncated_stale_and_mismatched_responses(self):
        with self.assertRaises(ProtocolError):
            parse_register_response(b"\x02\x0e", REG_CONNECTION)
        with self.assertRaises(ProtocolError):
            parse_register_response(response(0x20, 1, major=2), REG_CONNECTION)
        with self.assertRaises(ProtocolError):
            parse_register_response(response(0x20, 1), REG_BATTERY)
        value = parse_register_response(response(0x21, 101), REG_BATTERY)
        with self.assertRaises(ValueError):
            BarracudaXDriver._validate_value(REG_BATTERY, value)


if __name__ == "__main__":
    unittest.main()
