# QC45 review and owner confirmation

The original pin, capture and tests are unchanged. Review tests supplement
them with explicitly synthetic transport faults and recorded reply payloads.

## Repair scope

- Init requires STATUS with a version-shaped payload, rejecting GET echoes,
  ERROR and malformed replies. Bytes after init are retained for parsing.
- Probe reset/EOF is transient. Failed candidates close; a clean stop closes
  the candidate and prevents remaining attempts or retry waits.
- Tests drive real loop timeout, scheduled readback, reset and stdin EOF.
- The raw session tool logs RX chunks at receipt, keeps split frames, reads
  initial mode before writes, restores it on interruption and checks readback.
- The diagnostic Profile1 probe drains its queue and closes the descriptor.
- README, manifest and bridge list include Bose. Protocol text no longer
  claims latency or evidence absent from the stored capture.

## Evidence limits

The stored capture proves decoded 90% battery and mode 0–3 replies, including
return to mode 1. It does not include full raw RX headers, a complete UUID
listing, 89% battery or the described failed-channel traces. The original pin
contains an 89% sample: it remains the author's record, but the capture does
not corroborate it. Please supply that recording or explicitly identify the
sample as synthetic in an owner-authored follow-up. Do not invent it.

Channel 8 is confirmed. Candidates 2/9 are exploratory, not proof of another
model's support. Charging, acoustic effects, peer isolation and behavior while
custom slots are configured are unconfirmed. The runtime still exposes only
Quiet/ANC and Aware/Ambient. The original screenshot is retained.

## Owner test on the repaired revision

Use the exact repair commit supplied in the PR message. Save initial settings.

1. Connect QC45 and confirm battery plus the ANC/Ambient row appear.
2. Switch both ways; verify the panel follows the reported mode. Try the
   headset's own mode button and check the next poll follows it.
3. Disconnect/reconnect and confirm control returns. Disable/re-enable mode
   control during startup and confirm no old bridge retains the channel.
4. Run `tools/bose_session.py ADDRESS` with mode control disabled; provide
   the raw log and complete `bluetoothctl info ADDRESS` output. Confirm the
   original mode is restored; report failures or skipped checks explicitly.
5. Restore the plugin setting and headphone mode used before testing.

Do not merge or bump the version until the owner confirms the repaired
transport/control revision. Software checks cannot replace this test.
