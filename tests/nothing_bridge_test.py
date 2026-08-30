"""What nothing-bridge sends Nothing earbuds.

    python -m unittest tests.nothing_bridge_test

The frozen session is tests/pins/nothing/ear-a.json. What is here is the
framing (the CRC against PROTOCOL.md's worked example) and what a silent
device does.

No hardware and no socket: the bridge's only two effects on the world are
the socket's sendall() and emit(), and both are captured. The case cache is
pointed at a fresh temporary directory per session.
"""
import os
import shutil
import tempfile
import unittest
import weakref

from tests import harness

bridge_module = harness.load_bridge("nothing-bridge")


class FakeSocket:
    def __init__(self, frames):
        self.frames = frames

    def sendall(self, data):
        self.frames.append(bytes(data))


class Session(harness.Session):
    """A Nothing session. "device" in a pin is {"cmd": "1e", "dir": "40",
    "payload": hex}: the command, the direction byte and the payload, framed
    with the CRC the way the device frames them and fed through the bridge's
    framer. "sent" is every whole frame the bridge wrote, as hex. "open" is
    the socket coming up: the bridge asks for device info first."""

    def __init__(self):
        super().__init__(bridge_module)
        self.tmp = tempfile.mkdtemp(prefix="omaphones-test-")
        weakref.finalize(self, shutil.rmtree, self.tmp, ignore_errors=True)
        bridge_module.STATE_DIR = self.tmp
        bridge_module.CASE_FILE = os.path.join(self.tmp, "nothing-case.json")
        self.bridge = bridge_module.Bridge("3C:B0:ED:AF:7C:30")
        self.bridge.sock = FakeSocket(self.frames)

    def do_open(self):
        self.bridge.send(bridge_module.CMD_DEVICE_INFO)

    def device(self, spec):
        frame = bridge_module.frame(
            int(spec["cmd"], 16), int(spec["dir"], 16),
            harness.hexbytes(spec.get("payload", "")))
        self.bridge.buffer += frame
        for parsed in bridge_module.take_frames(self.bridge.buffer):
            self.bridge.on_frame(*parsed)


harness.pin_tests(globals(), "nothing-bridge", Session)


class Framing(unittest.TestCase):
    def test_the_noise_control_get_matches_the_worked_example(self):
        # PROTOCOL.md: 55 60 01 1E C0 00 00 01 B1 1D asks for the state.
        frame = bridge_module.frame(bridge_module.CMD_ANC_GET, bridge_module.DIR_GET)
        self.assertEqual(harness.hexstr(frame), "55 60 01 1e c0 00 00 01 b1 1d")

    def test_a_frame_with_a_bad_crc_is_dropped(self):
        frame = bytearray(bridge_module.frame(0x1E, 0x40, bytes([1, 1, 0])))
        frame[-1] ^= 0xFF
        self.assertEqual(bridge_module.take_frames(frame), [])


class Silent(unittest.TestCase):
    def test_no_mode_answer_parks_the_address(self):
        s = Session()
        s.do_open()
        s.device({"cmd": "06", "dir": "40", "payload": "00"})
        # The main loop's deadline, without the loop: the mode never came.
        s.bridge.finish(bridge_module.EXIT_UNSUPPORTED, "the device did not answer")
        self.assertEqual(s.bridge.exit_code, bridge_module.EXIT_UNSUPPORTED)
        self.assertEqual(s.lines[-1]["modes"], False)

    def test_nothing_is_written_before_the_mode_is_known(self):
        s = Session()
        s.do_open()
        s.command("set anc")
        s.command("latency on")
        self.assertEqual(len(s.sent), 1)


if __name__ == "__main__":
    unittest.main()
