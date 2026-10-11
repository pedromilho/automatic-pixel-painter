import cv2
import numpy as np

new = cv2.imread(r"C:\Users\pedro\Desktop\Screenshot_2.png")
old = cv2.imread(r"C:\Users\pedro\Documents\Codex\2026-09-27\quer\outputs\apos_conta_gotas.png")
images = [("new", new[974:1063, 950:1370], (950, 974)),
          ("old", old[830:930, 80:810], (80, 830))]
templates = [("new", cv2.imread("color_picker_modelo_novo.png", 0), 110),
             ("old", cv2.imread("color_picker_modelo.png", 0), 160)]
for name, image, origin in images:
    for label, template, threshold in templates:
        mask = np.uint8(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) > threshold)
        pattern = np.uint8(template > threshold)
        result = cv2.matchTemplate(mask, pattern, cv2.TM_CCOEFF_NORMED)
        _, score, _, point = cv2.minMaxLoc(result)
        print(name, label, round(score, 3),
              (origin[0] + point[0] + pattern.shape[1] // 2,
               origin[1] + point[1] + pattern.shape[0] // 2))
