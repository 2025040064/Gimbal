from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "k230视觉云台.py"
SPEC = importlib.util.spec_from_file_location("k230_gimbal", SCRIPT)
vision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vision)


class K230GimbalTests(unittest.TestCase):
    def setUp(self):
        self.session = vision.VisionSession(lambda now, before: now - before)
        self.first_card = (30, 35, 30, 40)
        self.larger_card = (200, 100, 80, 100)

    def confirm(self, cards, start=0):
        for frame in range(vision.CONFIRM_FRAMES):
            result = self.session.observe(cards, start + 33 * frame)
        return result

    def test_camera_only_previews_without_uart_or_recognition(self):
        sensor = Mock()
        frames = [Mock(), Mock()]
        sensor.snapshot.side_effect = [RuntimeError("sensor(0) snapshot chn(0) failed(3)"),
                                       *frames, KeyboardInterrupt()]
        media = Mock()
        modules = {
            "image": None,
            "machine": None,
            "media": SimpleNamespace(),
            "media.sensor": SimpleNamespace(Sensor=Mock(return_value=sensor)),
            "media.display": None,
            "media.media": SimpleNamespace(MediaManager=media),
        }
        with (
            patch.dict(sys.modules, modules),
            patch.multiple(time, sleep_ms=Mock(), ticks_ms=lambda: 0,
                           ticks_diff=lambda a, b: a-b, create=True),
            patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
            patch.object(vision, "CAMERA_ONLY", True, create=True),
            redirect_stdout(io.StringIO()) as console,
        ):
            vision.main()

        modules["media.sensor"].Sensor.assert_called_once_with(width=640, height=480, fps=30)
        sensor.run.assert_called_once_with()
        sensor.stop.assert_called_once_with()
        media.deinit.assert_called_once_with()
        for frame in frames:
            frame.compress_for_ide.assert_called_once_with()
        self.assertIn("[OK] FIRST_PREVIEW", console.getvalue())

    def test_select_id_zero_over_larger_distractor(self):
        self.assertTrue(self.session.command(b"ID,0", 0))
        confirmed, _, _ = self.confirm([(0, self.first_card), (9, self.larger_card)])
        frame = self.session.packet(confirmed)
        self.assertEqual(frame, b"\xAA\x55640,480,45,55,30,40,513,2,0,3\r\n")

    def test_loss_sends_no_target_and_reacquires_only_original_id(self):
        self.session.command(b"ID,2", 0)
        self.confirm([(2, self.first_card), (8, self.larger_card)])
        confirmed, _, _ = self.session.observe([(8, self.larger_card)], 2000)
        self.assertEqual(self.session.target_id, 2)
        self.assertEqual(
            self.session.packet(confirmed),
            b"\xAA\x55640,480,-1,-1,-1,-1,256,2,2,4\r\n",
        )
        new_box = (390, 255, 40, 50)
        for frame in range(vision.CONFIRM_FRAMES - 1):
            confirmed, _, _ = self.session.observe([(2, new_box)], 2100 + 33 * frame)
            self.assertNotIn(2, confirmed)
        confirmed, _, _ = self.session.observe([(2, new_box)], 2200)
        self.assertEqual(confirmed[2], new_box)

    def test_duplicate_id_and_unconfirmed_position_jump_are_rejected(self):
        self.session.command(b"ID,6", 0)
        self.confirm([(6, self.first_card)])
        confirmed, _, _ = self.session.observe([(6, self.larger_card)], 200)
        self.assertNotIn(6, confirmed)
        confirmed, _, _ = self.confirm([(6, self.first_card), (6, self.larger_card)], 300)
        self.assertNotIn(6, confirmed)

    def test_scan_reports_unique_ids_until_stm32_stops_it(self):
        self.assertTrue(self.session.command(b"SCAN", 100))
        _, new_ids, _ = self.confirm([(2, self.first_card), (0, self.larger_card)], 100)
        self.assertEqual(new_ids, (0, 2))
        _, new_ids, _ = self.session.observe([(2, self.first_card)], 400)
        self.assertEqual(new_ids, ())
        _, _, result = self.session.observe([], 60100)
        self.assertIsNone(result)
        self.assertEqual(self.session.mode, vision.VISION_SCAN)
        self.session.command(b"STOP", 60101)
        self.assertEqual(self.session.take_scan_result(), (0, 2))
        self.assertIsNone(self.session.take_scan_result())
        self.session.command(b"SCAN", 60200)
        _, new_ids, _ = self.confirm([(0, self.first_card)], 60200)
        self.assertEqual(new_ids, (0,))

    def test_stop_reports_scan_once_even_when_no_cards_were_found(self):
        for cards, expected in (([(10, self.first_card)], (10,)), ([], ())):
            self.assertTrue(self.session.command(b"SCAN", 100))
            self.confirm(cards, 100)
            self.assertTrue(self.session.command(b"STOP", 500))
            self.assertEqual(self.session.observe([], 501)[2], expected)
            self.assertIsNone(self.session.observe([], 502)[2])

    def test_terminal_accepts_cr_lf_and_crlf(self):
        reader = vision.CommandReader()
        self.assertEqual(list(reader.feed(b"SCAN\rID,10\nSTOP\r\n")),
                         [b"SCAN", b"ID,10", b"STOP"])

    def test_default_preview_does_not_open_command_input(self):
        uart = Mock()
        select = SimpleNamespace(poll=Mock())
        with patch.dict(sys.modules, {"select": select}), patch.object(vision, "COMMAND_INPUT", "none"):
            self.assertIsNone(vision.open_command_input(uart))
        select.poll.assert_not_called()
        uart.read.assert_not_called()

    def test_usb_read_checks_readiness_and_limits_input_per_frame(self):
        stream = io.StringIO("ID,10\rSCAN\n")
        poller = Mock()
        poller.poll.side_effect = lambda timeout: [(stream, 1)] if stream.tell() < 11 else []
        read = vision.USBCommandInput(stream, poller, 1)
        self.assertEqual(read(6), b"ID,10\r")
        self.assertEqual(read(32), b"SCAN\n")
        self.assertEqual(read(32), b"")
        self.assertTrue(all(call.args == (0,) for call in poller.poll.call_args_list))

    def test_commands_handle_split_lines_and_discard_oversize_lines(self):
        reader = vision.CommandReader()
        self.assertEqual(list(reader.feed(b"ID,")), [])
        self.assertEqual(list(reader.feed(b"0\r")), [b"ID,0"])
        self.assertEqual(list(reader.feed(b"\nSCAN\n")), [b"SCAN"])
        self.assertEqual(list(reader.feed(b"1234567890ID,6\nID,9\n")), [b"ID,9"])
        self.assertFalse(self.session.command(b"ID,10", 0))
        self.assertTrue(self.session.command(b"ID,9", 0))
        self.assertEqual(self.session.target_id, 9)
        self.assertTrue(self.session.command(b"STOP", 0))
        self.assertFalse(self.session.command(b"ID,-1", 0))
        self.assertIsNone(self.session.target_id)

    def test_repeated_selection_keeps_confirmation_and_stop_clears_it(self):
        self.session.command(b"ID,3", 0)
        self.confirm([(3, self.first_card)])
        self.session.command(b"ID,3", 200)
        confirmed, _, _ = self.session.observe([(3, self.first_card)], 201)
        self.assertEqual(confirmed[3], self.first_card)
        self.session.command(b"STOP", 300)
        self.session.command(b"ID,3", 301)
        confirmed, _, _ = self.session.observe([(3, self.first_card)], 302)
        self.assertNotIn(3, confirmed)

    def test_scan_waits_for_stop_across_device_tick_wrap(self):
        period = 1 << 20
        session = vision.VisionSession(
            lambda now, before: (now - before + period // 2) % period - period // 2
        )
        session.command(b"SCAN", period - 100)
        self.assertIsNone(session.observe([], 59900)[2])
        session.command(b"STOP", 60000)
        self.assertEqual(session.take_scan_result(), ())

    def test_main_receives_stm32_commands_and_sends_selected_target(self):
        now = 0
        previews, writes = [], []
        uart = Mock()
        pending = [b"STOP\n", b"ID,0\n"]
        uart.any.side_effect = lambda: len(pending[0]) if pending else 0
        uart.read.side_effect = lambda size: pending.pop(0)
        uart.write.side_effect = lambda frame: writes.append((now, frame)) or len(frame)

        def snapshot(chn=0):
            nonlocal now
            now += 50
            if now > 700:
                raise KeyboardInterrupt()
            frame = Mock()
            frame.compress_for_ide.side_effect = lambda: previews.append(now)
            return frame

        sensor = Mock()
        sensor.snapshot.side_effect = snapshot
        modules = {
            "image": SimpleNamespace(Image=Mock(), GRAYSCALE=0),
            "machine": SimpleNamespace(FPIOA=Mock(), UART=Mock(return_value=uart)),
            "media": SimpleNamespace(),
            "media.sensor": SimpleNamespace(Sensor=Mock(return_value=sensor)),
            "media.display": None,
            "media.media": SimpleNamespace(MediaManager=Mock()),
        }
        with (
            patch.dict(sys.modules, modules),
            patch.multiple(time, ticks_ms=lambda: now, ticks_diff=lambda a, b: a - b,
                           sleep_ms=Mock(), create=True),
            patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
            patch.object(vision, "detect_cards", return_value=[(0, self.first_card), (8, self.larger_card)]),
            redirect_stdout(io.StringIO()) as console,
        ):
            vision.main()
        self.assertEqual(previews, list(range(50, 701, 50)))
        payloads = [packet[2:-2].split(b",") for _, packet in writes]
        self.assertTrue(all(len(fields) == 10 for fields in payloads))
        self.assertTrue(any(fields[7:9] == [b"0", b"-1"] for fields in payloads))
        tracked = [fields for fields in payloads if fields[2] == b"45"]
        self.assertTrue(tracked)
        self.assertTrue(all(fields[2:6] == [b"45", b"55", b"30", b"40"] for fields in tracked))
        self.assertTrue(all(fields[7:9] == [b"2", b"0"] for fields in tracked))
        self.assertEqual(payloads[-1][7], b"3")  # Shutdown reports FAULT.
        self.assertIn("TRACK,0", console.getvalue())
        self.assertIn("[RX] ID,0", console.getvalue())
        uart.deinit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
