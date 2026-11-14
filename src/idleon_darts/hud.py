"""Profile-owned digit/arrow references. No game assets are distributed here."""
from pathlib import Path
import math
from .calibration import _visual_json


def normalize_mask(mask,size=40):
    import cv2,numpy as np
    ys,xs=np.where(mask)
    out=np.zeros((size,size),dtype='uint8')
    if not len(xs):return out
    patch=mask[ys.min():ys.max()+1,xs.min():xs.max()+1].astype('uint8')
    scale=(size-4)/max(patch.shape);w=max(1,round(patch.shape[1]*scale));h=max(1,round(patch.shape[0]*scale))
    patch=cv2.resize(patch,(w,h),interpolation=cv2.INTER_NEAREST)
    y,x=(size-h)//2,(size-w)//2;out[y:y+h,x:x+w]=patch
    return out


def ink(image,colour=False):
    import numpy as np
    rgb=image[:,:,:3];spread=np.ptp(rgb,axis=2)
    selected=(rgb.max(axis=2)>150)&(spread>65) if colour else (rgb.min(axis=2)>150)&(spread<45)
    if image.shape[2]==4:selected&=image[:,:,3]>100
    return selected.astype('uint8')


def similarity(a,b):
    import numpy as np
    union=np.count_nonzero(a|b)
    return float(np.count_nonzero(a&b)/union) if union else 0.


def wind_ink(image):
    selected=image[:,:,:3].max(axis=2)>150
    if image.shape[2]==4:selected&=image[:,:,3]>100
    return selected.astype('uint8')


def holes(mask):
    import cv2,numpy as np
    return cv2.connectedComponents(np.pad(1-mask.astype('uint8'),1,constant_values=1),connectivity=4)[0]-2


class HudReader:
    def __init__(self,directory):
        import cv2
        self.directory=Path(directory);self.config=_visual_json(self.directory/'hud.json')
        self.digits={}
        self.digit_variants={}
        for family in ('score','wind'):
            self.digits[family]=[]
            for digit in range(10):
                mask=cv2.imread(str(self.directory/f'ocr-{family}-{digit}.png'),cv2.IMREAD_GRAYSCALE)
                if mask is None:raise ValueError('Référence de chiffres manquante.')
                self.digits[family].append(normalize_mask((mask>127).astype('uint8')))
            self.digit_variants[family]=[]
            for digit,canonical in enumerate(self.digits[family]):
                variants=[canonical]
                for file in sorted(self.directory.glob(f'ocr-{family}-{digit}-v*.png'))[:16]:
                    raw=cv2.imread(str(file),cv2.IMREAD_GRAYSCALE)
                    if raw is not None:variants.append(normalize_mask((raw>127).astype('uint8')))
                self.digit_variants[family].append(variants)
        none_path=self.directory/'ocr-none.png'
        raw_none=cv2.imread(str(none_path),cv2.IMREAD_GRAYSCALE) if none_path.exists() else None
        self.none_mask=normalize_mask((raw_none>127).astype('uint8')) if raw_none is not None else None
        self.arrows=[];self.cache=None
        for level in range(3):
            raw=cv2.imread(str(self.directory/f'wind-arrow-{level}.png'),cv2.IMREAD_UNCHANGED)
            if raw is None:raise ValueError('Référence de direction manquante.')
            base=ink(raw,True);h,w=base.shape
            # Padding preserves the complete rotated shape, including transparent margins.
            import numpy as np
            padded=np.zeros((80,80),dtype='uint8');padded[40-h//2:40-h//2+h,40-w//2:40-w//2+w]=base
            references=[]
            for angle in range(-90,91):
                rotated=cv2.warpAffine(padded,cv2.getRotationMatrix2D((40,40),-angle,1),(80,80),flags=cv2.INTER_NEAREST)
                references.append((angle,normalize_mask(rotated)))
            self.arrows.append(references)

    def crop(self,image,key):
        x,y,w,h=self.config[key]
        if x<0 or y<0 or x+w>image.shape[1] or y+h>image.shape[0]:raise ValueError('Compteurs hors image.')
        return image[y:y+h,x:x+w]

    def digits_in(self,mask,family,prefix=False):
        import cv2,numpy as np
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'))
        components=[]
        for i in range(1,n):
            x,y,w,h,area=stats[i]
            if area>=15 and h>=8 and w>=2:components.append((int(x),int(y),int(w),int(h),i))
        components.sort()
        if not components:return None
        if not prefix:
            # The score label contains a colon: two small, vertically aligned dots.
            dots=[s for s in stats[1:] if 2<=s[2]<=12 and 2<=s[3]<=10 and s[4]>=3]
            boundaries=[max(a[0]+a[2],b[0]+b[2]) for a in dots for b in dots
                        if abs(int(a[0])-int(b[0]))<=3 and 5<=abs(int(a[1])-int(b[1]))<=25]
            if not boundaries:return None
            boundary=max(boundaries);components=[c for c in components if c[0]>=boundary]
        chars=[];previous=None
        for x,y,w,h,label in components:
            if previous is not None and prefix and x-previous>max(6,h*.3):break
            normalized=normalize_mask((labels[y:y+h,x:x+w]==label).astype('uint8'))
            count_holes=holes((labels[y:y+h,x:x+w]==label).astype('uint8'))
            scores=sorted([(max(similarity(normalized,t) for t in variants)
                            if i not in (0,8) or count_holes==(2 if i==8 else 1) else 0.,i)
                           for i,variants in enumerate(self.digit_variants[family])],reverse=True)
            if scores[0][0]<.66 or scores[0][0]-scores[1][0]<.025:
                if prefix:break
                return None
            chars.append(str(scores[0][1]));previous=x+w
            if len(chars)>6:return None
        return int(''.join(chars)) if chars else None

    def score(self,image):return self.digits_in(ink(self.crop(image,'score_region')),'score')

    def lives(self,image):
        import cv2,numpy as np
        a=self.crop(image,'lives_region');mask=((a[:,:,2]>180)&(a[:,:,1]<120)&(a[:,:,0]<140)).astype('uint8')
        _,_,stats,_=cv2.connectedComponentsWithStats(mask)
        scale=self.config.get('scale',2.5)/2.5
        return sum(1 for x,y,w,h,area in stats[1:] if area>120*scale*scale and w>12*scale and h>12*scale)

    def wind(self,image):
        import numpy as np
        if self.none_mask is not None:
            quality=similarity(normalize_mask(ink(self.crop(image,'none_region'))),self.none_mask)
            if quality>=.6:return dict(mph=0,angle=0,features=(0.,0.),quality=quality)
        region=self.crop(image,'wind_region');stamp=hash(region.tobytes())
        if self.cache and self.cache[0]==stamp:return self.cache[1]
        split=self.config.get('arrow_split',160)
        top=round(16*self.config.get('scale',2.5))
        mph=self.digits_in(wind_ink(region[top:,:split]),'wind',prefix=True)
        if mph is None or not 1<=mph<=35:return None
        arrow=normalize_mask(ink(region[:,split:],True));level=0 if mph<10 else (1 if mph<18 else 2)
        scores=sorted([(similarity(arrow,mask),angle) for angle,mask in self.arrows[level]],reverse=True)
        best,angle=scores[0]
        distant=max((s for s,a in scores if abs(a-angle)>15),default=0.)
        if best<.58 or best-distant<.04:return None
        magnitude=mph-.5;radians=math.radians(angle)
        result=dict(mph=mph,angle=angle,features=(magnitude*math.cos(radians),magnitude*math.sin(radians)),quality=best)
        self.cache=(stamp,result);return result
