# The two reference models

**JBL TUNE230NC TWS and Sony WH-CH720N are the canonical reference models,
prepared and tested by the maintainer, @ncr, on his own headphones.** Use their
coverage as the example for adding support. Use your own device's replies,
UUIDs, capabilities and owner name; do not copy their protocol bytes into a
model that has never answered them.

Canonical means evidence plus regression coverage, not that these headphones
represent every brand. Other owners' existing pins remain equally binding.

The expanded coverage requirement applies to new models and brands only.
Existing supported models keep their current tests and evidence; owners do
not have to fill historical gaps to remain supported. A change to an existing
model must test the changed behaviour and be confirmed by its owner, without
requiring a complete coverage retrofit. Existing pins remain binding.

## Read these together

| Layer | Reference | What it proves |
|:--|:--|:--|
| Evidence | `docs/captures/sony-wh-ch720n.txt`, `jbl-tune230nc-tws.txt` and their `-bluetoothctl.txt` files | Selected real HCI packets from 2026-09-08 and complete SDP records |
| Evidence index | `tests/fixtures/canonical.json`, `tests/canonical_evidence_test.py` | Each indexed RX frame occurs in the exact named packet in its capture |
| Sony session | `tests/pins/sony/wh-ch720n-canonical.json` | Real complete RX frames; Off/ANC/Ambient, Ambient 0/5/20, Focus on voice on/off; exact outgoing payloads |
| JBL session | `tests/pins/jbl/tune230nc-tws-canonical.json` | All four mode answers including TalkThru; exact outgoing commands; repeated reports |
| Bridge faults | `tests/canonical_bridges_test.py` | Fragmentation, checksum damage, queued commands and ACK timeout (Sony); malformed reports, discovery/subscription failures and timeout races (JBL) |
| Battery and lifecycle | `tests/gfps_reader_test.py` | Real one-battery Sony and three-component JBL frames; partial/glued reads, last reading at hangup, reconnect state, refresh, device isolation and unfollow |
| Shell decisions | `tests/model.test.js` | Both complete UUID lists select the correct backend and arguments; existing battery, routing and device-selection tests |
| Live integration | `tools/check-live`, `docs/captures/canonical-live.json` | Owner-run IPC through QML and real bridges, all controls, battery snapshots, mode persistence across refresh, mode recovery after reconnect, peer isolation and restoration |

The original `wh-ch720n.json` and `tune230nc-tws.json` pins are unchanged.
The new pins supplement them. Replays select real frames into a deterministic
conversation; they do not claim the recording's exact timing or ordering.
Sony's new pin feeds complete captured frames, including their checksum, so
it does not generate its own incoming packets with the encoder under test.
JBL's HCI notification payloads are rendered in the client line format that
its bridge consumes. Fast Pair frames are tested directly through the reader.

## What to bring for a new model

1. Keep your real probe output or decoded HCI packets and complete
   `bluetoothctl info` output. Name the capture from your new pin. Keep packet
   identifiers when extracting selected packets; say what was omitted.
2. Pin the initial handshake/query and the exact commands sent. Feed the
   answers your headphones actually gave for **every control you expose**.
   Check that sending a command alone cannot change the reported UI state.
3. Cover unsolicited state changes, repeated reports and unsupported commands.
   For a stream protocol, split a recorded frame at every byte boundary, join
   frames, and test damaged/truncated input. Label corrupted test data as fault
   injection, never as something the device answered.
4. Cover the battery shape your device reports: one figure or separate
   components. Check charging/unknown handling with clearly labelled synthetic
   boundary cases when no such recording is available. Include shared-reader
   routing if using Fast Pair.
5. Cover silence versus connection failure, queue/ACK behaviour where relevant,
   disconnect cleanup and recovery. Another connected device must keep its
   own state. A new model adds its own pin; it does not rewrite these references.
6. Run `tools/check`. Then run a live smoke test on your headphones and record
   initial settings, requested changes, **reported** results, restoration and
   failures. For a capability your model does not have, say not applicable.
   Document anything that remains untested; a green unit suite is not hardware
   confirmation.

## Repeat the owner's live check

Run from an isolated checkout, with both pairs connected and their bridges
ready. It temporarily changes modes and restores them in a `finally` block.
The explicit reconnect option briefly interrupts audio on the selected pair.

```bash
tools/check-live --sony 88:92:CC:D1:B1:F2 --jbl 78:5E:A2:76:7F:20 \
  --refresh --reconnect --output /tmp/omaphones-live.json
```

Use a new output path for each run. Hardware tests never run in CI or inside
`tools/check`. Do not edit the installed plugin or its repository metadata
while taking a measurement: hot reload invalidates the session. A run during
this work was rejected when concurrent plugin reloads interrupted JBL; the
saved successful run was repeated without concurrent file operations.

## Limits we keep visible

The captured battery samples are not charging samples. Charging/unknown tests
are synthetic protocol inputs, not a claim of a physical charging test. The
live checker reads the plugin's public state; it does not measure acoustic
noise reduction, assess audio quality or inspect screenshots. It verifies
mode persistence after a refresh request and mode recovery after reconnect,
not fresh Fast Pair battery delivery or uninterrupted telemetry. In particular,
Sony mode control uses a separate channel, so a successful mode check cannot
prove that a Fast Pair refresh succeeded. The historical live report
labels this check `refresh`; interpret it only as mode persistence. Bluetooth radio timing, firmware variations, touch controls and
case-open/closed transitions still need owner testing. No percentage of code
coverage is claimed.
