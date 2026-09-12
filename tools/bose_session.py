#!/usr/bin/env python3
"""Full Bose QC45 BMAP driving session.

Usage: bose_session.py <address> [seconds-per-step]

Opens RFCOMM channel 8 (the QC45's BMAP channel), inits with a [0.1] GET, reads
battery, dumps the mode table, then drives every mode index 0..3 via START
[31.3], watching for unsolicited pushes after each switch and reading the mode
back. Always restores the mode that was current when the session started. Every
raw frame the device sends is printed on its own line, decoded as [block.func]
where possible.
"""
import socket
import sys
import time

ADDR = sys.argv[1].upper() if len(sys.argv) > 1 else sys.exit("usage: bose_session.py <address> [wait]")
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
CH = 8
start = time.monotonic()
OP = {0: "SET", 1: "GET", 2: "SETGET", 3: "STATUS", 4: "ERROR",
      5: "START", 6: "RESULT", 7: "PROCESSING"}


def stamp():
    return "%7.2fs" % (time.monotonic() - start)


def describe(data):
    out = []
    pos = 0
    while pos + 4 <= len(data):
        fblock, func = data[pos], data[pos + 1]
        flags, length = data[pos + 2], data[pos + 3]
        if pos + 4 + length > len(data):
            out.append("[%d.%d] trailing %s" % (fblock, func, data[pos:].hex()))
            break
        payload = data[pos + 4:pos + 4 + length]
        op = OP.get(flags & 0x0f, "op%d" % flags)
        if (flags & 0x0f) == 4 and payload:
            out.append("[%d.%d] %s error=%02x" % (fblock, func, op, payload[0]))
        elif (fblock, func) == (31, 6) and op == "STATUS" and len(payload) == 47:
            idx = payload[0]
            name = payload[6:].split(b"\x00", 1)[0].decode("utf-8", "replace")
            out.append("[31.6] STATUS mode%d '%s' %s" % (idx, name, payload.hex()))
        else:
            out.append("[%d.%d] %s %s" % (fblock, func, op, payload.hex()))
        pos += 4 + length
    return out


sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
sock.settimeout(0.3)
print("%s == connect channel %d %s" % (stamp(), CH, ADDR), flush=True)
sock.connect((ADDR, CH))
print("%s == connected" % stamp(), flush=True)


def exchange(frame, label, listen=0.0, wait=WAIT):
    print("%s >>> %-30s %s" % (stamp(), label, frame.hex()), flush=True)
    sock.sendall(frame)
    got = b""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            print("%s !! closed" % stamp(), flush=True)
            return
        got += data
    if got:
        for line in describe(got):
            print("%s <<< %s" % (stamp(), line), flush=True)
    else:
        print("%s <<< (no reply)" % stamp(), flush=True)
    if listen > 0:
        end = time.monotonic() + listen
        while time.monotonic() < end:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                return
            for line in describe(data):
                print("%s <<< %s" % (stamp(), line), flush=True)


exchange(bytes([0x00, 0x01, 0x01, 0x00]), "[0.1] init GET")
exchange(bytes([0x02, 0x02, 0x01, 0x00]), "[2.2] GET battery")
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET current mode", wait=4)
exchange(bytes([0x1f, 0x01, 0x05, 0x00]), "[31.1] START GetAll", wait=6)

exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET current mode")
exchange(bytes([0x1f, 0x03, 0x05, 0x02, 0x00, 0x00]), "START [31.3] -> mode 0",
         listen=4)
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET readback")
exchange(bytes([0x1f, 0x03, 0x05, 0x02, 0x01, 0x00]), "START [31.3] -> mode 1",
         listen=4)
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET readback")
exchange(bytes([0x1f, 0x03, 0x05, 0x02, 0x02, 0x00]), "START [31.3] -> mode 2",
         listen=4)
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET readback")
exchange(bytes([0x1f, 0x03, 0x05, 0x02, 0x03, 0x00]), "START [31.3] -> mode 3",
         listen=4)
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET readback")

print("%s == restoring mode 1" % stamp(), flush=True)
exchange(bytes([0x1f, 0x03, 0x05, 0x02, 0x01, 0x00]), "START [31.3] -> mode 1",
         listen=2)
exchange(bytes([0x1f, 0x03, 0x01, 0x00]), "[31.3] GET restore check")
sock.close()
print("%s == done" % stamp(), flush=True)