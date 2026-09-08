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
import types
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


class ChannelSelection(unittest.TestCase):
    """connect() walks RFCOMM_CHANNELS in order. 15 is the earbuds' channel and
    is tried first, so their path is exactly what it was; 28 is the CMF
    Headphone Pro's, reached only when 15 refuses."""

    def _connect_with(self, open_channels):
        tried = []

        class FakeSock:
            def settimeout(self, *_):
                pass

            def setblocking(self, *_):
                pass

            def close(self):
                pass

            def connect(self, target):
                _address, channel = target
                tried.append(channel)
                if channel not in open_channels:
                    raise OSError(111, "Connection refused")

        real = bridge_module.socket
        fake = types.SimpleNamespace(
            AF_BLUETOOTH=getattr(real, "AF_BLUETOOTH", 31),
            SOCK_STREAM=getattr(real, "SOCK_STREAM", 1),
            BTPROTO_RFCOMM=getattr(real, "BTPROTO_RFCOMM", 3),
            socket=lambda *a, **k: FakeSock(),
        )
        bridge = bridge_module.Bridge("2C:BE:EE:3C:6F:FE")
        saved_socket = bridge_module.socket
        saved_attempts = bridge_module.CONNECT_ATTEMPTS
        bridge_module.socket = fake
        bridge_module.CONNECT_ATTEMPTS = 1  # no retry sleeps in a unit test
        try:
            ok = bridge.connect()
        finally:
            bridge_module.socket = saved_socket
            bridge_module.CONNECT_ATTEMPTS = saved_attempts
        return ok, tried, bridge

    def test_the_earbuds_channel_answers_and_28_is_never_tried(self):
        ok, tried, bridge = self._connect_with({15})
        self.assertTrue(ok)
        self.assertEqual(tried, [15])
        self.assertEqual(bridge.channel, 15)

    def test_the_headphone_pro_is_reached_on_28_when_15_refuses(self):
        ok, tried, bridge = self._connect_with({28})
        self.assertTrue(ok)
        self.assertEqual(tried, [15, 28])
        self.assertEqual(bridge.channel, 28)

    def test_neither_channel_open_is_a_transient_failure(self):
        captured = []
        saved_emit = bridge_module.emit
        bridge_module.emit = captured.append
        try:
            ok, tried, bridge = self._connect_with(set())
        finally:
            bridge_module.emit = saved_emit
        self.assertFalse(ok)
        self.assertEqual(tried, [15, 28])
        self.assertEqual(bridge.exit_code, bridge_module.EXIT_TRANSIENT)
        self.assertEqual(bridge.channel, None)
        self.assertEqual(captured[-1]["modes"], False)


class CmfFrames(unittest.TestCase):
    """The CMF Headphone Pro's own frames, from docs/captures/nothing-headphone-pro.txt,
    through the framer and the parsers. Noise control on this headset is the
    six-byte triplet form 01 <mode> 00 02 <level> 00."""

    ANC_ADAPTIVE = bridge_module.frame(0x1E, 0x40, harness.hexbytes("01 04 00 02 04 00"))
    BATTERY_15 = bridge_module.frame(0x07, 0x40, harness.hexbytes("01 06 0f"))

    def test_a_real_answer_survives_being_split_at_every_byte_boundary(self):
        for cut in range(1, len(self.ANC_ADAPTIVE)):
            buffer = bytearray()
            frames = []
            for chunk in (self.ANC_ADAPTIVE[:cut], self.ANC_ADAPTIVE[cut:]):
                buffer += chunk
                frames += bridge_module.take_frames(buffer)
            self.assertEqual(len(frames), 1, "split at %d" % cut)
            cmd, direction, payload = frames[0]
            self.assertEqual((cmd, direction), (0x1E, 0x40))
            self.assertEqual(bridge_module.parse_anc(payload), ("anc", "adaptive"))

    def test_two_answers_in_one_read_are_both_taken(self):
        buffer = bytearray(self.BATTERY_15 + self.ANC_ADAPTIVE)
        frames = bridge_module.take_frames(buffer)
        self.assertEqual([(cmd, d) for cmd, d, _ in frames], [(0x07, 0x40), (0x1E, 0x40)])
        self.assertEqual(buffer, bytearray())

    def test_a_flipped_crc_byte_drops_the_frame(self):
        damaged = bytearray(self.ANC_ADAPTIVE)
        damaged[-1] ^= 0xFF
        self.assertEqual(bridge_module.take_frames(damaged), [])

    def test_the_no_crc_event_form_the_cmf_uses_parses(self):
        # 55 00 03 03 e0 ... — ctrl 0x0300, bit 0x20 clear, so no trailer.
        raw = bytearray(harness.hexbytes("55 00 03 03 e0 06 00 00 01 04 00 02 04 00"))
        frames = bridge_module.take_frames(raw)
        self.assertEqual(len(frames), 1)
        cmd, direction, payload = frames[0]
        self.assertEqual((cmd, direction), (0x03, 0xE0))
        self.assertEqual(bridge_module.parse_anc(payload), ("anc", "adaptive"))

    def test_every_mode_and_level_the_cmf_reported(self):
        seen = {
            "01 05 00 02 04 00": ("off", "adaptive"),
            "01 07 00 02 04 00": ("ambient", "adaptive"),
            "01 04 00 02 04 00": ("anc", "adaptive"),
            "01 03 00 02 03 00": ("anc", "low"),
            "01 02 00 02 02 00": ("anc", "mid"),
            "01 01 00 02 01 00": ("anc", "high"),
        }
        for payload, expected in seen.items():
            self.assertEqual(bridge_module.parse_anc(harness.hexbytes(payload)), expected, payload)


