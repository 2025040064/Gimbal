import unittest

from k230_yolo_camera import normalize_detections


class DetectionResultTest(unittest.TestCase):
    def test_firmware_result_is_three_lists(self):
        result = ([[10.2, 20.4, 30.6, 40.8]], [8], [0.97])
        self.assertEqual(normalize_detections(result), [(8, 0.97, (10, 20, 31, 41))])

    def test_empty_result(self):
        self.assertEqual(normalize_detections(None), [])
        self.assertEqual(normalize_detections(([], [], [])), [])


if __name__ == "__main__":
    unittest.main()
