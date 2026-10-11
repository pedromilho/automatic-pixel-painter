import cv2
import numpy as np

image = cv2.imread(r"C:\Users\pedro\AppData\Local\Temp\codex-clipboard-e24e9fac-1cf8-4e0e-a84a-3a0b9072ea13.png")
points = [(65, 105), (102, 105), (137, 105), (137, 141), (102, 247), (65, 141)]
for kernel in (15, 21, 25, 31):
    background = cv2.medianBlur(image, kernel)
    contrast = np.max(cv2.absdiff(image, background), axis=2)
    features = []
    for x, y in points:
        patch = contrast[y-3:y+4, x-3:x+4]
        flatness = image[y-3:y+4, x-3:x+4].reshape(-1,3).std(axis=0).max()
        features.append((x, y, int(np.median(patch)), round(float((patch>=12).mean()), 2), round(float(flatness),1)))
    print(kernel, features)

background = cv2.medianBlur(image, 25)
contrast = np.max(cv2.absdiff(image, background), axis=2)
for x,y in [(66,107),(102,107),(138,107),(138,141),(102,248)]:
    inner=image[y-3:y+4,x-3:x+4]
    patch=contrast[y-3:y+4,x-3:x+4]
    center=np.median(inner.reshape(-1,3),axis=0)
    sides=[image[y-1:y+2,x+6],image[y-1:y+2,x-6],image[y+6,x-1:x+2],image[y-6,x-1:x+2]]
    print('grid',x,y,'flat',inner.reshape(-1,3).std(axis=0).max(),'median',np.median(patch),'coverage',(patch>=12).mean(),'sides',[np.max(np.abs(center-np.median(side,axis=0))) for side in sides])
