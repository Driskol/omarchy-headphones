"""What every bridge test shares: loading a bridge, faking GLib, and pins.

A pin is one model's frozen session — tests/pins/<brand>/<model>.json — and
the reason it is a file rather than a test class is so that it can be owned:
the file names the person whose headphones it describes, a change to it shows
up in `git diff` on its own, and tools/check refuses a pull request that edits
or deletes one. New models add files; nobody edits another owner's.

A pin lists steps. Each step is one key (plus an optional "note"):

    actions
      "device":    what came from the device, in the form this bridge's
                   Session understands (usually a hex string; see the
                   Session in the bridge's test file for the exact shape)
      "command":   one line on the bridge's stdin, e.g. "set anc"
      "ack":       the device acknowledging the last command (bridges with
                   a sequence/ACK scheme)
      "fire":      run every scheduled timer once, in order
      "call":      a session action by name, e.g. "open", or [name, args...]
      "wait_sent": block until at least N frames have gone out (bridges
                   that send from a thread)

    assertions
      "sent":         every frame sent so far, in order, as strings
      "sent_last":    the last frame sent
      "lines":        every stdout line so far, as JSON objects
      "line":         the last stdout line, whole
      "line_has":     keys the last stdout line must carry with these values
      "line_without": keys the last stdout line must not carry
      "line_count":   how many stdout lines so far
      "timers":       the intervals of every timer still scheduled
      "exit":         the bridge's exit code so far (null while running)
      "state":        bridge attributes with their expected values

What "sent" means is the bridge's business — a payload on one, a whole frame
on another, a line to a child process on a third — and each Session says
which in its docstring. The device frames in a pin are laid out from
PROTOCOL.md, not recorded: what a pin freezes is what the bridge sends and
prints, which is the promise made to that model's owner.

The bridges import python-dbus and PyGObject, which a continuous-integration
runner does not have. Where they are missing, stand-ins are installed under
the same names before a bridge is loaded; the tests never touch either — the
only two effects a bridge has on the world are write() and emit(), and both
are captured. Set OMAPHONES_TEST_STUBS=1 to use the stand-ins even where the
real modules exist, which is how the CI path is checked on a machine that has
them.
"""
import glob
import importlib.machinery
import importlib.util
import json
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
PINS = os.path.join(HERE, "pins")


def _stub_bluetooth_modules():
    if os.environ.get("OMAPHONES_TEST_STUBS") != "1":
        try:
            import dbus  # noqa: F401
            import dbus.mainloop.glib  # noqa: F401
            import dbus.service  # noqa: F401
            from gi.repository import GLib  # noqa: F401
            return
        except ImportError:
            pass
    if getattr(sys.modules.get("dbus"), "_omaphones_stub", False):
        return

    dbus = types.ModuleType("dbus")
    dbus._omaphones_stub = True

    class DBusException(Exception):
        def get_dbus_message(self):
            return str(self)

    dbus.DBusException = DBusException
    dbus.Boolean = bool
    dbus.Interface = lambda *args, **kwargs: None
    dbus.SystemBus = lambda: None
    mainloop = types.ModuleType("dbus.mainloop")
    mainloop_glib = types.ModuleType("dbus.mainloop.glib")
    mainloop_glib.DBusGMainLoop = lambda **kwargs: None
    mainloop.glib = mainloop_glib
    dbus.mainloop = mainloop
    service = types.ModuleType("dbus.service")

    class Object:
        def __init__(self, *args, **kwargs):
            pass

    service.Object = Object
    service.method = lambda *args, **kwargs: (lambda fn: fn)
    dbus.service = service

    gi = types.ModuleType("gi")
    repository = types.ModuleType("gi.repository")
    GLib = types.ModuleType("gi.repository.GLib")
    GLib.PRIORITY_DEFAULT = 0
    GLib.IO_IN, GLib.IO_HUP, GLib.IO_ERR = 1, 16, 8
    GLib.timeout_add = lambda *args, **kwargs: 0
    GLib.io_add_watch = lambda *args, **kwargs: 0
    GLib.source_remove = lambda *args: True
    GLib.unix_signal_add = lambda *args, **kwargs: 0

    class MainLoop:
        def run(self):
            pass

        def quit(self):
            pass

    GLib.MainLoop = MainLoop
    repository.GLib = GLib
    gi.repository = repository

    for name, module in (("dbus", dbus), ("dbus.mainloop", mainloop),
                         ("dbus.mainloop.glib", mainloop_glib),
                         ("dbus.service", service), ("gi", gi),
                         ("gi.repository", repository),
                         ("gi.repository.GLib", GLib)):
        sys.modules[name] = module


def load_bridge(name):
    """The bridge script at the repository root, as a module."""
    _stub_bluetooth_modules()
    path = os.path.join(ROOT, name)
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def hexbytes(text):
    """bytes from "aa 91 01 11" or "aa910111"."""
    return bytes.fromhex(str(text).replace(" ", ""))


def hexstr(data):
    return " ".join("%02x" % byte for byte in bytes(data))


class FakeGLib:
    """Records what the bridge schedules; the test decides when it fires."""

    PRIORITY_DEFAULT = 0
    IO_IN, IO_HUP, IO_ERR = 1, 16, 8

    def __init__(self):
        self.timers = []
        self.serial = 0

    def timeout_add(self, ms, fn, *args):
        self.serial += 1
        self.timers.append((ms, fn, args, self.serial))
        return self.serial

    def io_add_watch(self, *_args):
        return 0

    def source_remove(self, serial):
        self.timers = [t for t in self.timers if t[3] != serial]
        return True


