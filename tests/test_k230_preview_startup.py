import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / 'K230_数字识别_启动排障V2.py'
spec = importlib.util.spec_from_file_location('k230_preview', SCRIPT)
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)


class PreviewStartupTests(TestCase):
    def test_startup_without_preview_does_not_require_display(self):
        import os
        import sys
        import time
        from types import SimpleNamespace

        sensor = Mock()
        sensor.snapshot.side_effect = [Mock(), KeyboardInterrupt()]
        modules = {
            'media': SimpleNamespace(),
            'media.sensor': SimpleNamespace(Sensor=Mock(return_value=sensor)),
            'media.display': None,
            'media.media': SimpleNamespace(MediaManager=Mock()),
        }
        output = io.StringIO()
        with (patch.dict(sys.modules, modules),
              patch.multiple(time, ticks_ms=lambda: 0, sleep_ms=Mock(), create=True),
              patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
              patch.object(vision, 'ENABLE_IDE_PREVIEW', False),
              patch.object(vision, 'ENABLE_UART3', False),
              patch.object(vision, 'ENABLE_RECOGNITION', False),
              redirect_stdout(output)):
            vision.main()
        sensor.run.assert_called_once()
        self.assertIn('[OK] FIRST_SNAPSHOT', output.getvalue())

    def test_competition_frame_identifies_target_and_observation(self):
        self.assertEqual(vision.contest_frame((300, 220, 40, 40), {1, 7}, 2, 1, 19),
                         b'\xaa\x55640,480,320,240,40,40,130,2,1,19\r\n')

    def test_recorder_saves_frames_and_relative_timestamps(self):
        jpeg = b'\xff\xd8sample\xff\xd9'
        frame = Mock()
        frame.compressed.return_value = jpeg
        with TemporaryDirectory(dir=Path(__file__).resolve().parent) as root:
            with redirect_stdout(io.StringIO()):
                recorder = vision.ContestRecorder(root, 50, lambda a, b: a - b)
            try:
                recorder.capture(frame, 60)
                recorder.capture(frame, 80)
                recorder.capture(frame, 180)
            finally:
                recorder.close()
            folder = Path(root) / 'gimbal_0001'
            self.assertEqual((folder / 'camera.mjpeg').read_bytes(), jpeg * 2)
            self.assertEqual((folder / 'events.csv').read_text(), '10,FRAME,1\n130,FRAME,2\n')

    def test_visible_ids_are_sent_even_without_a_tracking_target(self):
        self.assertEqual(vision.coordinate_frame(None, {0, 3, 10}),
                         b'\xaa\x55640,480,-1,-1,-1,-1,1033\r\n')

    def test_dim_slightly_slanted_one_on_large_card(self):
        import os

        card = Mock()
        card.rect.return_value = (0, 0, 370, 390)
        card.pixels.return_value = 120000
        glyph = Mock()
        glyph.rect.return_value = (154, 117, 38, 134)
        glyph.pixels.return_value = 1920
        background = Mock()
        background.rect.return_value = (30, 304, 210, 54)
        background.pixels.return_value = 6800

        class Gray:
            def get_pixel(self, x, y):
                y -= 117
                if not 0 <= y < 134:
                    return 156
                stem_right = 191 - y // 14
                stroke_left = stem_right - 12
                if y < 32:
                    stroke_left = min(stroke_left, 154 + abs(y - 19) * 2)
                return 74 if stroke_left <= x <= stem_right else 156

            def find_blobs(self, thresholds, roi=None, **kwargs):
                if roi is None:
                    return [card]
                return [background, glyph] if thresholds[0][1] >= 74 else [background]

        with patch.object(os, 'exitpoint', create=True):
            result = vision.detect_cards(Gray())
        self.assertEqual([digit for digit, _ in result], [1])

    def test_detection_box_surrounds_digits_instead_of_white_card(self):
        import os

        gray = Mock()
        card = Mock()
        card.rect.return_value = (100, 60, 250, 300)
        card.pixels.return_value = 68000
        gray.find_blobs.return_value = [card]
        one = (165, 135, 28, 100)
        zero = (207, 140, 58, 96)
        for digit, glyphs, expected in (
            (1, [one], (160, 130, 38, 110)),
            (10, [one, zero], (160, 130, 110, 111)),
        ):
            with (self.subTest(digit=digit),
                  patch.object(os, 'exitpoint', create=True),
                  patch.object(vision, 'glyphs_in_card', return_value=glyphs),
                  patch.object(vision, 'recognize_digit', side_effect=lambda _, rect, threshold: int(rect == one))):
                self.assertEqual(vision.detect_cards(gray), [(digit, expected)])

    def test_default_uart_matches_wondermk_external_port(self):
        import sys
        from types import SimpleNamespace

        machine = SimpleNamespace(FPIOA=Mock(), UART=Mock())
        with patch.dict(sys.modules, {'machine': machine}), redirect_stdout(io.StringIO()):
            self.assertTrue(vision.ENABLE_UART3)
            self.assertIs(vision.open_uart3(), machine.UART.return_value)
        machine.FPIOA.return_value.set_function.assert_any_call(50, machine.FPIOA.UART3_TXD, oe=1)
        machine.UART.assert_called_once_with(
            machine.UART.UART3, baudrate=115200, bits=machine.UART.EIGHTBITS,
            parity=machine.UART.PARITY_NONE, stop=machine.UART.STOPBITS_ONE,
        )
        self.assertEqual(vision.COMMAND_INPUT, 'none')

    def test_usb_command_input_does_not_depend_on_uart(self):
        import os
        import sys
        import time
        from types import SimpleNamespace

        clock = [0]
        sensor = Mock()
        first_attempt = True
        def snapshot():
            nonlocal first_attempt
            if first_attempt:
                first_attempt = False
                raise RuntimeError('sensor(0) snapshot chn(0) failed(3)')
            clock[0] += 100
            if clock[0] > 300:
                raise KeyboardInterrupt
            return Mock()
        sensor.snapshot.side_effect = snapshot
        display = Mock()
        modules = {
            'media': SimpleNamespace(),
            'media.sensor': SimpleNamespace(Sensor=Mock(return_value=sensor)),
            'media.display': SimpleNamespace(Display=display),
            'media.media': SimpleNamespace(MediaManager=Mock()),
        }
        with (patch.dict(sys.modules, modules),
              patch.multiple(time, ticks_ms=lambda: clock[0],
                             ticks_diff=lambda a, b: a - b, sleep_ms=Mock(), create=True),
              patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
              patch.object(vision, 'ENABLE_UART3', False),
              patch.object(vision, 'ENABLE_IDE_PREVIEW', True),
              patch.object(vision, 'ENABLE_RECOGNITION', False),
              patch.object(vision, 'COMMAND_INPUT', 'usb'),
              patch.object(vision, 'open_command_input', return_value=Mock(return_value=b'')) as open_input,
              redirect_stdout(io.StringIO())):
            vision.main()
        open_input.assert_called_once_with(None)
        self.assertGreaterEqual(display.show_image.call_count, 2)

    def test_detection_report_includes_center_size_and_tracking(self):
        output = io.StringIO()
        with redirect_stdout(output):
            vision.report_detections({3: (10, 20, 30, 40)}, 3)
        self.assertIn('id=3', output.getvalue())
        self.assertIn('center=(25,40)', output.getvalue())
        self.assertIn('size=(30,40)', output.getvalue())
        self.assertIn('tracking=True', output.getvalue())

    def test_v2_recognizes_all_digit_templates(self):
        import os

        with patch.object(os, 'exitpoint', create=True):
            for digit, templates in enumerate(vision.DIGIT_TEMPLATES):
                template = templates[0]
                width, rows = template[0], template[1:]

                class Pattern:
                    def get_pixel(self, x, y):
                        col = min(11, x * 12 // width)
                        row = min(17, y * 18 // 100)
                        return 0 if rows[row] & (1 << (11 - col)) else 255

                with self.subTest(digit=digit):
                    self.assertEqual(vision.recognize_digit(Pattern(), (0, 0, width, 100)), digit)

    def test_locked_digit_stays_selected_after_fast_image_motion(self):
        session = vision.VisionSession(lambda now, before: now - before)
        session.command(b'ID,1', 0)
        for now in (0, 250, 500):
            session.observe([(1, (50, 100, 15, 55))], now)
        moved = (95, 100, 15, 55)
        confirmed, _, _ = session.observe([(1, moved), (7, (50, 100, 15, 55))], 750)
        self.assertEqual(confirmed.get(session.target_id), moved)

    def test_v2_command_scan_tracking_loss_and_reacquisition(self):
        session = vision.VisionSession(lambda now, before: now - before)
        reader = vision.CommandReader()
        self.assertEqual(list(reader.feed(b'SCAN\rID,10\nSTOP\r\n')),
                         [b'SCAN', b'ID,10', b'STOP'])
        self.assertTrue(session.command(b'SCAN', 0))
        for timestamp in (0, 250, 500):
            confirmed, found, _ = session.observe([(10, (10, 20, 30, 40))], timestamp)
        self.assertEqual(found, (10,))
        self.assertTrue(session.command(b'ID,10', 600))
        self.assertEqual(session.take_scan_result(), (10,))
        for timestamp in (700, 950, 1200):
            confirmed, _, _ = session.observe([(10, (10, 20, 30, 40))], timestamp)
        self.assertEqual(vision.coordinate_frame(confirmed[10]), b'\xaa\x55640,480,25,40,30,40\r\n')
        confirmed, _, _ = session.observe([], 1450)
        self.assertNotIn(10, confirmed)
        self.assertEqual(session.target_id, 10)
        for timestamp in (1700, 1950, 2200):
            confirmed, _, _ = session.observe([(10, (100, 120, 30, 40))], timestamp)
        self.assertEqual(confirmed[10], (100, 120, 30, 40))
        self.assertTrue(session.command(b'STOP', 2300))
        self.assertIsNone(session.target_id)
