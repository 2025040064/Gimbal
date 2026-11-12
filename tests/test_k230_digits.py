import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'k230视觉云台.py'
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('vision_digits', SCRIPT)
    vision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vision)
else:
    vision = None

class Blob:
    def __init__(self, rect, pixels=None):
        self._rect = rect
        self._pixels = pixels if pixels is not None else rect[2] * rect[3]
    def rect(self):
        return self._rect
    def pixels(self):
        return self._pixels

class Gray:
    def __init__(self, cards, glyphs):
        self.cards, self.glyphs = cards, glyphs
    def find_blobs(self, thresholds, roi=None, **kwargs):
        if roi is None:
            return self.cards
        return self.glyphs.get(roi, [])

def card_roi(rect):
    x, y, w, h = rect
    dx, dy = max(1, w // 12), max(1, h // 12)
    return (x + dx, y + dy, w - 2 * dx, h - 2 * dy)

class DigitTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(vision, '数字识别程序尚未创建')
        self.exitpoint = patch.object(os, 'exitpoint', create=True)
        self.exitpoint.start()
        self.addCleanup(self.exitpoint.stop)
    def test_multi_cards_and_ten(self):
        from unittest.mock import patch
        a, b = (30, 30, 120, 140), (220, 40, 180, 150)
        one, zero, two = Blob((250, 70, 25, 80), 600), Blob((290, 70, 50, 80), 1200), Blob((60, 60, 50, 80), 1000)
        gray = Gray([Blob(a), Blob(b)], {card_roi(a): [two], card_roi(b): [one, zero]})
        digits = {two.rect(): 2, one.rect(): 1, zero.rect(): 0}
        with patch.object(vision, 'recognize_digit', side_effect=lambda _, rect: digits[rect]):
            self.assertCountEqual(vision.detect_cards(gray), [(2, a), (10, b)])
    def test_two_unrelated_digits_are_not_ten(self):
        from unittest.mock import patch
        a = (30, 30, 250, 140)
        left, right = Blob((60, 60, 30, 80), 500), Blob((140, 60, 40, 80), 800)
        gray = Gray([Blob(a)], {card_roi(a): [left, right]})
        with patch.object(vision, 'recognize_digit', side_effect=lambda _, rect: {left.rect(): 2, right.rect(): 3}[rect]):
            self.assertEqual(vision.detect_cards(gray), [])
    def test_uart_frame_compatibility(self):
        self.assertEqual(vision.coordinate_frame((200, 100, 100, 150), {1}, vision.VISION_TRACK, 1, 20),
                         b'\xaa\x55640,480,250,175,100,150,2,2,1,20\r\n')
        self.assertEqual(vision.coordinate_frame(None, (), vision.VISION_IDLE, None, 0),
                         b'\xaa\x55640,480,-1,-1,-1,-1,0,0,-1,0\r\n')
    def test_digit_templates_match_exact_samples(self):
        for digit, templates in enumerate(vision.DIGIT_TEMPLATES):
            template = templates[0]
            rows = template[1:]
            width, height = template[0], 100
            class Pattern:
                def get_pixel(self, x, y):
                    col = min(11, x * 12 // width)
                    row = min(17, y * 18 // height)
                    return 0 if rows[row] & (1 << (11 - col)) else 255
            with self.subTest(digit=digit):
                self.assertEqual(vision.recognize_digit(Pattern(), (0, 0, width, height)), digit)

if __name__ == '__main__':
    unittest.main()
