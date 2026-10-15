import unittest

from barracuda_tray.hid_device import DeviceUnavailable, HidDevice, HidDeviceMatch, find_device


class FakeHandle:
    def __init__(self):
        self.path = None
        self.closed = False

    def open_path(self, path):
        self.path = path

    def close(self):
        self.closed = True


class FakeHid:
    def __init__(self, infos=None):
        self.handle = FakeHandle()
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


MATCH = HidDeviceMatch(0x1532, 0x0550, 3, 0xFF00, 1, "Test headset")


class HidDeviceTests(unittest.TestCase):
    def test_generic_transport_selects_the_driver_requested_collection(self):
        module = FakeHid()
        device = HidDevice(MATCH, module)
        self.assertEqual(find_device(module, MATCH)["path"], b"vendor")
        device.open()
        self.assertEqual(module.handle.path, b"vendor")
        device.close()
        self.assertTrue(module.handle.closed)

    def test_missing_matching_collection(self):
        device = HidDevice(MATCH, FakeHid(infos=[]))
        with self.assertRaises(DeviceUnavailable):
            device.open()
