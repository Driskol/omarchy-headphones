"""What xiaomi-bridge sends the Buds 5 Pro.

    python -m unittest tests.xiaomi_bridge_test

The frozen session is tests/pins/xiaomi/buds-5-pro.json. What is here is the
byte that must never go out, and what an unanswered handshake or query does.

No hardware and no D-Bus: the bridge's only two effects on the world are
`write()` and `emit()`, and both are captured.
"""
import unittest

from tests import harness

bridge_module = harness.load_bridge("xiaomi-bridge")


class Session(harness.Session):
    """A Xiaomi session. "device" in a pin is a whole Compact GAIA frame as
    hex, FF onwards, fed through the bridge's framer. "sent" is every whole
    frame the bridge wrote, as hex. "open" is the channel coming up: the
    bridge sends its handshake at once."""

    def __init__(self):
        super().__init__(bridge_module)
        self.bridge = bridge_module.Bridge(None, "64:8F:DB:87:06:CB", harness.FakeLoop())
        self.bridge.write = self.frames.append

    def do_open(self):
        self.bridge.opened(-1)

    def device(self, spec):
        self.bridge.buffer += harness.hexbytes(spec)
        frames, self.bridge.buffer = bridge_module.take_frames(self.bridge.buffer)
        for parsed in frames:
            self.bridge.on_frame(*parsed)


harness.pin_tests(globals(), "xiaomi-bridge", Session)

HANDSHAKE = "ff 03 00 00 00 0a 03 00"
HANDSHAKE_RET = "ff 03 00 04 00 0a 83 00 00 03 03 01"


class Forbidden(unittest.TestCase):
    def test_0x04_is_never_a_mode_and_never_sent(self):
        # SET 0x04 reboots the buds. It has no name, so no command reaches it,
        # and FORBIDDEN_SET refuses it even if the table above ever drifts.
        self.assertNotIn(0x04, bridge_module.BYTE_FROM_MODE.values())
        self.assertIn(0x04, bridge_module.FORBIDDEN_SET)
        bridge_module.BYTE_FROM_MODE["talkthru"] = 0x04
        try:
            s = Session()
            s.do_open()
            s.device(HANDSHAKE_RET)
            s.device("ff 03 00 05 00 1d 11 03 01 01 01 00 00")
            s.command("set talkthru")
            self.assertEqual(s.sent[-1], "ff 03 00 00 00 1d 10 03")
        finally:
            del bridge_module.BYTE_FROM_MODE["talkthru"]


class Silent(unittest.TestCase):
    def test_no_handshake_answer_is_transient(self):
        s = Session()
        s.do_open()
        for _ in range(bridge_module.INIT_ATTEMPTS):
            s.fire()
        self.assertEqual(s.sent, [HANDSHAKE] * bridge_module.INIT_ATTEMPTS)
        self.assertEqual(s.bridge.exit_code, bridge_module.EXIT_TRANSIENT)

    def test_no_mode_answer_parks_the_address(self):
        s = Session()
        s.do_open()
        s.device(HANDSHAKE_RET)
        self.assertEqual(s.sent, [HANDSHAKE, "ff 03 00 00 00 1d 10 03"])
        s.fire()
        self.assertEqual(s.bridge.exit_code, bridge_module.EXIT_UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
