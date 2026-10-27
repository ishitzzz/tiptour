"""X11 Composite capture exclusion. Never hide/unmap the visible companion.
Depth-24 backing and premultiplied depth-32 ARGB layers are reconstructed
only over fully covered backing. Unknown background, global opacity and
unsupported pixel depths refuse rather than invent content.
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
            # GTK toplevel XIDs may be children of WM decoration frames.
            # Mask/exclude the root child, not only the client id, or the frame's
            # backing can silently redraw our own entry into the reconstructed image.
            owned=set()
            for xid in xids:
                try:
                    w=d.create_resource_object('window',xid)
                    while True:
                        parent=w.query_tree().parent
                        if parent.id==root.id: break
                        if not parent.id: raise RuntimeError('own window has no root ancestor')
                        w=parent
                    owned.add(w.id)
                except error.BadWindow: continue
            xids=owned
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
                if wg.depth not in (24,32):raise RuntimeError('unsupported backing pixel depth')
                opacity=w.get_full_property(d.intern_atom('_NET_WM_WINDOW_OPACITY'),0)
                if opacity is not None and (len(opacity.value)!=1 or int(opacity.value[0])!=0xffffffff):
                    raise RuntimeError('global window opacity unsupported')
                pix=None
                try:
                    pix=w.composite_name_window_pixmap();d.sync()
                    x,y=clip[0]-p.x,clip[1]-p.y;cw,ch=clip[2]-clip[0],clip[3]-clip[1]
                    raw=pix.get_image(x,y,cw,ch,X.ZPixmap,0xffffffff)
                    im=Image.frombytes('RGBA' if wg.depth==32 else 'RGB',(cw,ch),raw.data,'raw','BGRA' if wg.depth==32 else 'BGRX')
                    wm=Image.new('L',(cw,ch),0);dr=ImageDraw.Draw(wm)
                    for q in w.shape_get_rectangles(shape.SK.Bounding).rectangles:
                        dr.rectangle((q.x-x,q.y-y,q.x+q.width-x-1,q.y+q.height-y-1),fill=255)
                    if wg.depth==32:
                        # X Render ARGB pixels are premultiplied. Rebuild over known
                        # lower backing, never blend a pointer-contaminated root sample.
                        alpha=im.getchannel('A')
                        inverse=ImageChops.invert(alpha).convert('RGB')
                        lower=scene.crop(clip)
                        blended=ImageChops.add(im.convert('RGB'),ImageChops.multiply(lower,inverse))
                        scene.paste(blended,(clip[0],clip[1]),wm)
                        opaque=ImageChops.multiply(alpha.point(lambda a:255 if a==255 else 0),wm)
                        remaining.paste(0,clip,opaque)
                    else:
                        scene.paste(im,(clip[0],clip[1]),wm);remaining.paste(0,clip,wm)
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
