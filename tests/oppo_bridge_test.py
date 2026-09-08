"""Pins what oppo-bridge sends for the OPPO Enco Air3 Pro.

    python -m unittest tests/oppo_bridge_test.py

The OPPO row is the same kind of promise as the Sony, Soundcore and Samsung
ones: this headset answered one exact query payload, and the bridge may keep
sending only those exact frames. The test below freezes the bytes the bridge
writes on connect and on `set <mode>`, and it freezes the query answers the
device itself gave.
"""
import importlib.machinery
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "oppo-bridge")
loader = importlib.machinery.SourceFileLoader("oppo_bridge", PATH)
spec = importlib.util.spec_from_loader("oppo_bridge", loader)
bridge_module = importlib.util.module_from_spec(spec)
loader.exec_module(bridge_module)

ADDRESS = "28:6F:40:D9:A5:A7"

# The answers the Enco Air3 Pro (product id 065C10) gave on the wire.
RET_OFF = bytes.fromhex("aa0c00000c810205000001010800")
RET_ANC = bytes.fromhex("aa0c00000c810205000001011000")
RET_AMBIENT = bytes.fromhex("aa0c00000c810205000001010001")
RET_BATTERY = bytes.fromhex("aa0d00000681030600000201500250")


class Session:
    def __init__(self):
        self.frames = []
        self.lines = []
        bridge_module.emit = self.lines.append
        loop = type("Loop", (), {"quit": lambda self: None})()
        self.bridge = bridge_module.Bridge(None, ADDRESS, loop)
        self.bridge.write = self.frames.append
        self.bridge.fd = 1


def payload_of(frame):
    frames, _ = bridge_module.take_frames(bytearray(frame))
    return frames[0]


class OppoBridge(unittest.TestCase):
    def test_anc_query_frame(self):
        s = Session()
        s.bridge.ask_mode()
        self.assertEqual([frame.hex() for frame in s.frames], [
            "aa0900000c010102000101",
        ])

    def test_battery_query_frame(self):
        s = Session()
        s.bridge.seq = 0x03
        s.bridge.ask_battery()
        self.assertEqual([frame.hex() for frame in s.frames], [
            "aa0700000601030000",
        ])

    def test_off_answer_names_off(self):
        s = Session()
        command, seq, payload = payload_of(RET_OFF)
        self.assertEqual(command, bridge_module.RET_ANC)
        s.bridge.on_frame(command, seq, payload)
        self.assertEqual(s.lines, [{
            "modes": True,
            "mode": "off",
            "available": ["off", "anc", "ambient"],
        }])

    def test_anc_answer_names_anc(self):
        s = Session()
        command, seq, payload = payload_of(RET_ANC)
        s.bridge.on_frame(command, seq, payload)
        self.assertEqual(s.lines[0]["mode"], "anc")

    def test_ambient_answer_names_ambient(self):
        s = Session()
        command, seq, payload = payload_of(RET_AMBIENT)
        s.bridge.on_frame(command, seq, payload)
        self.assertEqual(s.lines[0]["mode"], "ambient")

    def test_set_writes_the_observed_frames(self):
        s = Session()
        command, seq, payload = payload_of(RET_OFF)
        s.bridge.on_frame(command, seq, payload)
        s.frames.clear()
        s.bridge.seq = 0x11
        for line in ("set off", "set anc", "set ambient", "set talkthru"):
            s.bridge.command(line)
        self.assertEqual([frame.hex() for frame in s.frames], [
            "aa0a00000404110300010101",
            "aa0a00000404120300010102",
            "aa0a00000404130300010104",
        ])
        # talkthru is not offered, so nothing went out for it.
        self.assertEqual(len(s.frames), 3)

    def test_ack_asks_again(self):
        s = Session()
        command, seq, payload = payload_of(RET_OFF)
        s.bridge.on_frame(command, seq, payload)
        s.frames.clear()
        s.bridge.seq = 0x21
        frames, _ = bridge_module.take_frames(
            bytearray(bytes.fromhex("aa080000048421010000")))
        s.bridge.on_frame(*frames[0])
        self.assertEqual([frame.hex() for frame in s.frames], [
            "aa0900000c012102000101",
        ])

    def test_battery_answer_joins_the_line(self):
        s = Session()
        command, seq, payload = payload_of(RET_OFF)
        s.bridge.on_frame(command, seq, payload)
        s.frames.clear()
        s.lines.clear()
        command, seq, payload = payload_of(RET_BATTERY)
        self.assertEqual(command, bridge_module.RET_BATTERY)
        s.bridge.on_frame(command, seq, payload)
        self.assertEqual(s.lines, [{
            "modes": True,
            "mode": "off",
            "available": ["off", "anc", "ambient"],
            "battery": {
                "left": 80,
                "right": 80,
                "charging": [],
            },
        }])

    def test_an_unseen_pair_leaves_the_mode(self):
        s = Session()
        command, seq, payload = payload_of(RET_OFF)
        s.bridge.on_frame(command, seq, payload)
        s.lines.clear()
        # A bitmap position this headset never answered: not off, anc or
        # ambient here, so the panel keeps showing what it showed.
        s.bridge.on_frame(bridge_module.RET_ANC, 0x09, bytes([0x00, 0x01, 0x01, 0x20, 0x00]))
        self.assertEqual(s.lines, [])

    def test_silence_after_the_query_parks_the_address(self):
        s = Session()
        s.bridge.ask_mode()
        s.bridge.on_get_timeout()
        self.assertEqual(s.bridge.exit_code, bridge_module.EXIT_UNSUPPORTED)

    def test_framer_splits_glued_frames(self):
        glued = RET_OFF + RET_BATTERY
        frames, rest = bridge_module.take_frames(bytearray(glued))
        self.assertEqual(len(frames), 2)
        self.assertEqual(rest, bytearray())
        self.assertEqual(frames[0][0], bridge_module.RET_ANC)
        self.assertEqual(frames[1][0], bridge_module.RET_BATTERY)


if __name__ == "__main__":
    unittest.main()
