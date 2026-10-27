"""Run the actual app perception function in isolation, not a copied algorithm."""
import ast,threading,subprocess
from pathlib import Path
from PIL import Image
from tiptour_linux.target_cache import LocalPerceptionTargetCache
source=Path(__file__).resolve().parents[1]/'tiptour_linux/app.py'
tree=ast.parse(source.read_text())
f=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_perceive')
module=ast.Module(body=[f],type_ignores=[]);code=compile(ast.fix_missing_locations(module),str(source),'exec')
class Perception:
 def __init__(self):self.calls=0
 def ocr(self,img):self.calls+=1;return [{'bbox':[20,40,100,20],'center':[70,50],'label':'Launch','source':'ocr','conf':.99}]
class Detector:
 def detect(self,img):return [{'bbox':[10,20,50,20],'center':[35,30],'conf':.9}]
for detector in (None,Detector()):
 p=Perception();cache=LocalPerceptionTargetCache();ns={'_perc_lk':threading.Lock(),'_perc_seq':{'started':0,'applied':0},'detector':detector,'perception':p,'log':lambda *x:None,'LocalPerceptionTargetCache':LocalPerceptionTargetCache,'TARGET_CACHE':cache,'subprocess':subprocess}
 exec(code,ns);y,o,revision,private=ns['_perceive'](Image.new('RGB',(400,200)),True)
 assert p.calls==1 and o[0]['bbox']==[10,20,50,10] and o[0]['center']==[35,25]
 assert bool(y)==bool(detector) and cache.resolve('Launch') and private.resolve('Launch')
 assert revision==1 and ns['_perc_seq']['applied']==1
 cache.clear();ns['_perceive'](Image.new('RGB',(400,200)),True,publish=False)
 assert not cache.current_targets() and p.calls==2
 # Empty OCR is a real miss, never a fabricated target.
 p.ocr=lambda img:[];ns['detector']=None
 y,o,_,private=ns['_perceive'](Image.new('RGB',(400,200)),True)
 assert y==o==[] and private.resolve('Launch') is None and not cache.current_targets()
def unavailable(img):raise FileNotFoundError('test missing OCR binary')
p.ocr=unavailable
y,o,_,private=ns['_perceive'](Image.new('RGB',(400,200)),True)
assert y==o==[] and private.resolve('Launch') is None
print('PASS actual app perception AST: independent OCR with/withoutYOLO, scaling/privatecache/publication, noOCR miss')
