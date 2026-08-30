"""What samsung-bridge sends for the Galaxy Buds2.

    python -m unittest tests.samsung_bridge_test

The frozen session is tests/pins/samsung/galaxy-buds2.json: the bytes the
bridge writes on connect and on `set <mode>`, and the one status packet the
device itself answered with. What is here is what is *not* read, and what a
silent headset does.
"""
import unittest

from tests import harness

bridge_module = harness.load_bridge("samsung-bridge")

STATUS_FRAME = (
    "fd 2a 00 61 0b 03 12 12 01 01 11 00 00 00 bf 22 01 00 40 01 40 01 03 00 03 66"
    " 00 02 00 10 00 00 00 00 11 02 00 01 00 00 40 00 00 99 3d dd"
)
STATUS_PAYLOAD = (
    "0b 03 12 12 01 01 11 00 00 00 bf 22 01 00 40 01 40 01 03 00 03 66 00 02 00 10"
    " 00 00 00 00 11 02 00 01 00 00 40 00 00"
)


class Session(harness.Session):
    """A Samsung session. "device" in a pin is a whole frame as hex, FD to DD,
    fed through the bridge's framer. "sent" is every whole frame the bridge
    wrote, as hex. "open" sends the manager-info request, as the bridge does
    the moment the channel opens."""

    def __init__(self):
        super().__init__(bridge_module)
        self.bridge = bridge_module.Bridge(None, "84:5F:04:B5:D6:74", harness.FakeLoop())
        self.bridge.write = self.frames.append
        self.bridge.fd = -1

    def device(self, spec):
        self.bridge.buffer += harness.hexbytes(spec)
        self.bridge.parse_buffer()

    def do_open(self):
        self.bridge.send_manager_info()


harness.pin_tests(globals(), "samsung-bridge", Session)


class NotRead(unittest.TestCase):
    def test_a_plain_status_frame_is_not_read(self):
        # 0x60 has not been captured; the same bytes under that id say nothing.
        s = Session()
        frame = bytearray(harness.hexbytes(STATUS_FRAME))
        frame[3] = bridge_module.STATUS_UPDATED
        crc = bridge_module.crc16(bytes(frame[3:-3]))
        frame[-3:-1] = crc.to_bytes(2, "little")
        s.device(harness.hexstr(frame))
        self.assertEqual(s.lines, [])

    def test_parse_state_uses_the_observed_offsets(self):
        self.assertEqual(bridge_module.parse_state(harness.hexbytes(STATUS_PAYLOAD)), {
            "modes": True,
            "mode": "anc",
            "available": ["off", "anc", "ambient"],
            "battery": {"left": 18, "right": 18, "case": 0, "charging": []},
        })


class Silent(unittest.TestCase):
    def test_silence_after_the_request_parks_the_address(self):
        s = Session()
        s.do_open()
        s.bridge.status_timeout()
        self.assertEqual(s.bridge.exit_code, bridge_module.EXIT_UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
