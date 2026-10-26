import gi,json,os
from pathlib import Path
gi.require_version('Gtk','3.0');from gi.repository import Gtk,GLib
D=Path(os.environ['FIXTURE_DIR']); w=Gtk.Window(title='Recovery Native Target');w.set_default_size(600,300); box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);w.add(box)
fields={}
for name in ['first','second','secret','readonly']:
 e=Gtk.Entry();e.get_accessible().set_name(name);e.set_visibility(name!='secret');e.set_editable(name!='readonly');box.pack_start(e,False,False,0);fields[name]=e
b=Gtk.Button(label='button');box.pack_start(b,False,False,0);fields['button']=b
w.show_all();fields['first'].grab_focus();dialog=None
last=''
def tick():
 global last,dialog
 p=D/'command.json'
 if p.exists():
  raw=p.read_text()
  if raw!=last:
   last=raw;d=json.loads(raw);e=fields.get(d.get('field','first'))
   if 'text' in d: e.set_text(d['text'])
   if 'focus' in d: e.grab_focus()
   if 'selection' in d: e.select_region(*d['selection'])
   if 'modal' in d:
    if d['modal']:
     dialog=Gtk.MessageDialog(transient_for=w,modal=True,text='Blocking test modal');dialog.show_all()
    elif dialog: dialog.destroy();dialog=None;fields['first'].grab_focus()
 out={k:{'text':e.get_text(),'focus':e.has_focus(),'selection':e.get_selection_bounds(),'caret':e.get_position()} for k,e in fields.items() if isinstance(e,Gtk.Entry)}
 (D/'state.json').write_text(json.dumps(out));return True
GLib.timeout_add(50,tick);w.connect('destroy',Gtk.main_quit);Gtk.main()
