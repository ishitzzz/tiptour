import os,tempfile
os.environ['TIPTOUR_CONFIG_DIR']=tempfile.mkdtemp(prefix='r56-settings-')
from tiptour_linux import settings
from tiptour_linux.status_item import StatusItem,pointer_icon
from gi.repository import Gtk
seen=[]
w=settings.gtk_window(lambda:seen.append('closed'),standalone=False)
b=w.get_children()[0];cs=[x for x in b.get_children() if isinstance(x,Gtk.CheckButton)]
assert len(cs)==5
assert settings.DEFAULTS['isAccurateGroundingEnabled'] is False
assert 'Accurate Grounding' in cs[2].get_label()
cs[2].set_active(True);assert settings.load()['isAccurateGroundingEnabled'] is True
os.environ['TIPTOUR_ACCURATE_GROUNDING']='0';settings.apply_env();assert os.environ['TIPTOUR_ACCURATE_GROUNDING']=='0'
cs[1].set_active(False);assert settings.load()['isScreenshotStreamingEnabled'] is False
os.environ['TIPTOUR_STREAM']='1';settings.apply_env();assert os.environ['TIPTOUR_STREAM']=='1'
w.destroy();assert seen==['closed']
s=StatusItem(lambda:None,lambda:None,lambda:None,lambda:None)
assert pointer_icon().get_width()==18
s.menu.emit('map');assert s.capture_busy.is_set()
s.menu.emit('unmap');assert not s.capture_busy.is_set()
s.close()
print('PASS isolated supportedsettings save, explicitenv override, ownedclose callback,18px icon, shellbusy events; no userconfig changes')
