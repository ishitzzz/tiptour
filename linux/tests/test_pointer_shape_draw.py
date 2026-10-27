"""Actual queue override ordering; native pixels are checked separately."""
import ast,pathlib
source=pathlib.Path('tiptour_linux/overlay.py').read_text()
cls=next(x for x in ast.parse(source).body if isinstance(x,ast.ClassDef) and x.name=='PointerOverlay')
f=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='queue_draw')
class Base:
 def queue_draw(self):self.calls.append('queue')
ns={'Base':Base};node=ast.ClassDef(name='Probe',bases=[ast.Name(id='Base',ctx=ast.Load())],keywords=[],body=[f],decorator_list=[])
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'actual-overlay-queue','exec'),ns)
for composited,expected in [(False,['shape','queue']),(True,['queue'])]:
 w=ns['Probe']();w.composited=composited;w.calls=[];w.get_window=lambda:object();w.apply_shape=lambda:w.calls.append('shape');w.queue_draw();assert w.calls==expected,w.calls
print('PASS actual override: native shape before GTK invalidation, composited unchanged; pixels separate')
f=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='on_realize')
node.body=[f]
class Cairo:
 @staticmethod
 def Region():return 'empty'
ns={'Base':Base,'cairo':Cairo};exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'actual-overlay-realize','exec'),ns)
for composited,expected in [(False,['widget-empty','shape']),(True,['widget-empty'])]:
 w=ns['Probe']();w.composited=composited;w.calls=[];w.input_shape_combine_region=lambda r:w.calls.append('widget-'+r);w.apply_shape=lambda:w.calls.append('shape');w.on_realize();assert w.calls==expected,w.calls
print('PASS actual realize stores empty input on widget before first map')
