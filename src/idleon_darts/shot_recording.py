"""Bounded post-release flight recording; encoding happens after acquisition."""
from dataclasses import asdict
from pathlib import Path
import json


class FlightRecorder:
    def __init__(self,enabled=True):
        self.enabled=enabled;self.frames=[];self.bytes=0;self.last_ns=None
        self.interval_ns=50_000_000

    def add(self,frame,launcher):
        if not self.enabled or len(self.frames)>=48:return
        if self.last_ns is not None and frame.end_ns-self.last_ns<self.interval_ns:return
        import cv2,numpy as np
        from .models import Rect
        image=np.frombuffer(frame.bgr,dtype='uint8').reshape(frame.region.height,frame.region.width,3)
        left=max(0,int(launcher[0]-80));right=image.shape[1]
        patch=image[:,left:right]
        scale=min(1.,960/patch.shape[1],540/patch.shape[0])
        size=(max(1,round(patch.shape[1]*scale)),max(1,round(patch.shape[0]*scale)))
        pixels=cv2.resize(patch,size,interpolation=cv2.INTER_AREA) if scale<1 else patch.copy()
        if self.bytes+pixels.nbytes>80_000_000:return
        crop=Rect(left,0,right-left,image.shape[0])
        self.frames.append((dict(frame_id=frame.frame_id,capture_start_ns=frame.start_ns,
            capture_end_ns=frame.end_ns,sample_ns=frame.sample_ns,crop=asdict(crop),
            encoded_width=size[0],encoded_height=size[1]),pixels))
        self.bytes+=pixels.nbytes;self.last_ns=frame.end_ns

    def save(self,directory):
        import cv2
        directory=Path(directory);metadata=[]
        if self.frames:(directory/'flight').mkdir(exist_ok=True)
        for index,(row,pixels) in enumerate(self.frames):
            name=f'flight/frame-{index:03d}.png'
            if not cv2.imwrite(str(directory/name),pixels):raise OSError('Écriture d’une image de trajectoire impossible')
            metadata.append(dict(row,image=name))
        data=dict(schema_version=1,enabled=self.enabled,frames=metadata,
                  coordinates='crop relative to profile ROI; encoded image may be downscaled',
                  max_frames=48,target_fps=1e9/self.interval_ns)
        (directory/'flight.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        return len(metadata)
