"""Strict visual anchors with a bounded two-pixel render alignment search."""
import cv2
import numpy as np

def anchor_scores(image,reference,box,tolerance=2):
    x1,y1,x2,y2=box
    if reference.size!=(x2-x1,y2-y1):return -1,float('inf')
    search=np.asarray(image.crop((max(0,x1-tolerance),max(0,y1-tolerance),
        min(image.width,x2+tolerance),min(image.height,y2+tolerance))))
    ref=np.asarray(reference)
    if search.shape[0]<ref.shape[0] or search.shape[1]<ref.shape[1]:return -1,float('inf')
    _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(search,ref,cv2.TM_CCOEFF_NORMED))
    actual=search[y:y+ref.shape[0],x:x+ref.shape[1]]
    return score,float(np.abs(actual.astype('int16')-ref.astype('int16')).mean())
