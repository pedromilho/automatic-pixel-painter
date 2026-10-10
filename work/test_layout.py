"""Verifica os dois layouts de pintura sem clicar no Wplace."""

from pathlib import Path
import sys
from unittest.mock import patch

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot_blue_marble as bot
from bot_blue_marble import auto_roi, detect_squares, locate_picker_in_screen, palette_open, palette_top
from wplace_local import Session


new = cv2.imread(r"C:\Users\pedro\Desktop\Screenshot_2.png")
old = cv2.imread(r"C:\Users\pedro\Documents\Codex\2026-09-27\quer\outputs\apos_conta_gotas.png")
assert new is not None and old is not None

for name, image, expected_top, expected_picker in (
    ("new", new, 974, (1214, 1016)),
    ("old", old, 839, (276, 874)),
):
    assert palette_open(image)
    assert palette_top(image) == expected_top
    assert locate_picker_in_screen(image)[:2] == expected_picker
    roi = auto_roi(image)
    assert roi[3] == expected_top - 6
    squares, pitch = detect_squares(image, roi)
    if name == "new":
        assert len(squares) > 1000 and pitch == (27, 27)
    session = Session()
    plan = session._replan(image, roi)
    assert plan["picker"][:2] == expected_picker
    assert plan["count"] == len(squares)
    Path(f"work/preview_{name}.png").write_bytes(session.preview_png)
    print(name, "roi", roi, "picker", expected_picker, "squares", len(squares), "pitch", pitch)

try:
    Session()._replan(new, (80, 81, 1840, 980))
except ValueError:
    pass
else:
    raise AssertionError("A seleção não deve incluir a barra de pintura")

print("OK: prévias e recortes dos dois layouts")

events = []
def screenshot_region(*, region):
    left, top, width, height = region
    crop = new[top:top + height, left:left + width]
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

with patch.object(bot, "active_wplace_window", return_value=None), \
     patch.object(bot, "capture_bgr", return_value=new), \
     patch.object(bot.pygetwindow, "getActiveWindow", return_value=type("Window", (), {"title": "Wplace"})()), \
     patch.object(bot.pyautogui, "screenshot", side_effect=screenshot_region), \
     patch.object(bot.pyautogui, "moveTo", side_effect=lambda x, y, duration=0: events.append(("move", x, y))), \
     patch.object(bot.pyautogui, "click", side_effect=lambda *args: events.append(("click", args))), \
     patch.object(bot.time, "sleep", return_value=None):
    done = bot.paint([bot.Square(500, 400, 8, 8), bot.Square(527, 400, 8, 8)],
                     2, bot.TIMINGS["fast"], "button", None)

assert done == 2
assert events == [
    ("click", (1214, 1016)), ("move", 500, 400), ("click", ()), ("click", ()),
    ("click", (1214, 1016)), ("move", 527, 400), ("click", ()), ("click", ()),
]
print("OK: color picker do layout novo usado em dois pixels simulados")
