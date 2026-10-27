"""Actual parser and faithful cache, synthetic TSV only; native pixels separately."""
from PIL import Image
from tiptour_linux import perception as p
from tiptour_linux.target_cache import LocalPerceptionTargetCache
from types import SimpleNamespace
old=p.subprocess.run
try:
 p.subprocess.run=lambda *a,**k:SimpleNamespace(stdout='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t10\t40\t22\t12\t95\tFile\n5\t1\t1\t1\t1\t2\t50\t40\t25\t12\t92\tEdit\n5\t1\t1\t1\t2\t1\t100\t80\t50\t14\t96\tSave\n5\t1\t1\t1\t2\t2\t160\t80\t25\t14\t94\tAs\n5\t1\t2\t1\t1\t1\t20\t100\t22\t12\t12\tNoise\n')
 es=p.ocr(Image.new('RGB',(300,200)));cache=LocalPerceptionTargetCache();els=[dict(e,bbox=[e['bbox'][0],e['bbox'][1],e['bbox'][0]+e['bbox'][2],e['bbox'][1]+e['bbox'][3]]) for e in es];cache.update(els,(300,200),(0,0,300,200))
 assert cache.resolve('File')['global_point']==(21,46)
 assert cache.resolve('Edit')['global_point']==(62.5,46)
 assert cache.resolve('Save As')['global_rect']==(100,80,85,14)
 assert not any(e['label']=='Noise' for e in es)
 assert len(es)==len({(e['label'],tuple(e['bbox'])) for e in es})
finally:p.subprocess.run=old
print('PASS actual OCR parser retains exact single-word geometry and phrase line, confidence filter, no duplicate observation')
