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
        self.session = vision.VisionSession(3, lambda now, before: now - before)
        self.target = (3, (30, 35, 80, 100), (45, 53, 30, 60))
        self.moved = (3, (40, 37, 80, 100), (54, 57, 30, 60))
        self.distant = (3, (390, 255, 80, 100), (412, 270, 30, 60))
        self.distractor = (8, (200, 100, 110, 140), (230, 130, 60, 85))

    def confirm(self, detection):
        for now in (0, 50):
            self.assertIsNone(self.session.observe([detection], now))
            self.assertEqual(self.session.state, "CONFIRM")
        self.assertEqual(self.session.observe([detection], 100), detection)
        self.assertEqual(self.session.state, "TRACKING")

    def test_target_config_accepts_digits_and_rejects_other_values(self):
        for digit in range(10):
            with self.subTest(digit=digit):
                self.assertEqual(vision.VisionSession(digit, self.session.ticks_diff).target_id, digit)
        for invalid in (None, False, True, -1, 10, "3", 3.0):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "INITIAL_TARGET_ID"):
                vision.VisionSession(invalid, self.session.ticks_diff)

    def test_first_lock_requires_three_nearby_consecutive_frames(self):
        self.assertIsNone(self.session.observe([self.target], 0))
        self.assertIsNone(self.session.observe([self.distractor], 40))
        self.assertEqual(self.session.state, "SEARCH")
        self.assertIsNone(self.session.observe([self.target], 80))
        self.assertIsNone(self.session.observe([self.distant], 120))
        self.assertIsNone(self.session.observe([self.distant], 160))
        self.assertEqual(self.session.observe([self.distant], 200), self.distant)

    def test_tracking_updates_on_the_first_valid_frame_even_at_slow_frame_rates(self):
        self.confirm(self.target)
        self.assertEqual(self.session.observe([self.distractor, self.moved], 425), self.moved)
        self.assertEqual(self.session.last_seen, 425)
        self.assertEqual(self.session.state, "TRACKING")

    def test_short_loss_keeps_last_position_and_resumes_on_one_frame(self):
        self.confirm(self.target)
        self.assertIsNone(self.session.observe([self.distractor], 200))
        self.assertEqual(self.session.state, "HOLD")
        self.assertEqual(self.session.last_detection, self.target)
        self.assertEqual(self.session.last_seen, 100)
        self.assertEqual(self.session.observe([self.moved, self.distractor], 299), self.moved)
        self.assertEqual(self.session.state, "TRACKING")

    def test_long_loss_reacquires_on_the_other_side_with_three_new_frames(self):
        self.confirm(self.target)
        self.assertIsNone(self.session.observe([], 399))
        self.assertEqual(self.session.state, "HOLD")
        self.assertIsNone(self.session.observe([self.moved], 400))
        self.assertEqual(self.session.state, "REACQUIRE")
        self.assertIsNone(self.session.observe([self.distractor], 440))
        self.assertEqual(self.session.state, "OCCLUDED")
        for now in (3500, 3540):
            self.assertIsNone(self.session.observe([self.distant, self.distractor], now))
            self.assertEqual(self.session.state, "REACQUIRE")
        self.assertEqual(self.session.observe([self.distant, self.distractor], 3580), self.distant)
        self.assertEqual(self.session.target_id, 3)

    def test_independent_duplicate_is_ambiguous_and_overlap_is_deduplicated(self):
        overlap = (3, (32, 35, 80, 100), (47, 53, 30, 60))
        for now in (0, 50):
            self.assertIsNone(self.session.observe([self.target, overlap], now))
        self.assertEqual(self.session.observe([self.target, overlap], 100), self.target)
        self.assertIsNone(self.session.observe([self.target, self.distant], 150))
        self.assertEqual(self.session.state, "HOLD")
        self.assertIsNone(self.session.observe([self.distant], 200))
        self.assertEqual(self.session.state, "HOLD")
        self.assertEqual(self.session.observe([self.moved, overlap], 250), self.moved)

    def test_other_digits_do_not_end_search_or_switch_target(self):
        for now in range(0, 65_001, 50):
            self.assertIsNone(self.session.observe([self.distractor], now))
        self.assertEqual(self.session.target_id, 3)
        self.assertEqual(self.session.state, "SEARCH")
        new_session = vision.VisionSession(7, self.session.ticks_diff)
        seven = (7, self.target[1], self.target[2])
        for now in (0, 50):
            self.assertIsNone(new_session.observe([self.target, seven], now))
        self.assertEqual(new_session.observe([self.target, seven], 100), seven)

    def test_hold_deadline_across_device_tick_wrap(self):
        period = 1 << 20
        self.session = vision.VisionSession(
            3, lambda now, before: (now - before + period // 2) % period - period // 2
        )
        for now in (period - 150, period - 100, period - 50):
            self.session.observe([self.target], now)
        self.assertIsNone(self.session.observe([], 249))
        self.assertEqual(self.session.state, "HOLD")
        self.assertIsNone(self.session.observe([], 250))
        self.assertEqual(self.session.state, "OCCLUDED")

    def test_detector_and_uart_keep_glyph_center_and_card_size(self):
        card = (40, 70, 94, 120)
        glyph = (68, 85, 48, 72)
        gray = Mock()
        gray.find_blobs.side_effect = [
            [SimpleNamespace(rect=lambda: card, pixels=lambda: 8000)],
            [SimpleNamespace(rect=lambda: glyph, pixels=lambda: 1200)],
        ]
        template = vision.DIGIT_TEMPLATES[3][0]

        def get_pixel(x, y):
            col = (x - glyph[0]) // 4
            row = (y - glyph[1]) // 4
            return 0 if template[row + 1] & (1 << (vision.DIGIT_COLUMNS - 1 - col)) else 255

        gray.get_pixel.side_effect = get_pixel
        detections = vision.detect_cards(gray)
        self.assertEqual(detections, [(3, card, glyph)])
        self.assertEqual(vision.coordinate_frame(detections[0]), b"\xAA\x55640,480,92,121,94,120\r\n")
        self.assertEqual(vision.coordinate_frame(None), b"\xAA\x55640,480,-1,-1,-1,-1\r\n")

    def test_main_keeps_preview_sends_fresh_coordinates_and_ignores_old_commands(self):
        timestamps = (25, 50, 75, 100, 125, 150, 175, 200, 225, 300, 425, 3500, 3550, 3600, 10_000)
        stamps = iter(timestamps)
        now = 0
        preview = {}
        writes = []

        def snapshot():
            nonlocal now
            now = next(stamps)
            return Mock()

        def show_image(frame):
            preview[now] = [call.args for call in frame.draw_cross.call_args_list]
            if now == timestamps[-1]:
                raise KeyboardInterrupt

        def write(frame):
            writes.append((now, frame))
            return len(frame)

        def detect(_):
            cards = [self.distractor]
            if now <= 125:
                cards.append(self.target)
            elif now in (175, 200):
                cards.append(self.moved)
            elif 3500 <= now <= 3600:
                cards.append(self.distant)
            return cards

        uart = Mock()
        uart.read.return_value = b"SCAN\r\nID,5\r\nSTOP\r\n"
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
            patch.object(vision, "INITIAL_TARGET_ID", 3),
            patch.object(vision, "detect_cards", side_effect=detect),
            redirect_stdout(io.StringIO()) as console,
        ):
            vision.main()

        self.assertEqual(list(preview), list(timestamps))
        self.assertEqual(preview[75], [(320, 240), (60, 83)])
        self.assertEqual(preview[150], [(320, 240)])
        self.assertEqual(preview[175], [(320, 240), (69, 87)])
        self.assertEqual(preview[3550], [(320, 240)])
        self.assertEqual(preview[3600], [(320, 240), (427, 300)])
        missing = vision.NO_TARGET_FRAME
        self.assertEqual(writes, [
            (25, missing),
            (75, b"\xAA\x55640,480,60,83,80,100\r\n"),
            (125, b"\xAA\x55640,480,60,83,80,100\r\n"),
            (175, b"\xAA\x55640,480,69,87,80,100\r\n"),
            (3500, missing), (3550, missing),
            (3600, b"\xAA\x55640,480,427,300,80,100\r\n"),
            (10_000, missing), (10_000, missing),
        ])
        self.assertIn("TRACK,3,75", console.getvalue())
        self.assertIn("LOST,3,3500", console.getvalue())
        self.assertIn("TRACK,3,3600", console.getvalue())
        self.assertIn("STATS,10000,15,4", console.getvalue())
        self.assertNotIn("TIMEOUT", console.getvalue())
        uart.read.assert_not_called()
        display.init.assert_called_once_with(display.VIRT, width=640, height=480, fps=30, to_ide=True)
        uart.deinit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
