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

## Owner check needed before merge

This follow-up has not been run on CMF hardware by the maintainer. Please
confirm these steps on the updated PR branch, using the existing test setup:

1. Record the initial mode, ANC strength, latency and battery reading. Confirm
   the Bluetooth **Name**, not just Alias, is `CMF Headphone Pro`.
2. Connect normally and confirm the mode controls and single battery appear.
   The bridge should connect directly on 28. Repeat after a disconnect and
   reconnect and confirm the controls recover.
3. Through the panel, set Off, Ambient and ANC; then Low, Mid, High and
   Adaptive; then low latency on and off. Record the reported results after
   each change, not just that the click was accepted.
4. Restore the original settings. Report the tested commit, any failures,
   and whether another connected device remained unaffected, if available.

Charging, acoustic effects, radio timing and firmware variants remain outside
these software checks. Another headset is optional; mark its isolation check
untested if unavailable. The version remains 1.3.0 until owner confirmation
and successful CI permit the merge and patch release.
