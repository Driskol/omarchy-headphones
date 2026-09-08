"""Evidence shared by the two owner's reference models, not generated frames."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
MODELS = json.loads((ROOT / 'tests/fixtures/canonical.json').read_text())


def frame(brand, group, label):
    return bytes.fromhex(MODELS[brand][group][label]['hex'])


def packets(brand):
    text = (ROOT / MODELS[brand]['capture']).read_text()
    out = {}
    for block in re.split(r'(?=^\S)', text, flags=re.M):
        match = re.search(r'#(\d+)\s', block.splitlines()[0] if block else '')
        if match:
            out[int(match[1])] = b''.join(bytes.fromhex(m[1]) for m in re.finditer(
                r'^        ((?:[0-9a-f]{2} ?)+)(?=  |$)', block, re.M))
    return out
