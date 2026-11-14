"""Read installed visual assets only; never modify the game or ship its files."""
from pathlib import Path
from dataclasses import asdict
import gzip,json,re,struct,math
import xml.etree.ElementTree as ET


class GameAssets:
    def __init__(self,executable):
        self.archive=Path(executable).parent/'resources'/'app.asar'
        with self.archive.open('rb') as stream:
            header=struct.unpack('<4I',stream.read(16))
            if not 0<header[3]<2_000_000:raise ValueError('Index du jeu invalide')
            tree=json.loads(stream.read(header[3]));base=8+header[1]
            def entry(path):
                node=tree
                for part in path.split('/'):node=node['files'][part]
                return node
            code=entry('distBuild/static/game/N.js');pak=entry('distBuild/static/game/lib/default.pak')
            if code['size']>40_000_000:raise ValueError('Index visuel du jeu trop grand')
            stream.seek(base+int(code['offset']));text=stream.read(code['size']).decode('utf-8')
            self.base=base+int(pak['offset']);self.size=pak['size']
        self.entries={name:(int(offset),int(size)) for offset,name,size in re.findall(
            r'R0i([0-9]+)R1zR2R(?:3|16)R4y[0-9]+:([^R]+)R6i([0-9]+)',text)}

    def read(self,name):
        from urllib.parse import quote
        key=quote(name,safe='');offset,size=self.entries[key]
        if size>1_000_000 or offset<0 or offset+size>self.size:raise ValueError('Ressource visuelle invalide')
        with self.archive.open('rb') as stream:
            stream.seek(self.base+offset);data=stream.read(size)
        if data[:2]==b'\x1f\x8b':
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as zipped:data=zipped.read(4_000_001)
        if len(data)>4_000_000:raise ValueError('Ressource visuelle décompressée trop grande')
        return data

    def image(self,name):
        import cv2,numpy as np
        data=self.read('assets/data/'+name)
        image=cv2.imdecode(np.frombuffer(data,dtype='uint8'),cv2.IMREAD_UNCHANGED)
        if image is None:raise ValueError('Image du jeu illisible')
        return image

    def prepare_hud(self,directory,scale,none_region):
        import cv2,numpy as np
        from .hud import ink,wind_ink
        directory=Path(directory)
        fonts={}
        for family,font in [('score',109),('wind',475),('wind-medium',352)]:
            image=cv2.imdecode(np.frombuffer(self.read(f'assets/graphics/1x/font-{font}.png'),dtype='uint8'),-1)
            chars={int(n.get('id')):n for n in ET.fromstring(self.read(f'assets/graphics/1x/font-{font}.fnt')).findall('.//char')}
            fonts[family]=(image,chars)
            for digit in range(10):
                node=chars[48+digit];x,y,w,h=[int(node.get(k)) for k in ('x','y','width','height')]
                select=ink if family=='score' else wind_ink
                cv2.imwrite(str(directory/f'ocr-{family}-{digit}.png'),select(image[y:y+h,x:x+w])*255)
                glyph=image[y:y+h,x:x+w]
                shifts=(0,.25,.5,.75) if family=='score' else (0,.5)
                for index,(dx,dy) in enumerate(( (dx,dy) for dx in shifts for dy in (0,.25,.5,.75))):
                    matrix=np.array([[scale,0,2+dx],[0,scale,2+dy]],dtype='float64')
                    raster=cv2.warpAffine(glyph,matrix,(math.ceil(w*scale)+5,math.ceil(h*scale)+5),flags=cv2.INTER_LINEAR)
                    name='wind' if family=='wind-medium' else family
                    variant=index+8 if family=='wind-medium' else index
                    cv2.imwrite(str(directory/f'ocr-{name}-{digit}-v{variant}.png'),select(raster)*255)
        image,chars=fonts['score'];width=sum(int(chars[ord(c)].get('xadvance')) for c in 'None')
        mask=np.zeros((20,width+8),dtype='uint8');cursor=0
        for char in 'None':
            n=chars[ord(char)];x,y,w,h=[int(n.get(k)) for k in ('x','y','width','height')]
            mask[:h,cursor:cursor+w]|=ink(image[y:y+h,x:x+w]);cursor+=int(n.get('xadvance'))
        cv2.imwrite(str(directory/'ocr-none.png'),mask*255)
        for level in range(3):cv2.imwrite(str(directory/f'wind-arrow-{level}.png'),self.image(f'DartWind{level}.png'))
        rect=lambda x,y,w,h:[round(v*scale) for v in (x,y,w,h)]
        data=dict(schema_version=1,scale=scale,score_region=rect(4,28,120,25),lives_region=rect(570,28,390,27),
                  wind_region=rect(496,6,107,41),arrow_split=round(63.5*scale),none_region=list(none_region))
        (directory/'hud.json').write_text(json.dumps(data,indent=2),encoding='utf-8')


