from pathlib import Path
import os,tempfile,json,subprocess,sys,threading
from tiptour_linux import app_skills,actions
from tiptour_linux.engine import ReadOnlyEngine
from tiptour_linux.target_cache import LocalPerceptionTargetCache
bundled=Path(app_skills.__file__).resolve().parents[1]/'skills/blender/SKILL.md'
with tempfile.TemporaryDirectory() as d:
 os.environ['HOME']=d;os.chdir(d)
 target=Path(d)/'.tiptour/skills/blender.md';target.parent.mkdir(parents=True);target.write_text(bundled.read_text())
 first=app_skills.shared_registry();skill=first.skill('Blender');assert skill
 peers=[]
 threads=[threading.Thread(target=lambda:peers.append(app_skills.shared_registry())) for _ in range(12)]
 for t in threads:t.start()
 for t in threads:t.join()
 assert len(peers)==12 and all(x is first for x in peers)
 engine=ReadOnlyEngine(lambda:{'name':'Blender'},lambda:{},lambda:None,LocalPerceptionTargetCache(),lambda _:None,lambda:None)
 assert engine._registry is first
 target.write_text(target.read_text().replace('"physicalKeys"','"changedDelivery"').replace('"label": "A"','"label": "Z"'))
 # File edit does not alter loaded HTTP or semantic policy objects.
 assert engine._registry.skill('Blender') is skill
 assert app_skills.normalize_semantic_keyboard_steps([{'type':'pressKey','label':'select all'}],'Blender')[0]['label']=='A'
 # Numeric policy is selected from the same cached skill; saved-range guard
 # stops before any native focus, key or OS action. Stubbing focus is forbidden.
 try:actions._skill_numeric_text({'type':'type','value':'2.5','_native_range':{'test':True}},'Blender')
 except Exception as e:assert 'saved native range' in str(e)
 else:raise AssertionError('numeric cached policy not selected')
 # Explicit registries stay independent; fresh process sees changed policy.
 assert app_skills.AppSkillRegistry().skill('Blender').should_type_physical_keys('2.5') is False
 code="from tiptour_linux.app_skills import shared_registry;assert not shared_registry().skill('Blender').should_type_physical_keys('2.5');print('new process reload pass')"
 p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True);assert p.returncode==0,p.stderr
 print('snapshot same object across 12 threads, engine, semantic review and numeric saved-range boundary; postinit file edit stable; explicit registry and fresh process reload: pass')
