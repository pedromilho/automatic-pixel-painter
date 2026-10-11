from collections import Counter
import cv2
import numpy as np

paths = [r"C:\Users\pedro\Desktop\Screenshot_2.png",
         r"C:\Users\pedro\Documents\Codex\2026-09-27\quer\outputs\apos_conta_gotas.png"]
for path in paths:
    image = cv2.imread(path)
    h,w = image.shape[:2]
    roi = (81,81,w-81, min(h-112,h-81))
    crop = image[roi[1]:roi[3],roi[0]:roi[2]]
    for kernel in (15, 19, 21, 25, 31):
        background = cv2.medianBlur(crop,kernel)
        contrast = np.max(cv2.absdiff(crop,background),axis=2)
        mask = np.uint8(contrast>=12)
        _, _, stats, _ = cv2.connectedComponentsWithStats(mask,8)
        candidates=[]
        for left,top,width,height,area in stats[1:]:
            if 4<=width<=16 and 4<=height<=16 and abs(width-height)<=2 and area>=.70*width*height:
                candidates.append((int(width),int(height)))
        common=Counter(candidates).most_common(1)[0] if candidates else None
        print(path.split('\\')[-1],kernel,len(candidates),common)
