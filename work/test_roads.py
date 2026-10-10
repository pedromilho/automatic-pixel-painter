"""Regressão visual offline: ruas com marcadores e células vazias."""

from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot_blue_marble import auto_roi, detect_squares, recover_grid_markers


full = cv2.imread(r"C:\Users\pedro\Desktop\Screenshot_2.png")
assert full is not None
roi = auto_roi(full)
squares, pitch = detect_squares(full, roi)
points = {(square.x, square.y) for square in squares}
assert pitch == (27, 27)
assert len(squares) == 2159
assert (106, 203) in points and (983, 336) in points  # Marcadores sobre ruas.
assert (797, 681) not in points and (1807, 123) not in points  # Vazio e botão Blue Marble.

crop = cv2.imread(r"C:\Users\pedro\AppData\Local\Temp\codex-clipboard-e24e9fac-1cf8-4e0e-a84a-3a0b9072ea13.png")
assert crop is not None
detected_in_annotated_crop, _ = detect_squares(crop, (0, 0, crop.shape[1], crop.shape[0]))
background = cv2.medianBlur(crop, 25)
contrast = np.max(cv2.absdiff(crop, background), axis=2)
recovered = recover_grid_markers(crop, contrast,
                                 (0, 0, crop.shape[1], crop.shape[0]),
                                 detected_in_annotated_crop, (11, 11))
recovered_points = {(square.x, square.y) for square in recovered}
assert {(66, 107), (102, 107), (138, 107), (138, 141), (102, 248)} <= recovered_points

print("OK: ruas recuperadas; áreas vazias e interface preservadas")
