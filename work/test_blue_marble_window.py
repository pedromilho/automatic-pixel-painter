"""Confere exclusão da janela flutuante sem perder pixels do mapa."""

from pathlib import Path
import sys
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot_blue_marble as bot


image = cv2.imread(str(Path(__file__).with_name("preview_new.png")))
assert image is not None
window = bot.blue_marble_window(image)
assert window == (1777, 81, 1840, 160)
roi = bot.auto_roi(image)
assert roi == (81, 81, 1839, 968)  # O recorte permanece inteiro.

with patch.object(bot, "blue_marble_window", return_value=None):
    baseline, _ = bot.detect_squares(image, roi)
filtered, _ = bot.detect_squares(image, roi)
assert len(filtered) == len(baseline)  # Nenhum pixel válido do mapa foi removido.

without_widget = image.copy()
without_widget[82:159, 1778:1839] = (110, 81, 69)
assert bot.blue_marble_window(without_widget) is None

grid = np.full((240, 240, 3), (60, 70, 80), dtype=np.uint8)
for y in range(20, 220, 25):
    for x in range(20, 220, 25):
        grid[y-4:y+4, x-4:x+4] = (200, 130, 90)
with patch.object(bot, "blue_marble_window", return_value=None):
    all_squares, _ = bot.detect_squares(grid, (0, 0, 240, 240))
with patch.object(bot, "blue_marble_window", return_value=(13, 13, 28, 28)):
    safe_squares, _ = bot.detect_squares(grid, (0, 0, 240, 240))
assert len(all_squares) == 64 and len(safe_squares) == 63
assert (20, 20) not in {(square.x, square.y) for square in safe_squares}

preview = bot.annotated(image, roi, filtered)
assert tuple(preview[window[1], window[0] + 10]) == (0, 0, 255)
print("OK: janela identificada, marcada e excluída; mapa preservado")
