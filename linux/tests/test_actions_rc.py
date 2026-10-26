"""Self-contained xdotool shims, no display/model: checked failures before/after a partial click."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tiptour_linux import actions as a
d=Path(tempfile.mkdtemp());p=d/'xdotool'
def shim(body):p.write_text('#!/bin/sh\n'+body);p.chmod(0o755);os.environ['PATH']=str(d)+':/usr/bin:/bin'
shim('exit 0\n');assert a.execute({'type':'click'},(1,2))['ok'];assert a.execute({'type':'doubleClick'},(1,2))['ok']
shim('echo boom >&2;exit 1\n');r=a.execute({'type':'click'},(1,2));assert not r['ok'] and 'rc=1' in r['error']
shim('if [ "$1" = click ]; then echo boom >&2;exit 1;fi\nexit 0\n');r=a.execute({'type':'click'},(1,2));assert not r['ok'] and 'click' in r['error']
os.environ['PATH']='/nonexistent';r=a.execute({'type':'click'},(1,2));assert not r['ok'] and 'unavailable' in r['error']
print('PASS checked click dispatch success/failure/second-call failure/missing binary (simulated shims)')
