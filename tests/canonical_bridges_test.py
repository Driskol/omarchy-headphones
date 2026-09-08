"""Fault injection around recorded ncr sessions. Fault bytes are not evidence."""
import unittest
from unittest.mock import patch

from tests import canonical
from tests.sony_bridge_test import Session as Sony, bridge_module as sony
from tests.jbl_bridge_test import Session as Jbl, bridge_module as jbl


class SonyReference(unittest.TestCase):
    def ready(self):
        s = Sony(name='WH-CH720N')
        s.receive(canonical.frame('sony', 'rx', 'handshake'))
        s.ack()
        s.receive(canonical.frame('sony', 'rx', 'initial'))
        return s

    def test_every_split_of_a_real_frame_is_inert_until_complete(self):
        wire = canonical.frame('sony', 'rx', 'ambient')
        for split in range(1, len(wire)):
            with self.subTest(split=split):
                s = self.ready()
                before = list(s.frames)
                s.receive(wire[:split])
                self.assertEqual(s.lines[-1]['mode'], 'anc')
                self.assertEqual(s.frames, before)
                s.receive(wire[split:])
                self.assertEqual(s.lines[-1]['mode'], 'ambient')
                # This is a literal recorded-frame response expectation, not
                # an encode/decode round trip through the same implementation.
                self.assertEqual(s.frames[-1].hex(), '3e010100000000023c')

    def test_glued_recorded_notifications_and_duplicate_are_acknowledged(self):
        s = self.ready()
        ambient = canonical.frame('sony', 'rx', 'ambient')
        off = canonical.frame('sony', 'rx', 'off')
        before = len(s.frames)
        s.receive(ambient + ambient + off)
        self.assertEqual([line['mode'] for line in s.lines], ['anc', 'ambient', 'off'])
        self.assertEqual(len(s.frames), before + 3)
        self.assertEqual(s.bridge.buffer, bytearray())

    def test_bad_checksum_is_not_acked_or_displayed_then_valid_frame_recovers(self):
        s = self.ready()
        bad = bytearray(canonical.frame('sony', 'rx', 'ambient'))
        bad[-2] ^= 1
        before = list(s.frames)
        s.receive(bytes(bad))
        self.assertEqual(s.frames, before)
        self.assertEqual(s.lines[-1]['mode'], 'anc')
        s.receive(canonical.frame('sony', 'rx', 'ambient'))
        self.assertEqual(s.lines[-1]['mode'], 'ambient')

    def test_noise_before_a_valid_frame_is_discarded(self):
        s = self.ready()
        s.receive(b'noise\x00\xff' + canonical.frame('sony', 'rx', 'off'))
        self.assertEqual(s.lines[-1]['mode'], 'off')

    def test_invalid_or_unsupported_commands_send_nothing(self):
        for s in (Sony(name='WH-CH720N'), self.ready()):
            before = list(s.frames)
            commands = ('', 'set', 'set talkthru', 'set nonsense', 'level nan', 'voice maybe', 'latency on')
            for command in commands:
                s.command(command)
            self.assertEqual(s.frames, before)
        s = Sony(name='WH-CH720N')
        s.command('set anc'); s.command('level 5'); s.command('voice on')
        self.assertEqual(s.frames, [])

    def test_settings_change_only_when_device_reports_them(self):
        s = self.ready()
        s.command('level 5'); s.ack()
        self.assertEqual(s.lines[-1]['level'], 14)
        s.receive(canonical.frame('sony', 'rx', 'level5'))
        self.assertEqual(s.lines[-1]['level'], 5)
        s.command('set off')
        self.assertEqual(s.sent[-1], '68 17 01 00 00 00 05')

    def test_ack_timeout_moves_queue_and_old_timeout_cannot_free_new_command(self):
        s = self.ready()
        s.command('set off')
        serial = s.bridge.sent
        s.command('set ambient')
        self.assertEqual(s.sent[-1], '68 17 01 00 00 00 0e')
        s.bridge.on_ack_timeout(serial)
        self.assertEqual(s.sent[-1], '68 17 01 01 01 00 0e')
        self.assertTrue(s.bridge.waiting)
        s.bridge.on_ack_timeout(serial)
        self.assertTrue(s.bridge.waiting)
        self.assertIsNone(s.bridge.exit_code)

    def test_unanswered_handshake_is_transient_not_unsupported(self):
        s = Sony(name='WH-CH720N')
        s.bridge.send_init(1)
        for _ in range(sony.INIT_ATTEMPTS):
            s.fire()
        self.assertEqual(s.sent, ['00 00'] * sony.INIT_ATTEMPTS)
        self.assertEqual(s.bridge.exit_code, sony.EXIT_TRANSIENT)

    def test_disconnect_or_read_failure_ends_once(self):
        for condition in (sony.GLib.IO_HUP, sony.GLib.IO_ERR):
            s = self.ready()
            self.assertFalse(s.bridge.on_io(-1, condition))
            self.assertEqual(s.bridge.exit_code, sony.EXIT_TRANSIENT)
            count = len(s.lines)
            s.bridge.finish(0, 'second ending')
            self.assertEqual(len(s.lines), count)
        s = self.ready()
        with patch.object(sony.os, 'read', side_effect=OSError('lost')):
            self.assertFalse(s.bridge.on_io(-1, sony.GLib.IO_IN))
        self.assertEqual(s.bridge.exit_code, sony.EXIT_TRANSIENT)


