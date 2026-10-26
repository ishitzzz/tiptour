import os,time,json,subprocess
from pathlib import Path
D=Path(os.environ['RUN_DIR']);fifo=D/'fifo';mode=os.environ.get('MODE','type')
def log(s):(D/'driver_events.txt').open('a').write(str(time.time())+' '+s+'\n')
def send(s):
 with fifo.open('w') as f:f.write(s+'\n')
 log('sent '+s)
def waitfor(s,timeout=25):
 end=time.time()+timeout
 while time.time()<end:
  if (D/'stdout.txt').exists() and s in (D/'stdout.txt').read_text(errors='replace'):return
  time.sleep(.1)
 raise RuntimeError('timeout waiting '+s)
end=time.time()+25
while not fifo.exists() and time.time()<end: time.sleep(.1)
time.sleep(1)
if mode=='stop': request='point go: scroll down';typ='scroll'
elif mode=='setValue':request='point go: set the value to replaced';typ='setValue'
else:request='point go: type hello world';typ='type'
send(request);waitfor('proposal rev 1 displayed');time.sleep(.2);send('yes')
if mode=='stop':
 waitfor('TEST real key dispatched');send('stop');time.sleep(2)
else:waitfor('action executed');time.sleep(.5)
subprocess.run(['ffmpeg','-loglevel','error','-y','-f','x11grab','-video_size','1280x800','-i',os.environ['DISPLAY'],'-frames:v','1',str(D/'final.png')],timeout=10)
send('@quit')
