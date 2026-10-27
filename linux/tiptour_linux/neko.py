"""Pinned NekoCursorView sprite state. No input, provider or action behavior."""
import math
from pathlib import Path

DIRECTIONS=('right','downright','down','downleft','left','upleft','up','upright')
def direction(dx,dy,minimum=1.5):
    if math.hypot(dx,dy)<minimum:return None
    return DIRECTIONS[int(((math.degrees(math.atan2(dy,dx))+360)%360+22.5)//45)%8]

class Neko:
    def __init__(self):
        self.previous=(0.,0.);self.direction='right';self.frame=1;self.idle=0.;self.last=None;self.cache={}
    def tick(self,position,now):
        if self.last is not None and now-self.last<.2:return False
        self.last=now
        d=direction(position[0]-self.previous[0],position[1]-self.previous[1])
        if d:self.direction=d;self.idle=0.
        else:self.idle+=.2
        self.frame=2 if self.frame==1 else 1;self.previous=position
        return True
    @property
    def sprite(self):
        if self.idle>=4:return 'sleep%d'%self.frame
        if self.idle>=1.2:return 'scratch%d'%self.frame
        if self.idle>0:return 'awake'
        return self.direction+str(self.frame)
    def surface(self,name):
        import cairo
        if name not in self.cache:
            path=Path(__file__).with_name('neko_sprites')/(name+'.png')
            try:self.cache[name]=cairo.ImageSurface.create_from_png(str(path))
            except (OSError,cairo.Error):self.cache[name]=None
        return self.cache[name]
    def paint(self,c,x,y,size=32,scale=1.,name=None,opacity=1.):
        import cairo
        surface=self.surface(name or self.sprite)
        c.save();c.translate(x,y);c.scale(scale,scale)
        if surface:
            c.scale(size/surface.get_width(),size/surface.get_height())
            c.set_source_surface(surface,-surface.get_width()/2,-surface.get_height()/2)
            c.get_source().set_filter(cairo.FILTER_NEAREST);c.paint_with_alpha(opacity)
        else:
            c.arc(0,0,6,0,math.tau);c.set_source_rgba(1,.2,.6,.8);c.fill()
        c.restore()

class PawTrail:
    """Programmatic flight footprints, not a drawing/annotation surface."""
    def __init__(self,neko):
        import gi,cairo
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk,Gdk
        self.Gdk=Gdk;self.cairo=cairo;self.neko=neko;self.points=[];self.fade=None
        self.window=Gtk.Window(type=Gtk.WindowType.POPUP)
        w=self.window;w.set_wmclass('tiptour-neko-trail','TipTourNekoTrail');w.set_title('TipTour Neko flight footprints')
        w.set_app_paintable(True);w.set_decorated(False);w.set_keep_above(True);w.set_accept_focus(False)
        screen=w.get_screen();self.W,self.H=screen.get_width(),screen.get_height();w.set_default_size(self.W,self.H);w.move(0,0)
        vis=screen.get_rgba_visual();self.composited=bool(vis and screen.is_composited())
        if self.composited:w.set_visual(vis)
        w.connect('draw',lambda _,c:(self.paint(c),False)[1]);w.connect('realize',lambda *_:w.get_window().input_shape_combine_region(cairo.Region(),0,0))
    def paint(self,c):
        import time
        c.set_operator(self.cairo.OPERATOR_SOURCE);c.set_source_rgba(0,0,0,0);c.paint();c.set_operator(self.cairo.OPERATOR_OVER)
        opacity=max(0.,1-(time.monotonic()-self.fade)/.45) if self.fade is not None else 1.
        points=[]
        for i in range(1,len(self.points),3):
            a,b=self.points[i-1],self.points[i];points.append((b,direction(b[0]-a[0],b[1]-a[1],.5) or 'right'))
        for i,(p,d) in enumerate(points):self.neko.paint(c,*p,size=16,name='fp_'+d,opacity=(.15+.55*i/max(len(points)-1,1))*opacity)
    def start(self,p):self.points=[p];self.fade=None
    def append(self,p):self.points=(self.points+[p])[-22:]
    def finish(self,now):self.fade=now
    def clear(self):self.points=[];self.fade=None;self.window.hide()
    def tick(self,now,visible):
        if self.fade is not None and now-self.fade>=.47:self.clear();return
        if not self.points or not visible:self.window.hide();return
        w=self.window;w.show_all()
        if not self.composited and w.get_window():
            s=self.cairo.ImageSurface(self.cairo.FORMAT_A8,self.W,self.H);self.paint(self.cairo.Context(s))
            w.get_window().shape_combine_region(self.Gdk.cairo_region_create_from_surface(s),0,0)
            w.get_window().input_shape_combine_region(self.cairo.Region(),0,0)
        w.queue_draw()
