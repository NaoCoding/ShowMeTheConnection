import unittest

from barracuda_tray.drivers.barracuda_x import BarracudaXDriver, RAZER_BARRACUDA_X_MATCH, REG_CONNECTION
from barracuda_tray.hid_device import HidDevice
from barracuda_tray.protocol import make_read_command, make_remote_mode

SAMPLE = bytes.fromhex("02 0E 50 49 08 D9 A3 92 6B 01 04 00 20 01 01 01")


class FakeHandle:
    def __init__(self, reports):
        self.reports = list(reports)
        self.writes = []
        self.closed = False

    def open_path(self, _path):
        pass

    def write(self, packet):
        self.writes.append(bytes(packet))

    def read(self, _size, _timeout):
        return self.reports.pop(0) if self.reports else []

    def close(self):
        self.closed = True


class FakeHid:
    def __init__(self, handle):
        self.handle = handle

    def enumerate(self, _vid, _pid):
        return [{"vendor_id": 0x1532, "product_id": 0x0550, "interface_number": 3,
                 "usage_page": 0xFF00, "usage": 1, "path": b"razer-vendor"}]

    def device(self):
        return self.handle


class BarracudaDriverTests(unittest.TestCase):
    def test_receiver_identity_and_verified_exchange_live_in_driver(self):
        self.assertEqual((RAZER_BARRACUDA_X_MATCH.vendor_id, RAZER_BARRACUDA_X_MATCH.product_id), (0x1532, 0x0550))
        handle = FakeHandle([[], SAMPLE])
        transport = HidDevice(RAZER_BARRACUDA_X_MATCH, FakeHid(handle))
        driver = BarracudaXDriver(transport, sleeper=lambda _seconds: None)
        self.assertTrue(driver.read_connection())
        self.assertEqual(handle.writes, [make_remote_mode(True), make_read_command(REG_CONNECTION), make_remote_mode(False)])
        driver.close()
        self.assertTrue(handle.closed)

    def test_hid_read_timeout_is_bounded(self):
        handle = FakeHandle([])
        transport = HidDevice(RAZER_BARRACUDA_X_MATCH, FakeHid(handle))
        driver = BarracudaXDriver(transport, sleeper=lambda _seconds: None)
        with self.assertRaises(TimeoutError):
            driver.read_connection()
        driver.close()


if __name__ == "__main__":
    unittest.main()