class JblReference(unittest.TestCase):
    def session(self):
        s = Jbl()
        self.addCleanup(s.close)
        return s

    def notify(self, s, mode):
        data = canonical.frame('jbl', 'rx', mode).hex(' ')
        s.device('Handle Value Not/Ind: 0x000c - (10 data bytes): ' + data)

    def test_all_four_real_answers_and_spontaneous_changes(self):
        s = self.session()
        for mode in ('off', 'anc', 'ambient', 'talkthru'):
            self.notify(s, mode)
            self.assertEqual(s.lines[-1], {'modes': True, 'mode': mode})
        self.assertEqual(s.support, [('answered', '0x1234')])
        self.assertEqual(s.sent, [])

    def test_set_is_not_a_report(self):
        s = self.session()
        self.notify(s, 'off')
        s.command('set anc')
        self.assertEqual(s.lines, [{'modes': True, 'mode': 'off'}])
        self.notify(s, 'anc')
        self.assertEqual(s.lines[-1]['mode'], 'anc')

    def test_short_or_other_protocol_lines_do_not_fabricate_a_mode(self):
        s = self.session()
        self.notify(s, 'ambient')
        for line in ('', 'random log', 'aa 91 07 12',
                     'aa 91 07 12 01 00 02 00', 'aa 92 07 12 01 00 02 00 03 00'):
            s.device(line)
        self.assertEqual(s.lines, [{'modes': True, 'mode': 'ambient'}])
        self.notify(s, 'anc')
        self.assertEqual(s.lines[-1]['mode'], 'anc')

    def test_unrecognised_commands_send_nothing(self):
        s = self.session()
        for line in ('', 'set', 'set unknown', 'level 5', 'voice on', 'latency on'):
            s.command(line)
        self.assertEqual(s.sent, [])

    def test_discovery_or_subscription_failure_never_marks_model_unsupported(self):
        for line in ('GATT discovery procedures failed', 'Failed to register notify handler',
                     'GATT client not initialized', 'Device disconnected'):
            with self.subTest(line=line):
                s = self.session()
                s.device(line)
                self.assertEqual(s.bridge.exit_code, jbl.EXIT_TRANSIENT)
                self.assertEqual(s.support, [])
                self.assertFalse(s.bridge.remember_miss())
                self.assertEqual(s.bridge.start(), jbl.EXIT_TRANSIENT)

    def test_a_report_that_beats_timeout_cannot_be_recorded_as_a_miss(self):
        s = self.session()
        self.notify(s, 'anc')
        self.assertFalse(s.bridge.remember_miss())
        self.assertEqual(s.support, [('answered', '0x1234')])

    def test_first_exit_wins_and_wakes_every_startup_wait(self):
        s = self.session()
        s.bridge.finish(0)
        s.bridge.finish(jbl.EXIT_TRANSIENT, 'late EOF')
        self.assertEqual(s.bridge.exit_code, 0)
        self.assertEqual(s.lines, [])
        for event in (s.bridge.discovered, s.bridge.registered, s.bridge.answered):
            self.assertTrue(event.is_set())
        self.assertEqual(s.bridge.start(), 0)