def auto_calibrate(window_id,destination,cancel,seed=None):
    from .assisted import focus_game,list_game_windows
    from .capture import WindowsFrameSource
    from .models import Rect,Profile
    from .calibration import VISUAL_VERSION,external_directory
    from .vision import cv2,np,find_blade,fit_pivot,find_red_target
    from datetime import datetime,timezone
    from uuid import uuid4
    desktop=focus_game(window_id);context=desktop.snapshot()
    window=next(w for w in list_game_windows() if w['id']==window_id)
    assets=GameAssets(window['executable'])
    bar=round(32*context.dpi/96)
    scale=min(context.rect.width/960,(context.rect.height-bar)/540)
    width,height=round(960*scale),round(540*scale)
    scene=Rect(context.rect.left+(context.rect.width-width)//2,
               context.rect.top+bar+(context.rect.height-bar-height)//2,width,height)
    with WindowsFrameSource(desktop,scene) as source:
        frame=source.grab();image=np.frombuffer(frame.bgr,dtype='uint8').reshape(height,width,3)
        raw=assets.image('DartPlat.png');tw,th=round(raw.shape[1]*scale),round(raw.shape[0]*scale)
        template=cv2.resize(raw,(tw,th),interpolation=cv2.INTER_LINEAR)
        mask=(template[:,:,3]>180).astype('uint8')*255
        mask[:th//2]=0  # Feet overlap the platform's upper half.
        result=1-cv2.matchTemplate(image,template[:,:,:3],cv2.TM_SQDIFF_NORMED,mask=mask)
        # Restrict to the platform's game area; header icons cannot qualify.
        result[:round(170*scale)]=0;result[:,:round(40*scale)]=0;result[:,round(550*scale):]=0
        _,quality,_,position=cv2.minMaxLoc(result)
        if quality<.9:raise ValueError('Affichez le mini-jeu Throwy Darts, puis relancez la préparation automatique.')
        px,py=position
        ax=max(0,round(px+40*scale));ay=max(0,round(py-145*scale))
        arm=Rect(ax,ay,min(round(105*scale),width-ax),min(round(175*scale),height-ay))
        board=Rect(round(900*scale),round(80*scale),min(round(60*scale),width-round(900*scale)),round(420*scale))
        anchor=Rect(round(px+6*scale),round(py+14*scale),round(92*scale),round(14*scale))
        wind=Rect(round(496*scale),round(22*scale),round(65*scale),round(23*scale))
        target=find_red_target(image,board)
        if target is None:raise ValueError('Cible rouge non reconnue.')
        lines=[]
        for _ in range(180):
            import time
            time.sleep(1/60)
            if cancel.is_set():raise RuntimeError('Calibration arrêtée')
            frame=source.grab();pixels=np.frombuffer(frame.bgr,dtype='uint8').reshape(height,width,3)
            line=find_blade(pixels,arm,area_min=400*(scale/2.5)**2,area_max=1400*(scale/2.5)**2,
                            length_min=50*scale/2.5,length_max=180*scale/2.5)
            if line:lines.append(line)
        if len(lines)<90:raise ValueError(f'Fléchette insuffisamment reconnue ({len(lines)}/180).')
        pivot,metrics=fit_pivot(lines)
    destination=external_directory(destination);destination.mkdir(parents=True,exist_ok=False)
    regions=dict(arm=arm,board=board,anchor=anchor,wind_none=wind)
    profile=Profile(1,uuid4().hex,datetime.now(timezone.utc).isoformat(),context.rect,scene,context.dpi,VISUAL_VERSION,None,())
    metrics.update(vision_scale=scale/2.5,platform_quality=quality,scale=scale,platform_position=list(position))
    cv2.imwrite(str(destination/'reference.png'),image)
    for name,region in [('anchor',anchor),('wind-none',wind)]:
        cv2.imwrite(str(destination/(name+'.png')),image[region.top:region.top+region.height,region.left:region.left+region.width])
    assets.prepare_hud(destination,scale,(wind.left,wind.top,wind.width,wind.height))
    (destination/'profile.json').write_text(json.dumps(asdict(profile),indent=2),encoding='utf-8')
    (destination/'visual.json').write_text(json.dumps(dict(schema_version=1,profile_id=profile.profile_id,
        regions={k:asdict(v) for k,v in regions.items()},pivot=pivot,target_size=[target[0].width,target[0].height],
        template_threshold=.98,metrics=metrics),indent=2),encoding='utf-8')
    from .ballistics import application_model
    data=application_model(profile.profile_id,scale,
        (metrics['angle_max_degrees']-metrics['angle_min_degrees'])/2,
        px+110*scale-pivot[0],py-51*scale-pivot[1])
    model=destination/'physics-model.json';model.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return dict(kind='auto-calibration',calibration=str(destination),model=str(model),preview=str(destination/'reference.png'),inputs_sent=False,metrics=metrics)
