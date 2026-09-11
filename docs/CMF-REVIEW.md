# CMF Headphone Pro review follow-up

The channel change is selected by the name reported by the headset, passed
from DeviceFollower through Model.js to nothing-bridge. Known legacy Nothing
models keep channel 15 even after a refusal. CMF Headphone Pro uses only 28.
Unknown names can try 15 then 28; an old call without a name retains only 15.
No protocol parser, outgoing command payload, owner pin or capture is changed.
The standalone probe keeps its old default of 15; CMF probing uses
`tools/nothing_probe.py --channel 28 <address>` with mode control disabled.

## Evidence and software checks

`tests/nothing_cmf_test.py` supplements the author's original pin with full
frames from `docs/captures/nothing-headphone-pro.txt`. It checks all 64
unredacted TX/RX frames, every split point of each RX frame, all exposed mode,
ANC-strength and latency commands against captured writes, ACK/read-back,
unsolicited reports, deduplication and damaged-frame recovery. Simulated
socket refusal verifies retry ordering and cleanup. A controlled clock drives
the real run loop through info/query timeout and EOF, then a fresh bridge
recovers using its own reports. These are software replays and synthetic
connection failures, not new hardware observations.

The original `headphone-pro.json` and `ear-a.json` pins remain byte-for-byte
unchanged. The CMF pin's device-info payload `00` is a synthetic handshake
placeholder, not the ASCII device-info answer recorded by the owner. Its
structured replies are re-encoded by the old harness; they are not full raw
packet evidence. The supplemental replay uses captured packets directly.
The capture explicitly redacts the device-info serial, invalidating its
original checksum, so that one frame is excluded rather than reconstructed
and called observed. The real loop's info timeout is exercised separately.
The earlier framing tests now use complete captured ANC/battery literals
instead of asking the encoder under test to manufacture incoming packets.

## Owner confirmation for 1.3.1

On 2026-09-11, [@adilahmad17 confirmed commit 22497ef on his CMF Headphone Pro](https://github.com/ncr/omarchy-headphones/pull/12#issuecomment-5627277481)
and accepted the review changes, including the channel-selection tests.
He copied the changed bridge, Model.js, DeviceFollower.qml and probe into his
plugin and restarted the shell. The maintainer has not independently tested CMF.

- Bluetooth Name, not just Alias: `CMF Headphone Pro`.
- Initial state: ANC / Adaptive, low latency off, battery 20%.
- Normal connection: named bridge invocation selects only channel 28; mode
  controls and a single battery appeared. No earbud or case components.
- Disconnect/reconnect: controls recovered in about six seconds, returning to
  ANC / Adaptive / latency off. A brief unsupported state occurred while the
  first connection attempts were refused and retried.
- Panel sweep: Off / Ambient / ANC, Low / Mid / High / Adaptive and low latency
  on / off each produced the expected reported state.
- Restoration: original ANC / Adaptive / latency-off settings restored.

PR CI passed for that same commit. The release changes after 22497ef update
README, metadata and this record; they do not alter the tested bridge or QML.

## Remaining limits

Second-connected-device isolation was not completed: the other available
headset was another CMF model outside this PR, and Headphone Pro powered off
at low battery before an unrelated headset could be used. Charging-state
frames, acoustic effects, radio timing and firmware variants remain untested.
Software isolation and fault checks do not substitute for those hardware tests.

The gallery retains the owner's original 1120×840 screenshot. Its fixed-height
crop cuts through the low-latency row. No missing UI or hardware evidence has
been reconstructed; the complete control sweep is documented in the linked
owner confirmation above.
