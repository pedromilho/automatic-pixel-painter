"""Regressão da barra de pintura com arte escura no mapa."""

from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixel_detector import auto_roi, locate_picker_in_screen, palette_top


for filename, expected_top, expected_picker in (
    ("preview_new.png", 974, (1214, 1016)),
    ("preview_old.png", 839, (276, 874)),
):
    image = cv2.imread(str(Path(__file__).with_name(filename)))
    assert image is not None
    assert palette_top(image) == expected_top
    assert auto_roi(image)[3] == expected_top - 6
    assert locate_picker_in_screen(image)[:2] == expected_picker

    dark_art = image.copy()
    height, width = dark_art.shape[:2]
    dark_art[round(height * .62):round(height * .72),
             round(width * .45):round(width * .55)] = (35, 35, 35)
    assert palette_top(dark_art) == expected_top

bug_preview = cv2.imread(str(Path(__file__).with_name("bug_preview_crop.png")))
assert bug_preview is not None
# A antiga rotina encerrava o recorte em y=266, no meio do desenho.
assert palette_top(bug_preview) == 388
assert auto_roi(bug_preview)[3] == 382

second_bug = cv2.imread(str(Path(__file__).with_name("bug2_preview_crop.png")))
assert second_bug is not None
# A seleção desta captura terminava em y=341; a barra real começa em y=388.
assert palette_top(second_bug) == 388
assert auto_roi(second_bug)[3] == 382
print("OK: barra e recorte corretos nos dois layouts e na captura relatada")
