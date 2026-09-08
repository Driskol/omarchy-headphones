"""A fixture is evidence only if its bytes occur in the named captured packet."""
import unittest
import json
from tests import canonical


class Evidence(unittest.TestCase):
    def test_canonical_pins_use_only_recorded_mode_bytes(self):
        for brand, pin_name in (('sony', 'wh-ch720n'), ('jbl', 'tune230nc-tws')):
            pin = json.loads((canonical.ROOT / f'tests/pins/{brand}/{pin_name}-canonical.json').read_text())
            self.assertEqual(pin['owner'], 'ncr')
            self.assertEqual(pin['capture'], canonical.MODELS[brand]['capture'])
            recorded = list(canonical.packets(brand).values())
            for step in pin['steps']:
                if 'device' in step:
                    device = step['device']
                    if isinstance(device, dict):
                        wire = bytes.fromhex(device['wire'])
                    elif 'data bytes): ' in device:
                        wire = bytes.fromhex(device.split('data bytes): ')[1])
                    else:
                        continue  # Client lifecycle scaffolding, not radio bytes.
                elif 'sent_last' in step:
                    sent = step['sent_last']
                    wire = bytes.fromhex(' '.join(sent.split()[2:]).replace('0x', '')) if brand == 'jbl' else bytes.fromhex(sent)
                else:
                    continue
                self.assertTrue(any(wire in packet for packet in recorded),
                                f'{brand}: pin bytes absent from capture: {wire.hex()}')

    def test_every_reference_frame_exists_in_its_capture(self):
        for brand, model in canonical.MODELS.items():
            packets = canonical.packets(brand)
            for group in ('rx', 'gfps'):
                for label, record in model[group].items():
                    with self.subTest(brand=brand, group=group, label=label):
                        self.assertIn(record['packet'], packets)
                        self.assertIn(bytes.fromhex(record['hex']), packets[record['packet']])

    def test_uuid_records_are_owned_devices_not_example_lists(self):
        for model in canonical.MODELS.values():
            text = (canonical.ROOT / model['uuid_capture']).read_text()
            self.assertIn(model['address'], text)
            self.assertIn('UUID:', text)
