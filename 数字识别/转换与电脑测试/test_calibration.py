import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import test_det_kmodel as detector
import to_kmodel


class CalibrationTest(unittest.TestCase):
    def test_calibration_matches_inference_and_spans_dataset(self):
        with tempfile.TemporaryDirectory(dir='.') as directory:
            for i in range(10):
                rgb = np.full((40, 80, 3), (20 * i, 30, 200), dtype=np.uint8)
                Image.fromarray(rgb).save(Path(directory) / f'{i:02}.png')
            data = to_kmodel.generate_data([1, 3, 320, 320], 5, directory)
            self.assertEqual(data.shape, (5, 1, 1, 3, 320, 320))
            self.assertEqual(data.dtype, np.uint8)
            self.assertEqual(int(data[-1, 0, 0, 0, 160, 160]), 180)
            image = cv2.imread(str(Path(directory) / '00.png'))
            expected, _, _, _ = detector.preprocess(image, 320, 320)
            np.testing.assert_array_equal(data[0, 0], expected)


if __name__ == '__main__':
    unittest.main()