class CmfMalformed(unittest.TestCase):
    """Fault injection: bytes bent on purpose. None of these is something the
    CMF Headphone Pro was seen to answer — they are here to pin how the parsers
    treat damage, not to claim the headset sends it."""

    def test_a_truncated_noise_control_payload_yields_nothing_usable(self):
        self.assertEqual(bridge_module.parse_anc(b""), (None, None))
        self.assertEqual(bridge_module.parse_anc(b"\x01"), (None, None))

    def test_an_unknown_mode_byte_is_not_forced_into_a_mode(self):
        mode, _level = bridge_module.parse_anc(harness.hexbytes("01 6f 00"))
        self.assertIsNone(mode)

    def test_a_battery_component_the_map_does_not_know_is_skipped(self):
        levels, charging = bridge_module.parse_battery(harness.hexbytes("02 09 40 06 0f"))
        self.assertEqual(levels, {"headset": 15})
        self.assertEqual(charging, [])

    def test_a_level_over_100_is_dropped_not_clamped(self):
        levels, _ = bridge_module.parse_battery(harness.hexbytes("01 06 65"))  # 0x65 = 101
        self.assertEqual(levels, {})

    def test_the_charging_bit_would_be_read_off_the_headset_level(self):
        # Synthetic: the probe ran on battery, so a charging frame was never seen.
        levels, charging = bridge_module.parse_battery(harness.hexbytes("01 06 8f"))
        self.assertEqual(levels, {"headset": 15})
        self.assertEqual(charging, ["headset"])

    def test_an_empty_battery_payload_is_no_components(self):
        self.assertEqual(bridge_module.parse_battery(b""), ({}, []))


class CmfLifecycle(unittest.TestCase):
    """Silence, unsupported input, ignored frames and two-headset isolation,
    on the CMF's single-battery shape."""

    def _opened(self):
        session = Session()
        session.do_open()
        session.device({"cmd": "06", "dir": "40", "payload": "00"})
        return session

    def test_battery_without_a_mode_answer_prints_nothing_then_parks(self):
        session = self._opened()
        session.device({"cmd": "07", "dir": "40", "payload": "01 06 0f"})
        self.assertEqual(session.lines, [])
        session.bridge.finish(bridge_module.EXIT_UNSUPPORTED, "no mode answer")
        self.assertEqual(session.bridge.exit_code, bridge_module.EXIT_UNSUPPORTED)
        self.assertEqual(session.lines[-1], {"modes": False, "error": "no mode answer"})

    def test_a_name_outside_the_panels_vocabulary_sends_nothing(self):
        session = self._opened()
        session.device({"cmd": "1e", "dir": "40", "payload": "01 04 00 02 04 00"})
        before = list(session.sent)
        session.command("set purple")
        session.command("level eleven")
        session.command("latency maybe")
        self.assertEqual(session.sent, before)

    def test_frames_the_bridge_never_asked_for_are_ignored(self):
        session = self._opened()
        session.device({"cmd": "1e", "dir": "40", "payload": "01 04 00 02 04 00"})
        settled = dict(session.lines[-1])
        session.device({"cmd": "19", "dir": "e0", "payload": "01 00"})     # E0 19
        session.device({"cmd": "09", "dir": "7c", "payload": "00 04 00"})  # 09 / 7c
        self.assertEqual(session.lines[-1], settled)
        self.assertIsNone(session.bridge.exit_code)

    def test_a_second_headset_does_not_disturb_the_first(self):
        first = self._opened()
        first.device({"cmd": "1e", "dir": "40", "payload": "01 01 00 02 01 00"})  # high
        first_line = dict(first.lines[-1])
        second = self._opened()  # from here module.emit points at `second`
        second.device({"cmd": "1e", "dir": "40", "payload": "01 07 00 02 04 00"})  # ambient
        second.device({"cmd": "07", "dir": "40", "payload": "01 06 63"})           # 99%
        self.assertEqual(first.bridge.mode, "anc")
        self.assertEqual(first.bridge.level, "high")
        self.assertEqual(first.lines[-1], first_line)
        self.assertEqual(second.bridge.mode, "ambient")
        self.assertEqual(second.bridge.levels, {"headset": 99})


if __name__ == "__main__":
    unittest.main()
