#!/usr/bin/env python3
"""Probe OPPO HeyMelody listening mode over RFCOMM.

Registers an org.bluez.Profile1 for the HeyMelody SPP UUID
(0000079a-d102-11e1-9b23-00025b00a5a5), connects the socket, and sends an ANC
query (0x010C) and a battery query (0x0106), optionally setting a mode.

Usage: oppo_probe.py <address> [seconds] [set:off|anc|ambient]

The widget's oppo-bridge holds the same profile, so turn useModeControl off
before running this, or BlueZ will refuse the registration to whichever asks
second.
"""
import datetime
import os
import struct
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

UUID = "0000079a-d102-11e1-9b23-00025b00a5a5"
PROFILE_PATH = "/io/github/ncr/omaphones/oppoprobe"
START = datetime.datetime.now()

SET_PAYLOAD = {"off": "010101", "anc": "010102", "ambient": "010104"}


def stamp():
    return "%7.2fs" % (datetime.datetime.now() - START).total_seconds()


def frame(command, seq, payload=b""):
    inner = struct.pack("<H", command) + bytes([seq & 0xFF]) \
        + struct.pack("<H", len(payload)) + bytes(payload)
    total = 2 + len(inner)
    var = bytearray()
    value = total
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            var.append(byte | 0x80)
        else:
            var.append(byte)
            break
    return b"\xAA" + bytes(var) + b"\x00\x00" + inner


def decode(data):
    out = []
    i = 0
    while i < len(data):
        if data[i] != 0xAA:
            out.append("junk @%d: %02x" % (i, data[i]))
            i += 1
            continue
        value = 0
        shift = 0
        j = i + 1
        while j < len(data):
            byte = data[j]
            value |= (byte & 0x7F) << shift
            shift += 7
            j += 1
            if not (byte & 0x80):
                break
        else:
            break
        if j + 2 > len(data):
            break
        if data[j] != 0 or data[j + 1] != 0:
            out.append("bad header @%d" % i)
            i += 1
            continue
        if j + 2 + 5 > len(data):
            break
        command = data[j + 2:j + 4]
        seq = data[j + 4]
        paylen = data[j + 5] | (data[j + 6] << 8)
        if j + 2 + 5 + paylen > len(data):
            break
        payload = data[j + 7:j + 7 + paylen]
        anc = ""
        for k in range(len(payload) - 2):
            if payload[k] == 0x01 and payload[k + 1] == 0x01:
                v1 = payload[k + 2]
                v2 = payload[k + 3] if k + 3 < len(payload) else 0
                anc = " window 01 01 %02x %02x" % (v1, v2)
                break
        try:
            asc = bytes(payload).decode("ascii")
        except Exception:
            asc = "-"
        out.append("cmd=%s seq=%02x payload=%s%s ascii=%r"
                   % (command.hex(), seq, payload.hex(), anc, asc))
        i = j + 2 + 5 + paylen
    return out, i


class Link:
    def __init__(self, fd, plan):
        self.fd = fd
        self.buffer = bytearray()
        GLib.io_add_watch(fd, GLib.PRIORITY_DEFAULT,
                          GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.on_io)
        delay = 500
        for name, data in plan:
            GLib.timeout_add(delay, lambda n=name, d=data: (self.send(n, d), False)[1])
            delay += 1400

    def on_io(self, _fd, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            print("%s !! closed" % stamp(), flush=True)
            self.fd = -1
            return False
        try:
            data = os.read(self.fd, 4096)
        except OSError as error:
            print("%s !! read err: %s" % (stamp(), error), flush=True)
            self.fd = -1
            return False
        if not data:
            print("%s !! EOF" % stamp(), flush=True)
            self.fd = -1
            return False
        print("%s <<< %s" % (stamp(), data.hex()), flush=True)
        self.buffer += data
        lines, consumed = decode(self.buffer)
        for line in lines:
            print("%s     %s" % (stamp(), line), flush=True)
        if consumed > 0:
            self.buffer = self.buffer[consumed:]
        return True

    def send(self, name, data):
        if self.fd < 0:
            return
        print("%s >>> %s %s" % (stamp(), name, data.hex()), flush=True)
        try:
            os.write(self.fd, data)
        except OSError as error:
            print("%s !! write: %s" % (stamp(), error), flush=True)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: oppo_probe.py <address> [seconds] [set:off|anc|ambient]")
        return 0
    address = argv[0]
    seconds = 25
    wanted = None
    for arg in argv[1:]:
        if arg.startswith("set:"):
            wanted = arg.split(":", 1)[1].strip().lower()
            if wanted not in SET_PAYLOAD:
                sys.exit("unknown mode %r (off, anc, ambient)" % wanted)
        else:
            seconds = int(arg)

    plan = [
        ("query-anc", frame(0x010C, 0x01, bytes.fromhex("0101"))),
        ("query-battery", frame(0x0106, 0x02)),
    ]
    if wanted is not None:
        plan.append(("set-%s" % wanted,
                     frame(0x0404, 0x03, bytes.fromhex(SET_PAYLOAD[wanted]))))
        plan.append(("query-anc-after", frame(0x010C, 0x04, bytes.fromhex("0101"))))

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    loop = GLib.MainLoop()
    link = {"l": None}

    objects = dbus.Interface(
        bus.get_object("org.bluez", "/"),
        "org.freedesktop.DBus.ObjectManager").GetManagedObjects()
    device_path = None
    for path, interfaces in objects.items():
        device = interfaces.get("org.bluez.Device1")
        if device and str(device.get("Address", "")).upper() == address.upper():
            device_path = str(path)
            break
    if not device_path:
        sys.exit("no paired device with address %s" % address)

    class Profile(dbus.service.Object):
        @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
        def Release(self):
            pass

        @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}",
                             out_signature="")
        def NewConnection(self, _path, fd, _properties):
            print("%s == connected" % stamp(), flush=True)
            link["l"] = Link(fd.take(), plan)

        @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
        def RequestDisconnection(self, _path):
            print("%s == BlueZ asked to disconnect" % stamp(), flush=True)

    Profile(bus, PROFILE_PATH)
    manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"),
                             "org.bluez.ProfileManager1")
    manager.RegisterProfile(PROFILE_PATH, UUID, {
        "Name": "Oppo probe",
        "Role": "client",
        "Channel": dbus.UInt16(0),
        "RequireAuthentication": dbus.Boolean(False),
        "RequireAuthorization": dbus.Boolean(False),
        "AutoConnect": dbus.Boolean(False),
    })

    dev = dbus.Interface(bus.get_object("org.bluez", device_path), "org.bluez.Device1")

    def connect(attempt=0):
        def failed(error):
            print("%s ConnectProfile: %s" % (stamp(), error.get_dbus_message()), flush=True)
            if attempt < 10:
                GLib.timeout_add(1500, lambda: connect(attempt + 1))

        dev.ConnectProfile(UUID, reply_handler=lambda: None,
                           error_handler=failed, timeout=30)
        return False

    GLib.timeout_add(500, connect)
    GLib.timeout_add_seconds(seconds, lambda: (loop.quit(), False)[1])
    loop.run()
    try:
        manager.UnregisterProfile(PROFILE_PATH)
    except dbus.DBusException:
        pass
    print("%s == done" % stamp(), flush=True)


if __name__ == "__main__":
    main()
