import unittest

from barracuda_tray.hid_device import DeviceUnavailable, HeadsetDevice
from barracuda_tray.protocol import make_read_command, make_remote_mode, REG_CONNECTION


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
    def __init__(self, handle, infos=None):
        self.handle = handle
        self.infos = infos if infos is not None else [
            {"vendor_id": 0x1532, "product_id": 0x0550, "interface_number": 3,
             "usage_page": 0x000C, "usage": 1, "path": b"consumer"},
            {"vendor_id": 0x1532, "product_id": 0x0550, "interface_number": 3,
             "usage_page": 0xFF00, "usage": 1, "path": b"vendor"},
        ]

    def enumerate(self, _vid, _pid):
        return self.infos

    def device(self):
        return self.handle


class HidDeviceTests(unittest.TestCase):
    def test_selects_vendor_collection_and_uses_verified_exchange(self):
        handle = FakeHandle([[], SAMPLE])
        device = HeadsetDevice(FakeHid(handle), sleeper=lambda _seconds: None)
        self.assertTrue(device.read_connection())
        self.assertEqual(handle.writes, [make_remote_mode(True), make_read_command(REG_CONNECTION), make_remote_mode(False)])
        device.close()
        self.assertTrue(handle.closed)

    def test_missing_device_and_read_timeout(self):
        handle = FakeHandle([])
        absent = FakeHid(handle, infos=[])
        with self.assertRaises(DeviceUnavailable):
            HeadsetDevice(absent, sleeper=lambda _seconds: None).read_connection()
        # The mock returns empty HID reads until the bounded request deadline expires.
        device = HeadsetDevice(FakeHid(handle), sleeper=lambda _seconds: None)
        with self.assertRaises(TimeoutError):
            device.read_connection()
        device.close()


if __name__ == "__main__":
    unittest.main()