class FakeLoop:
    def quit(self):
        pass

    def run(self):
        pass


class Session:
    """One bridge with its effects captured. Bridge tests subclass this.

    A subclass sets self.bridge and captures whatever the bridge writes into
    self.frames; it defines device() for the shape its pins use, and ack()
    where the protocol has one. `sent` is the frames as strings, in whatever
    form the subclass documents.
    """

    def __init__(self, module):
        self.module = module
        self.lines = []
        self.frames = []
        self.glib = FakeGLib()
        module.emit = self.lines.append
        if hasattr(module, "GLib"):
            module.GLib = self.glib
        self.bridge = None

    # ---- actions

    def device(self, spec):
        raise NotImplementedError

    def command(self, line):
        self.bridge.command(line)

    def ack(self):
        raise NotImplementedError("this bridge has no ACK")

    def fire(self):
        """Run every scheduled timer, in order, once."""
        pending, self.glib.timers = self.glib.timers, []
        for _ms, fn, args, _serial in pending:
            fn(*args)

    def call(self, name, *args):
        action = getattr(self, "do_" + name, None)
        if action is None:
            action = getattr(self.bridge, name)
        return action(*args)

    def wait_sent(self, count):
        if len(self.sent) < count:
            raise AssertionError("only %d frames sent, wanted %d"
                                 % (len(self.sent), count))

    # ---- what happened

    @property
    def sent(self):
        return [hexstr(frame) for frame in self.frames]

    @property
    def timers(self):
        return [ms for ms, _fn, _args, _serial in self.glib.timers]

    @property
    def exit_code(self):
        return self.bridge.exit_code

    def state(self, name):
        return getattr(self.bridge, name)


ACTIONS = ("device", "command", "ack", "fire", "call", "wait_sent")
ASSERTIONS = ("sent", "sent_last", "lines", "line", "line_has",
              "line_without", "line_count", "timers", "exit", "state")


def run_pin(test, session, pin, path):
    """Play a pin's steps against a session, asserting as it goes."""
    for index, step in enumerate(pin["steps"]):
        keys = [key for key in step if key != "note"]
        if len(keys) != 1:
            raise AssertionError("%s step %d: one key per step, got %r"
                                 % (path, index, keys))
        key = keys[0]
        value = step[key]
        where = "%s step %d (%s)%s" % (
            os.path.relpath(path, ROOT), index, key,
            ": " + step["note"] if "note" in step else "")

        if key == "device":
            session.device(value)
        elif key == "command":
            session.command(value)
        elif key == "ack":
            session.ack()
        elif key == "fire":
            session.fire()
        elif key == "call":
            if isinstance(value, list):
                session.call(value[0], *value[1:])
            else:
                session.call(value)
        elif key == "wait_sent":
            session.wait_sent(value)
        elif key == "sent":
            test.assertEqual(session.sent, value, where)
        elif key == "sent_last":
            test.assertTrue(session.sent, where + ": nothing sent")
            test.assertEqual(session.sent[-1], value, where)
        elif key == "lines":
            test.assertEqual(session.lines, value, where)
        elif key == "line":
            test.assertTrue(session.lines, where + ": nothing printed")
            test.assertEqual(session.lines[-1], value, where)
        elif key == "line_has":
            test.assertTrue(session.lines, where + ": nothing printed")
            last = session.lines[-1]
            for name, expected in value.items():
                test.assertIn(name, last, where)
                test.assertEqual(last[name], expected, where + " key " + name)
        elif key == "line_without":
            test.assertTrue(session.lines, where + ": nothing printed")
            for name in value:
                test.assertNotIn(name, session.lines[-1], where)
        elif key == "line_count":
            test.assertEqual(len(session.lines), value, where)
        elif key == "timers":
            test.assertEqual(session.timers, value, where)
        elif key == "exit":
            test.assertEqual(session.exit_code, value, where)
        elif key == "state":
            for name, expected in value.items():
                test.assertEqual(session.state(name), expected,
                                 where + " attribute " + name)
        else:
            raise AssertionError("%s: unknown step key %r" % (where, key))


def pins_for(bridge):
    """(path, pin) for every pin file of a bridge, by file name."""
    brand = bridge[:-len("-bridge")] if bridge.endswith("-bridge") else bridge
    out = []
    for path in sorted(glob.glob(os.path.join(PINS, brand, "*.json"))):
        with open(path) as handle:
            out.append((path, json.load(handle)))
    return out


def pin_tests(namespace, bridge, session_factory):
    """One TestCase per pin file, added to a test module's namespace.

    session_factory(**pin["session"]) returns the Session to play it on.
    """
    pins = pins_for(bridge)
    if not pins:
        raise AssertionError("no pins for %s under %s" % (bridge, PINS))
    for path, pin in pins:
        stem = os.path.splitext(os.path.basename(path))[0]

        def test_frozen_session(self, pin=pin, path=path):
            session = session_factory(**pin.get("session", {}))
            run_pin(self, session, pin, path)

        name = "Pin_" + stem.replace("-", "_").replace(".", "_")
        cls = type(name, (unittest.TestCase,), {
            "test_frozen_session": test_frozen_session,
            "__doc__": "%s — %s. Frozen." % (pin["model"], pin["owner"]),
            "__module__": namespace["__name__"],
        })
        namespace[name] = cls
