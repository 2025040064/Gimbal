"""Regression checks for the WonderMK startup and STM32 contest link."""
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
spec = importlib.util.spec_from_file_location("closed_loop_vision", SCRIPT)
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)


class ClosedLoopTests(unittest.TestCase):
    def test_defaults_match_working_preview_and_external_uart(self):
        self.assertEqual((vision.SENSOR_WIDTH, vision.SENSOR_HEIGHT), (640, 480))
        self.assertEqual((vision.DETECT_WIDTH, vision.DETECT_HEIGHT), (640, 480))
        self.assertEqual(vision.COMMAND_INPUT, "uart3")
        self.assertTrue(vision.ENABLE_IDE_PREVIEW)

    def test_uart_maps_external_port_and_reads_only_available_bytes(self):
        uart = Mock()
        machine = SimpleNamespace(FPIOA=Mock(), UART=Mock(return_value=uart))
        with patch.dict(sys.modules, {"machine": machine}), redirect_stdout(io.StringIO()):
            self.assertIs(vision.open_uart(), uart)
        machine.FPIOA.return_value.set_function.assert_any_call(50, machine.FPIOA.UART3_TXD, oe=1)
        machine.FPIOA.return_value.set_function.assert_any_call(51, machine.FPIOA.UART3_RXD, ie=1)
        self.assertEqual(machine.UART.call_args.args, (machine.UART.UART3,))
        read = vision.open_command_input(uart)
        uart.any.return_value = 0
        self.assertFalse(read(32))
        uart.read.assert_not_called()
        uart.any.return_value = 5
        uart.read.return_value = b"ID,1\n"
        self.assertEqual(read(32), b"ID,1\n")
        uart.read.assert_called_once_with(5)

    def test_stop_id_observation_loss_and_scan_match_stm32_protocol(self):
        session = vision.VisionSession(lambda a, b: a - b)
        self.assertTrue(session.command(b"STOP", 0))
        self.assertEqual(session.packet({}), b"\xaa\x55640,480,-1,-1,-1,-1,0,0,-1,0\r\n")
        self.assertTrue(session.command(b"ID,1", 1))
        self.assertEqual(session.packet({}), b"\xaa\x55640,480,-1,-1,-1,-1,0,2,1,0\r\n")
        for now in (150, 300, 450):
            confirmed, _, _ = session.observe([(1, (300, 220, 40, 40)), (7, (10, 10, 20, 30))], now)
        self.assertEqual(session.packet(confirmed), b"\xaa\x55640,480,320,240,40,40,130,2,1,3\r\n")
        # A heartbeat is not a new camera observation.
        first = session.packet(confirmed)
        self.assertEqual(session.packet(confirmed), first)
        session.command(b"ID,1", 500)
        self.assertEqual(session.packet(confirmed), first)
        session.sequence = 65535
        confirmed, _, _ = session.observe([], 600)
        self.assertEqual(session.packet(confirmed), b"\xaa\x55640,480,-1,-1,-1,-1,0,2,1,0\r\n")
        session.command(b"SCAN", 650)
        confirmed, _, _ = session.observe([], 61000)
        self.assertEqual(session.mode, vision.VISION_SCAN)  # STM32 owns scan duration.
        session.command(b"STOP", 61001)
        self.assertEqual(session.mode, vision.VISION_IDLE)

    def test_recognition_checks_ide_stop_between_digit_templates(self):
        gray = Mock()
        gray.get_pixel.return_value = 255
        with patch.object(os, "exitpoint", side_effect=Exception("IDE interrupt"), create=True):
            with self.assertRaisesRegex(Exception, "IDE interrupt"):
                vision.recognize_digit(gray, (0, 0, 30, 60))

    def test_first_preview_precedes_recognition_and_stop_interrupt_is_not_swallowed(self):
        events, writes = [], []
        clock = [0]
        sensor, uart, media, gray = Mock(), Mock(), Mock(), Mock()
        uart.any.return_value = 0
        uart.write.side_effect = lambda frame: writes.append(frame) or len(frame)

        def snapshot(chn=0):
            clock[0] += 50
            events.append("snapshot")
            frame = Mock()
            frame.compress_for_ide.side_effect = lambda: events.append("preview")
            return frame

        def detect(_):
            events.append("recognition")
            raise Exception("IDE interrupt")

        sensor.snapshot.side_effect = snapshot
        modules = {
            "media": SimpleNamespace(),
            "media.sensor": SimpleNamespace(Sensor=Mock(return_value=sensor)),
            "media.media": SimpleNamespace(MediaManager=media),
            "media.display": None,
            "image": SimpleNamespace(Image=Mock(return_value=gray), GRAYSCALE=0),
        }
        with (patch.dict(sys.modules, modules),
              patch.multiple(os, exitpoint=Mock(), EXITPOINT_ENABLE_SLEEP=1, create=True),
              patch.multiple(time, ticks_ms=lambda: clock[0], ticks_diff=lambda a, b: a-b,
                             sleep_ms=Mock(), create=True),
              patch.object(vision, "open_uart", return_value=uart),
              patch.object(vision, "detect_cards", side_effect=detect),
              redirect_stdout(io.StringIO()) as output):
            with self.assertRaisesRegex(Exception, "IDE interrupt"):
                vision.main()
        self.assertLess(events.index("preview"), events.index("recognition"))
        sensor.set_framesize.assert_called_once_with(width=640, height=480, chn=0)
        self.assertIn("[OK] FIRST_PREVIEW", output.getvalue())
        self.assertNotIn("recognition disabled", output.getvalue())
        self.assertTrue(writes)
        self.assertTrue(all(len(frame[2:-2].split(b",")) == 10 for frame in writes))
        uart.deinit.assert_called_once()
        sensor.stop.assert_called_once()
        media.deinit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
