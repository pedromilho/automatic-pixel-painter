from collections import Counter
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot_blue_marble import auto_roi, detect_squares

image = cv2.imread(r"C:\Users\pedro\Desktop\Screenshot_2.png")
roi = auto_roi(image)
squares, pitch = detect_squares(image, roi)
crop = image[roi[1]:roi[3], roi[0]:roi[2]]
background = cv2.medianBlur(crop, 15)
contrast = np.max(cv2.absdiff(crop, background), axis=2)

def clusters(values, gap=3):
    groups = []
    for value in sorted(set(values)):
        if not groups or value - groups[-1][-1] > gap:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [int(round(np.median(group))) for group in groups]

xs, ys = clusters([s.x for s in squares]), clusters([s.y for s in squares])
width = Counter(s.width for s in squares).most_common(1)[0][0]
height = Counter(s.height for s in squares).most_common(1)[0][0]
print("roi", roi, "detected", len(squares), "pitch", pitch,
      "cols", len(xs), "rows", len(ys), "size", width, height)

hits = []
misses = []
for y in ys:
    for x in xs:
        seen = any(abs(s.x - x) <= 3 and abs(s.y - y) <= 3 for s in squares)
        rx, ry = x - roi[0], y - roi[1]
        half = max(2, width // 2 - 1)
        patch = contrast[ry-half:ry+half+1, rx-half:rx+half+1]
        if patch.shape != (2*half+1, 2*half+1):
            continue
        raw = crop[ry-half:ry+half+1, rx-half:rx+half+1]
        flatness = float(np.max(raw.reshape(-1,3).std(axis=0)))
        center = np.median(raw.reshape(-1,3), axis=0)
        offset = half + 2
        side_colors = [np.median(crop[ry-1:ry+2, rx+offset], axis=0),
                       np.median(crop[ry-1:ry+2, rx-offset], axis=0),
                       np.median(crop[ry+offset, rx-1:rx+2], axis=0),
                       np.median(crop[ry-offset, rx-1:rx+2], axis=0)]
        sides = sum(np.max(np.abs(center-side)) >= 10 for side in side_colors)
        score = (float((patch >= 12).mean()), float(np.median(patch)), float(patch.mean()), flatness, sides)
        (hits if seen else misses).append((x, y, score))

print("hits",len(hits),"misses",len(misses))
for label, group in (("hits",hits),("miss",misses)):
    scores = np.array([item[2] for item in group])
    print(label, "coverage", np.percentile(scores[:,0],[0,10,25,50,75,90,100]),
          "median",np.percentile(scores[:,1],[0,10,25,50,75,90,100]),
          "flat",np.percentile(scores[:,3],[0,10,25,50,75,90,100]),
          "sides",Counter(scores[:,4]))
print("top misses",sorted(misses,key=lambda item:item[2][0],reverse=True)[:25])
print("top-right misses", [(x,y,score) for x,y,score in misses if x>1750 and y<180])
print("low misses", sorted(misses,key=lambda item:item[2][0])[:20])
print("recovered side counts",Counter(v[2][4] for v in misses if v[2][0]>=.85 and v[2][1]>=12 and v[2][3]<=4))

preview = image.copy()
for x, y, score in misses:
    if score[0] >= .45:
        cv2.circle(preview, (x, y), 10, (0,0,255), 1)
cv2.imwrite("work/probe_roads_preview.png",preview)
