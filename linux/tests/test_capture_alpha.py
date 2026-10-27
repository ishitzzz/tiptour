"""Actual ARGB branch extracted from capture source, explicit pixel fixtures."""
import ast,pathlib
from PIL import Image,ImageChops
root=ast.parse(pathlib.Path('tiptour_linux/x11_capture.py').read_text())
branch=next(n for n in ast.walk(root) if isinstance(n,ast.If) and ast.unparse(n.test)=='wg.depth == 32')
code=compile(ast.fix_missing_locations(ast.Module(body=branch.body,type_ignores=[])),'actual-argb-branch','exec')
def apply(back,rgba,unknown=255,shape=255):
 scene=Image.new('RGB',(1,1),back);remaining=Image.new('L',(1,1),unknown)
 ns={'ImageChops':ImageChops,'im':Image.new('RGBA',(1,1),rgba),'wm':Image.new('L',(1,1),shape),'scene':scene,'remaining':remaining,'clip':(0,0,1,1)}
 exec(code,ns);return scene.getpixel((0,0)),remaining.getpixel((0,0))
assert apply((20,40,60),(100,50,25,128),0)==((109,69,54),0)
assert apply((20,40,60),(0,0,0,0))==((20,40,60),255)
assert apply((20,40,60),(100,50,25,255))==((100,50,25),0)
assert apply((20,40,60),(100,50,25,255),255,0)==((20,40,60),255)
assert apply((0,0,255),(128,0,0,128))[1]==255 # translucent over unknown must remain refused
# Guard exists on the actual read path before pixmap decoding.
s=pathlib.Path('tiptour_linux/x11_capture.py').read_text();assert "if remaining.getbbox():raise RuntimeError" in s
assert "_NET_WM_WINDOW_OPACITY" in s and '!=0xffffffff' in s
print('PASS actual premultipliedARGB branch: layer blend, opaque coverage, transparent unknown, shape mask; unknown/opacity refusal guards present')
