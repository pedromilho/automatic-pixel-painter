"""Agrupamento, sequência de cliques e retomada sem mover o mouse real."""

from contextlib import ExitStack
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import call, patch

import numpy as np

import pixel_detector as detector
import pixel_server as server


class GroupedColorsTests(unittest.TestCase):
    def setUp(self):
        self.squares = [detector.Square(x, 20, 8, 8) for x in (20, 40, 60, 80)]
        self.a, self.b, self.c, self.d = self.squares
        self.colors = {self.a: (10, 20, 30), self.b: (11, 20, 30),
                       self.c: (10, 20, 30), self.d: (10, 20, 30)}

    def test_nearby_colors_stay_separate_and_border_is_ignored(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        for square, color in self.colors.items():
            image[square.y-2:square.y+3, square.x-2:square.x+3] = color
            image[square.y-1, square.x-1] = (255, 255, 255)
        self.assertEqual(detector.marker_colors(image, self.squares), self.colors)
        self.assertEqual(detector.order_by_color(self.squares, self.colors, "fewest"),
                         [self.b, self.a, self.c, self.d])
        self.assertEqual(detector.order_by_color(self.squares, self.colors, "most"),
                         [self.a, self.c, self.d, self.b])

    def paint_mocks(self, stack):
        target = SimpleNamespace(_hWnd=123)
        stack.enter_context(patch.object(detector, "active_canvas_window", return_value=target))
        stack.enter_context(patch.object(detector, "capture_bgr", return_value=np.zeros((100, 100, 3), dtype=np.uint8)))
        stack.enter_context(patch.object(detector, "palette_open", return_value=True))
        stack.enter_context(patch.object(detector, "overlay_panel", return_value=None))
        stack.enter_context(patch.object(detector, "picker_region", return_value=(0, 0, 10, 10)))
        stack.enter_context(patch.object(detector, "locate_picker_in_screen", return_value=(5, 6, 1)))
        stack.enter_context(patch.object(detector, "locate_picker", return_value=(5, 6, 1)))
        stack.enter_context(patch.object(detector.pygetwindow, "getActiveWindow", return_value=target))
        stack.enter_context(patch.object(detector.pyautogui, "screenshot", return_value=np.zeros((10, 10, 3), dtype=np.uint8)))
        stack.enter_context(patch.object(detector.pyautogui, "moveTo"))
        stack.enter_context(patch.object(detector.time, "sleep"))
        return stack.enter_context(patch.object(detector.pyautogui, "click"))

    def test_picker_only_at_group_boundaries(self):
        with ExitStack() as stack:
            click = self.paint_mocks(stack)
            done = detector.paint([self.a, self.c, self.d, self.b], 4,
                                  detector.TIMINGS["fast"], "button", None,
                                  mode="grouped", colors=self.colors)
        self.assertEqual(done, 4)
        self.assertEqual(click.call_args_list,
                         [call(5, 6), call(), call(), call(), call(),
                          call(5, 6), call(), call()])

    def test_stop_between_groups_and_resume_samples_again(self):
        stop = threading.Event()
        with ExitStack() as stack:
            click = self.paint_mocks(stack)
            done = detector.paint([self.b, self.a, self.c], 3,
                                  detector.TIMINGS["fast"], "button", None,
                                  mode="grouped", colors=self.colors, stop_event=stop,
                                  on_progress=lambda *_: stop.set())
            self.assertEqual(done, 1)
            self.assertEqual(click.call_args_list, [call(5, 6), call(), call()])
            click.reset_mock()
            stop.clear()
            done = detector.paint([self.a, self.c], 2, detector.TIMINGS["fast"],
                                  "button", None, mode="grouped", colors=self.colors)
            self.assertEqual(done, 2)
            self.assertEqual(click.call_args_list, [call(5, 6), call(), call(), call()])

    def test_batches_and_order_changes_never_repeat_completed_pixels(self):
        session = server.Session()
        session.image = np.zeros((100, 100, 3), dtype=np.uint8)
        session.squares = self.squares.copy()
        session.colors = self.colors
        session.picker = (5, 6, 1)
        painted = []

        def paint(squares, *args, **kwargs):
            painted.extend(squares)
            for done in range(1, len(squares) + 1):
                kwargs["on_progress"](done, len(squares))
            return len(squares)

        def thread(*, target, **kwargs):
            return SimpleNamespace(start=target)

        with patch.object(server, "paint", side_effect=paint), \
             patch.object(server.threading, "Thread", side_effect=thread):
            session.start("grouped", 6, 1, 0, "most")
            session.start("grouped", 6, 1, 0, "most")
            session.start("grouped", 6, 2, 0, "fewest")
        self.assertEqual(painted, [self.a, self.c, self.d, self.b])
        self.assertEqual(session.cursor, 4)
        self.assertEqual(len(set(painted)), 4)

    def test_missing_picker_or_invalid_order_rejected(self):
        session = server.Session()
        session.image = np.zeros((100, 100, 3), dtype=np.uint8)
        session.squares = self.squares
        with self.assertRaises(ValueError):
            session.start("grouped", 6, 1, 0)
        with self.assertRaises(ValueError):
            session.start("grouped", 6, 1, 0, "invalid")

    def test_excluded_colors_remain_pending_and_can_be_reincluded(self):
        for mode in ("grouped", "per_pixel", "specific"):
            with self.subTest(mode=mode):
                session = server.Session()
                session.image = np.zeros((100, 100, 3), dtype=np.uint8)
                session.squares = self.squares.copy()
                session.colors = self.colors
                session.picker = (5, 6, 1)
                painted = []

                def paint(squares, *args, **kwargs):
                    painted.extend(squares)
                    kwargs["on_progress"](len(squares), len(squares))
                    return len(squares)

                with patch.object(server, "paint", side_effect=paint), \
                     patch.object(server.threading, "Thread",
                                  side_effect=lambda **kw: SimpleNamespace(start=kw["target"])):
                    session.start(mode, 6, 4, 0, "most", ["#1e140a"])
                    self.assertEqual(painted, [self.b])
                    self.assertEqual(session.status()["remaining"], 3)
                    summary = {color["hex"]: color for color in session.plan()["colors"]}
                    self.assertEqual(summary["#1e140a"],
                                     {"hex": "#1e140a", "count": 3, "remaining": 3})
                    self.assertEqual(summary["#1e140b"]["remaining"], 0)
                    with self.assertRaises(ValueError):
                        session.start(mode, 6, 4, 0, "most", ["#1e140a"])
                    session.start(mode, 6, 4, 0, "most", [])
                self.assertEqual(painted, [self.b, self.a, self.c, self.d])
                self.assertEqual(session.cursor, 4)

    def test_invalid_exclusions_do_not_start_or_change_plan(self):
        session = server.Session()
        session.image = np.zeros((100, 100, 3), dtype=np.uint8)
        session.squares = self.squares.copy()
        session.colors = self.colors
        session.picker = (5, 6, 1)
        for excluded in ("#1e140a", [123], ["#ffffff"], ["#1e140a", "#1e140b"]):
            with self.assertRaises(ValueError):
                session.start("grouped", 6, 4, 0, "most", excluded)
            self.assertFalse(session.running)
            self.assertEqual(session.cursor, 0)
            self.assertEqual(session.squares, self.squares)


if __name__ == "__main__":
    unittest.main()
