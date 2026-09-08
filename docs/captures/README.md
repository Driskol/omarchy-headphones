# Captures

What a device actually said, kept verbatim. A pin in `tests/pins/` is laid
out from `PROTOCOL.md`; a capture is what `PROTOCOL.md` was written from.
When a review asks "did this headset ever answer that frame", the answer is
`grep` here rather than a memory.

One file per model, `<brand>-<model>.txt`, the output of the brand's probe in
`tools/` (or of an HCI snoop, decoded), unedited but for the parts that
identify you if you want them out. Name it from the pin:

```json
"capture": "docs/captures/sony-wh-1000xm4.txt"
```

`tools/check` verifies the file exists. A frame the bridge parses for a model
should appear in that model's capture; one that does not is a guess, and
guesses are what the second rule keeps out.

The models merged before this directory existed have no capture; their
evidence is the tables in `PROTOCOL.md`. New ones come with one.
