from pathlib import Path
from PIL import Image
from tiptour_linux.engine import ReadOnlyEngine
from tiptour_linux.app_skills import AppSkillRegistry
from tiptour_linux.target_cache import LocalPerceptionTargetCache
import io,base64
cache=LocalPerceptionTargetCache();cache.update([dict(bbox=[10,20,110,50],label='Save',source='ocr',conf=1)],(400,200),(0,0,400,200))
flags=dict(autopilot=False,screenshots=False,accurate_grounding=True,action_driver=False)
refreshed=[];captures=[]
def capture():
 captures.append(1);im=Image.new('RGB',(400,200),'white');small=im.resize((200,100));b=io.BytesIO();small.save(b,'JPEG');return im,b.getvalue(),im.size
engine=ReadOnlyEngine(lambda:dict(name='Blender',desktop_id='org.blenderfoundation.blender'),lambda:flags,lambda:None,cache,refreshed.append,capture,AppSkillRegistry(roots=[(Path(__file__).resolve().parents[1]/'skills','bundled')]))
assert engine.observe()['isAutopilotEnabled'] is False
assert engine.skills()['skillCount']==1 and engine.active_skill()['skill']['isActive']
assert engine.targets()['targetCount']==1 and not refreshed
assert engine.targets(True,'test')['refreshed'] and refreshed==['test']
assert engine.targets()['targets'][0]['screenshotBox']==[10,20,110,50]
assert engine.screenshots()['reason']=='screenshots_disabled' and captures==[]
flags['screenshots']=True;r=engine.screenshots();assert r['ok'] and r['screenshotCount']==1 and len(captures)==1
assert r['screenshots'][0]['displayWidthInPoints']==400
assert r['screenshots'][0]['screenshotWidthInPixels']==200
im=Image.open(io.BytesIO(base64.b64decode(r['screenshots'][0]['dataURL'].split(',',1)[1])));assert im.size==(200,100)
assert not hasattr(engine,'act') and not hasattr(engine,'submit')
print('read-only facade offline adapter contract: pass, not live runtime/HTTP')

# Setting can change while the native capture is blocked. Never expose its bytes.
flags['screenshot_epoch']=1
original=engine._capture
def changed_capture():
 value=original();flags['screenshots']=False;return value
engine._capture=changed_capture
assert engine.screenshots()['reason']=='screenshots_disabled'
flags['screenshots']=True
def off_on_capture():
 value=original();flags['screenshot_epoch']+=2;return value
engine._capture=off_on_capture
assert engine.screenshots()['reason']=='screenshots_disabled'
print('PASS readonly capture-time off and off/on epoch withhold raw images')
