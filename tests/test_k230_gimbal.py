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

    def test_select_id_zero_over_larger_distractor_and_keep_wire_format(self):
        self.assertTrue(self.session.command(b"ID,0", 0))
        confirmed, _, _ = self.confirm([(0, self.first_card), (9, self.larger_card)])
        frame = vision.coordinate_frame(confirmed.get(self.session.target_id))
        self.assertEqual(frame, b"\xAA\x55640,480,45,55,30,40\r\n")

    def test_loss_sends_no_target_and_reacquires_only_original_id(self):
        self.session.command(b"ID,2", 0)
        self.confirm([(2, self.first_card), (8, self.larger_card)])
        confirmed, _, _ = self.session.observe([(8, self.larger_card)], 2000)
        self.assertEqual(self.session.target_id, 2)
        self.assertEqual(
            vision.coordinate_frame(confirmed.get(self.session.target_id)),
            b"\xAA\x55640,480,-1,-1,-1,-1\r\n",
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

    def test_scan_reports_unique_ids_and_freezes_at_deadline(self):
        self.assertTrue(self.session.command(b"SCAN", 100))
        _, new_ids, _ = self.confirm([(2, self.first_card), (0, self.larger_card)], 100)
        self.assertEqual(new_ids, (0, 2))
        _, new_ids, _ = self.session.observe([(2, self.first_card)], 400)
        self.assertEqual(new_ids, ())
        _, new_ids, result = self.session.observe([(9, self.first_card)], 60100)
        self.assertEqual(new_ids, ())
        self.assertEqual(result, (0, 2))
        _, _, result = self.session.observe([], 60101)
        self.assertIsNone(result)
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
        with patch.dict(sys.modules, {"select": select}):
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
        self.assertTrue(self.session.command(b"ID,10", 0))
        self.assertEqual(self.session.target_id, 10)
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

    def test_scan_deadline_across_device_tick_wrap(self):
        period = 1 << 20
        session = vision.VisionSession(
            lambda now, before: (now - before + period // 2) % period - period // 2
        )
        start = period - 100
        session.command(b"SCAN", start)
        self.assertIsNone(session.observe([], 59899)[2])
        self.assertEqual(session.observe([], 59900)[2], ())

    def test_main_previews_each_frame_and_sends_only_selected_coordinates(self):
        now = 0
        preview = {}
        writes = []

        def snapshot():
            nonlocal now
            now += 25
            return Mock()

        def show_image(frame):
            preview[now] = [call.args[0] for call in frame.draw_rectangle.call_args_list]
            if now == 325:
                raise KeyboardInterrupt

        def write(frame):
            writes.append((now, frame))
            return len(frame)

        def detect(_):
            cards = [(8, self.larger_card)]
            if now != 250:
                cards.append((0, self.first_card))
            return cards

        uart = Mock()
        read_commands = Mock(side_effect=[b""] * 4 + [b"ID,", b"0\r\n"] + [b""] * 7)
        uart.write.side_effect = write
        sensor = Mock()
        sensor.snapshot.side_effect = snapshot
        display = Mock()
        display.show_image.side_effect = show_image
        modules = {
            "image": SimpleNamespace(Image=Mock(), GRAYSCALE=0),
            "machine": SimpleNamespace(FPIOA=Mock(), UART=Mock(return_value=uart)),
            "media": SimpleNamespace(),
            "media.sensor": SimpleNamespace(Sensor=Mock(return_value=sensor)),
            "media.display": SimpleNamespace(Display=display),
            "media.media": SimpleNamespace(MediaManager=Mock()),
        }
        with (
            patch.dict(sys.modules, modules),
            patch.multiple(time, ticks_ms=lambda: now, ticks_diff=lambda a, b: a - b,
                           sleep_ms=Mock(), create=True),
            patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
            patch.object(vision, "detect_cards", side_effect=detect),
            patch.object(vision, "open_command_input", return_value=read_commands),
            redirect_stdout(io.StringIO()) as console,
        ):
            vision.main()

        self.assertEqual(list(preview), list(range(25, 326, 25)))
        self.assertIn(self.first_card, preview[75])
        self.assertIn(self.first_card, preview[200])
        self.assertNotIn(200, [stamp for stamp, _ in writes])
        self.assertNotIn(self.first_card, preview[250])
        self.assertIn(self.first_card, preview[325])
        selected = b"\xAA\x55640,480,45,55,30,40\r\n"
        missing = b"\xAA\x55640,480,-1,-1,-1,-1\r\n"
        self.assertEqual(writes, [
            (25, missing), (75, missing), (125, missing), (175, missing),
            (225, selected), (275, missing), (325, selected), (325, missing)
        ])
        self.assertIn("LOST,0", console.getvalue())
        self.assertEqual(console.getvalue().count("TRACK,0"), 2)
        display.init.assert_called_once_with(display.VIRT, width=640, height=480, fps=30, to_ide=True)
        uart.deinit.assert_called_once_with()
        machine = modules["machine"]
        machine.FPIOA.return_value.set_function.assert_any_call(
            5, machine.FPIOA.UART2_TXD
        )
        machine.FPIOA.return_value.set_function.assert_called_once()
        uart.read.assert_not_called()
        machine.UART.assert_called_once_with(
            machine.UART.UART2, baudrate=115200, bits=machine.UART.EIGHTBITS,
            parity=machine.UART.PARITY_NONE, stop=machine.UART.STOPBITS_ONE
        )


if __name__ == "__main__":
    unittest.main()
