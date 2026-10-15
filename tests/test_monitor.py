import threading
import time
import unittest

from barracuda_tray.hid_device import DeviceUnavailable
from barracuda_tray.monitor import ConnectionState, Monitor


class FakeDevice:
    def __init__(self):
        self.connected = True
        self.fail = False
        self.closed = 0

    def read_connection(self):
        if self.fail:
            raise OSError("timeout")
        return self.connected

    def read_details(self):
        return 52, False

    def close(self):
        self.closed += 1


class FakeDriver(FakeDevice):
    key = "fake-headset"
    display_name = "Fake Headset"

    def read_details(self):
        return None, None


class MonitorTests(unittest.TestCase):
    def test_transitions_clear_stale_battery_and_reconnect(self):
        device = FakeDevice()
        monitor = Monitor(device)
        state = monitor.poll_once(force_details=True)
        self.assertEqual((state.connection, state.battery), (ConnectionState.CONNECTED, 52))
        device.connected = False
        state = monitor.poll_once()
        self.assertEqual(state.connection, ConnectionState.DISCONNECTED)
        self.assertIsNone(state.battery)
        device.connected = True
        state = monitor.poll_once()
        self.assertEqual((state.connection, state.battery), (ConnectionState.CONNECTED, 52))

    def test_failure_becomes_unknown_after_repeated_failure(self):
        device = FakeDevice()
        monitor = Monitor(device)
        monitor.poll_once(force_details=True)
        device.fail = True
        self.assertEqual(monitor.poll_once().connection, ConnectionState.CONNECTED)
        self.assertEqual(monitor.poll_once().connection, ConnectionState.UNKNOWN)

    def test_unavailable_receiver_and_worker_shutdown(self):
        class Missing(FakeDevice):
            def read_connection(self):
                raise DeviceUnavailable()
        missing = Missing()
        monitor = Monitor(missing, connection_interval=0.01)
        self.assertEqual(monitor.poll_once().connection, ConnectionState.RECEIVER_UNAVAILABLE)
        device = FakeDevice()
        monitor = Monitor(device, connection_interval=0.01)
        monitor.start()
        time.sleep(0.04)
        monitor.stop()
        self.assertFalse(monitor._thread.is_alive())
        self.assertGreaterEqual(device.closed, 1)

    def test_multiple_registered_drivers_keep_independent_states(self):
        first, second = FakeDriver(), FakeDriver()
        second.key = "fake-speaker"
        second.display_name = "Fake Speaker"
        second.connected = False
        monitor = Monitor(drivers=[first, second])
        monitor.poll_once(force_details=True)
        self.assertEqual(len(monitor.states), 2)
        self.assertEqual(monitor.states[0].device_name, "Fake Headset")
        self.assertIsNone(monitor.states[0].battery)
        self.assertEqual(monitor.states[1].connection, ConnectionState.DISCONNECTED)


if __name__ == "__main__":
    unittest.main()
