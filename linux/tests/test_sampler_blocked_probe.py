import os,sys,time,threading,queue,subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tiptour_linux import highlight as H
ticks=[]
mon=H.HighlightMonitor(on_move=lambda p:ticks.append(time.time()),on_commit=lambda pts,c:q.put(pts))
q=queue.Queue(); done=[]
def worker():
    pts=q.get(); t=time.time()
    ctx=H.build_context(pts,lambda p:{"rect":(0,0,10,10),"title":"x","pid":1},lambda *a,**k:time.sleep(12),probe_timeout=6)
    done.append((time.time()-t,ctx.get("atspi_status")))
threading.Thread(target=worker,daemon=True).start()
mon.start()
def drive():
    subprocess.run(["xdotool","keydown","ctrl","keydown","shift"])
    for i in range(60):
        subprocess.run(["xdotool","mousemove",str(300+i*5),str(300+(i%7)*9)]); time.sleep(0.05)
    subprocess.run(["xdotool","keyup","shift","keyup","ctrl"])
threading.Thread(target=drive).start()
time.sleep(14)
g=[b-a for a,b in zip(ticks,ticks[1:])]
print("moves",len(ticks),"maxgap %.3f"%max(g) if g else None,"commit",done)
# post-commit sampler still alive?
ticks.clear(); subprocess.run(["xdotool","keydown","ctrl","keydown","shift"]);
for i in range(20): subprocess.run(["xdotool","mousemove",str(800+i*8),"500"]); time.sleep(0.03)
subprocess.run(["xdotool","keyup","shift","keyup","ctrl"]); print("moves after (sampler alive while worker maybe blocked):",len(ticks))
