"""REAL X11 (Xvfb+xfwm4, xclip, xdotool, owned GTK entry): clipboard preservation + negative insert cases. Run by run_ask_insert_neg.sh."""
import sys, os, io, time, subprocess; sys.path.insert(0, ".")
from tiptour_linux import ask
from PIL import Image
OUT = os.environ["OUT"]; wid = open(OUT + "/target_wid.txt").read().strip(); res = []
def rec(name, ok, detail): res.append((name, ok, detail)); print(("PASS " if ok else "FAIL ") + name + ": " + detail, flush=True)
def entry(): time.sleep(0.6); return open(os.environ["ENTRY_DUMP"]).read()
def clear_entry(): subprocess.run(["xdotool", "windowactivate", "--sync", wid]); subprocess.run(["xdotool", "key", "ctrl+a", "BackSpace"]); time.sleep(.5)
def png(): b = io.BytesIO(); Image.new("RGB", (8, 8), (200, 30, 30)).save(b, "PNG"); return b.getvalue()
def set_clip(data, mime): ask.Clipboard._write(data, mime)
# 1 previous image restored
clear_entry(); P = png(); set_clip(P, "image/png"); c = ask.Clipboard(); r = ask.insert_draft(c, "draft one", wid)
rec("prev-image", "draft one" in entry() and ask.Clipboard._read("image/png") == P and "restored previous image/png" in r, r)
# 2 previous text restored
clear_entry(); set_clip(b"my earlier text", "UTF8_STRING"); r = ask.insert_draft(ask.Clipboard(), "draft two", wid)
rec("prev-text", "draft two" in entry() and ask.Clipboard._read() == b"my earlier text", r)
# 3 changed by others between paste and restore: wrap xdotool paste
clear_entry(); set_clip(b"before", "UTF8_STRING"); real_run = subprocess.run
def hooked(cmd, *a, **k):
    out = real_run(cmd, *a, **k)
    if cmd[:2] == ["xdotool", "key"] and "ctrl+v" in cmd: time.sleep(0.5); ask.Clipboard._write(b"user copied this during paste", "UTF8_STRING")
    return out
subprocess.run = hooked; r = ask.insert_draft(ask.Clipboard(), "draft three", wid); subprocess.run = real_run
rec("changed-during-paste", ask.Clipboard._read() == b"user copied this during paste" and "changed by others" in r, r)
# 4 changed after stage, before paste -> refuse, no paste
clear_entry(); set_clip(b"before4", "UTF8_STRING"); orig = ask.Clipboard.stage
def stage_then_steal(self, payload, mime): orig(self, payload, mime); ask.Clipboard._write(b"stolen", "UTF8_STRING")
ask.Clipboard.stage = stage_then_steal; r = ask.insert_draft(ask.Clipboard(), "draft four", wid); ask.Clipboard.stage = orig
rec("changed-before-paste", "draft four" not in entry() and r.startswith("refused") and ask.Clipboard._read() == b"stolen", r)
# 5 target window gone
subprocess.run(["xdotool", "key", "ctrl+a", "BackSpace"]); gone = "99999999"; r = ask.insert_draft(ask.Clipboard(), "draft five", gone)
rec("target-gone", r.startswith("refused") and "draft five" not in entry(), r)
# 6 multi-format previous: reported partial
clear_entry(); p = subprocess.Popen(["xclip", "-selection", "clipboard", "-t", "image/png", "-i"], stdin=subprocess.PIPE); p.stdin.write(P); p.stdin.close(); time.sleep(.2)
r = ask.insert_draft(ask.Clipboard(), "draft six", wid); rec("prev-single-format-image-again", "draft six" in entry(), r)
# 7 empty previous
subprocess.run(["xdotool", "key", "ctrl+a", "BackSpace"]); c = ask.Clipboard(); c.stage(b"x", "UTF8_STRING"); c.prev = {}; r = c.restore(); rec("prev-empty", "empty" in r, r)
# 8 copied earlier (owned), user copies something between preview and Insert -> clean refusal string, no paste, no exception; next insert recovers
clear_entry(); c = ask.Clipboard(); c.stage(b"copied text", "UTF8_STRING"); ask.Clipboard._write(b"user copy in between", "UTF8_STRING")
r = ask.insert_draft(c, "draft eight", wid); rec("changed-between-preview-and-insert", r.startswith("refused") and "draft eight" not in entry() and ask.Clipboard._read() == b"user copy in between", r)
r = ask.insert_draft(c, "draft nine", wid); rec("retry-after-refusal", "draft nine" in entry(), r)
# 9 multi-format previous clipboard (html + text, held by a GTK owner): refuse BEFORE overwriting, do not paste
clear_entry(); h = subprocess.Popen([sys.executable, "tests/clip_multi_holder.py"]); time.sleep(1.5)
before = ask.Clipboard._read("text/html"); r = ask.insert_draft(ask.Clipboard(), "draft multi", wid)
rec("multi-format-refused-before-overwrite", before == b"<b>rich</b>" and r.startswith("refused") and "draft multi" not in entry() and ask.Clipboard._read("text/html") == b"<b>rich</b>", r)
h.terminate(); time.sleep(.5)
print("SUMMARY", sum(1 for x in res if x[1]), "/", len(res))
