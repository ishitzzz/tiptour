"""X11 Composite capture exclusion. Never hide/unmap the visible companion.
Only opaque depth-24 window backing pixels are accepted. Unknown background,
translucent windows and unsupported servers refuse rather than invent content.
Candidate automatically attempts clean backing capture when available.
Not parity-cleared. The app uses a logged hide fallback when unsupported.
"""
from PIL import Image, ImageDraw, ImageGrab, ImageChops
from Xlib import X, display, error
from Xlib.ext import composite, shape

_backing=None

def prepare():
    """Must precede mapping our overlay: automatic redirection retains the app
    backing that it would otherwise lose when obscured on a bare X server."""
    global _backing
    if _backing is not None:return
    d=display.Display()
    if not d.has_extension('Composite'):d.close();raise RuntimeError('X11 Composite unavailable')
    errs=[]
    d.screen().root.composite_redirect_subwindows(composite.RedirectAutomatic,onerror=lambda e,r:errs.append(e));d.sync()
    if errs:d.close();raise RuntimeError('X11 backing setup refused')
    _backing=d

def excluding(xids):
    """Isolated capture process owns the server grab. Killing it closes its X
    connection and releases the grab even if an X reply or readback stalls."""
    import subprocess,sys,io,json
    p=subprocess.Popen([sys.executable,'-m',__name__,json.dumps(list(xids))],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:out,err=p.communicate(timeout=1.5)
    except BaseException:
        p.kill();p.communicate();raise RuntimeError('X11 exclusion worker exceeded 1.5s; connection closed')
    if p.returncode:raise RuntimeError('X11 exclusion failed: '+err.decode('utf8','replace')[-250:])
    im=Image.open(io.BytesIO(out));im.load();return im.convert('RGB')

def _capture(xids):
    d=display.Display()
    try:
        root=d.screen().root
        d.grab_server()
        try:
            rg=root.get_geometry();raw=root.get_image(0,0,rg.width,rg.height,X.ZPixmap,0xffffffff)
            full=Image.frombytes('RGB',(rg.width,rg.height),raw.data,'raw','BGRX')
            if rg.depth!=24:raise RuntimeError('unsupported root pixel format')
            mask=Image.new('L',full.size,0);md=ImageDraw.Draw(mask);wins=root.query_tree().children
            for w in wins:
                if w.id not in xids:continue
                wa=w.get_attributes()
                if wa.map_state!=X.IsViewable:continue
                p=root.translate_coords(w,0,0)
                for q in w.shape_get_rectangles(shape.SK.Bounding).rectangles:
                    md.rectangle((p.x+q.x,p.y+q.y,p.x+q.x+q.width-1,p.y+q.y+q.height-1),fill=255)
            box=mask.getbbox()
            if box is None:return full
            remaining=mask.copy();scene=full.copy()
            for w in wins:
                if w.id in xids:continue
                try:wa=w.get_attributes()
                except error.BadWindow:continue  # destroyed resource has no current backing or visible pixels
                if wa.map_state!=X.IsViewable or wa.win_class==X.InputOnly:continue
                wg=w.get_geometry();p=root.translate_coords(w,0,0)
                rect=(p.x,p.y,p.x+wg.width,p.y+wg.height)
                clip=(max(0,box[0],rect[0]),max(0,box[1],rect[1]),min(full.width,box[2],rect[2]),min(full.height,box[3],rect[3]))
                if clip[2]<=clip[0] or clip[3]<=clip[1]:continue
                if wg.depth!=24:raise RuntimeError('translucent backing window unsupported')
                pix=None
                try:
                    pix=w.composite_name_window_pixmap();d.sync()
                    x,y=clip[0]-p.x,clip[1]-p.y;cw,ch=clip[2]-clip[0],clip[3]-clip[1]
                    raw=pix.get_image(x,y,cw,ch,X.ZPixmap,0xffffffff)
                    im=Image.frombytes('RGB',(cw,ch),raw.data,'raw','BGRX')
                    wm=Image.new('L',(cw,ch),0);dr=ImageDraw.Draw(wm)
                    for q in w.shape_get_rectangles(shape.SK.Bounding).rectangles:
                        dr.rectangle((q.x-x,q.y-y,q.x+q.width-x-1,q.y+q.height-y-1),fill=255)
                    scene.paste(im,(clip[0],clip[1]),wm);remaining.paste(0,(clip[0],clip[1],clip[2],clip[3]),wm)
                finally:
                    if pix:pix.free()
            if remaining.getbbox():raise RuntimeError('own UI covers unsupported desktop background')
            full.paste(scene,(0,0),mask);return full
        finally:d.ungrab_server();d.sync()
    finally:d.close()

if __name__=='__main__':
    import sys,json
    try:_capture(json.loads(sys.argv[1])).save(sys.stdout.buffer,'PNG')
    except Exception as e:print(type(e).__name__+': '+str(e),file=sys.stderr);sys.exit(1)
