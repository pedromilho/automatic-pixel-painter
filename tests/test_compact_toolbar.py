"""Regressão da barra compacta; todos os comandos de mouse são simulados."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

import cv2
import numpy as np
from PIL import Image

import pixel_detector as detector
from pixel_server import Session


class CompactToolbarTests(unittest.TestCase):
    def setUp(self):
        toolbar = cv2.imread(str(Path(__file__).parent / "fixtures" / "compact_toolbar.png"))
        self.assertIsNotNone(toolbar)
        self.image = np.full((1080, 1920, 3), (100, 90, 80), dtype=np.uint8)
        self.image[1002:1063, 659:1297] = toolbar

    def test_capture_bounds_and_picker(self):
        self.assertEqual(detector.palette_top(self.image), 1002)
        roi = detector.auto_roi(self.image)
        self.assertEqual(roi, (81, 81, 1839, 996))
        plan = Session()._replan(self.image, roi)
        self.assertEqual(plan["picker"][:2], (870, 1030))
        with self.assertRaises(ValueError):
            Session()._replan(self.image, (81, 81, 1839, 1010))

    def test_missing_picker_does_not_choose_another_control(self):
        self.image[1014:1046, 854:886] = (45, 40, 35)
        with self.assertRaises(RuntimeError):
            detector.locate_picker_in_screen(self.image)

    def test_rechecks_picker_and_samples_before_each_pixel(self):
        def screenshot(*, region):
            x, y, width, height = region
            crop = self.image[y:y + height, x:x + width]
            return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

        target = SimpleNamespace(_hWnd=123)
        squares = [detector.Square(500, 400, 8, 8), detector.Square(523, 400, 8, 8)]
        with patch.object(detector, "active_canvas_window", return_value=target), \
             patch.object(detector, "capture_bgr", return_value=self.image), \
             patch.object(detector.pygetwindow, "getActiveWindow", return_value=target), \
             patch.object(detector.pyautogui, "screenshot", side_effect=screenshot) as capture, \
             patch.object(detector.pyautogui, "moveTo"), \
             patch.object(detector.pyautogui, "click") as click, \
             patch.object(detector.time, "sleep"):
            done = detector.paint(squares, 2, detector.TIMINGS["fast"], "button", None)

        self.assertEqual(done, 2)
        capture.assert_called_once()
        self.assertEqual(click.call_args_list, [call(870, 1030), call(), call()] * 2)


if __name__ == "__main__":
    unittest.main()
