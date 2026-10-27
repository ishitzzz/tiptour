"""Gemini-only Linux startup checks. Not full CompanionPanel onboarding.

Pinned CompanionPanelView/ProviderSetupView separate mode, key and permissions.
This surface checks Linux capabilities without collecting keys or granting access.
"""
import glob
import os
import shutil
import subprocess
import sys
import importlib.util
import threading


def readiness(env=None):
    env = dict(os.environ if env is None else env)
    checks = []
    x11 = bool(env.get('DISPLAY')) and env.get('XDG_SESSION_TYPE', 'x11').lower() != 'wayland'
    checks.append(('X11 desktop', x11, 'X11 is required. Wayland is not supported.'))
    from .keypool import configured_keys
    count = len(configured_keys(env.get('TIPTOUR_KEYS_GLOB', ''), env))
    checks.append(('Existing Gemini key configuration', count > 0, '%d nonempty configured entries; validity and quota not checked.' % count))
    checks.append(('X11 input tools', bool(shutil.which('xdotool')), 'xdotool must be installed.'))
    checks.append(('Local OCR', bool(shutil.which('tesseract')), 'Binary check only; not an accessibility permission.'))
    checks.append(('Accessibility support', importlib.util.find_spec('gi') is not None, 'GTK bindings found; AT-SPI app access remains unverified until use.'))
    return checks


def command(voice=False, act=False, out=None):
    args = [sys.executable, '-u', '-m', 'tiptour_linux.app', '--text-ui']
    if voice: args.append('--voice')
    if act: args.append('--act')
    if out: args += ['--out', out]
    return args


def initial_target_snapshot(read, timeout=.2):
    sampled = [None]
    def run(): sampled[0] = read()
    worker = threading.Thread(target=run, daemon=True); worker.start(); worker.join(timeout)
    return None if worker.is_alive() else sampled[0]


def main():
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GLib
    from .text_panel import window_id, target_identity
    original = initial_target_snapshot(lambda: target_identity(window_id()))
    w = Gtk.Window(title='TipTour Linux setup'); w.set_wmclass('tiptour-setup', 'TipTourSetup'); w.set_default_size(440, 380)
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18); w.add(b)
    for text in ['TipTour - Linux preview', 'Gemini uses the existing model and key configuration. JEV is not available in this Linux build.', 'Requests can send screenshots and text to Gemini. Every proposed action still needs local Confirm.', 'Target: the app focused before opening setup (X11 window %s). To change it, close setup, focus the app, and reopen.' % (original[0] if original else 'unavailable')]:
        label = Gtk.Label(label=text); label.set_line_wrap(True); label.set_xalign(0); b.pack_start(label, False, False, 0)
    status = Gtk.Label(label='Checking local setup...'); status.set_line_wrap(True); status.set_xalign(0); b.pack_start(status, False, False, 0)
    voice = Gtk.CheckButton(label='Enable existing voice input (Ctrl+Alt). Microphone and PulseAudio required.')
    voice.set_active(False)
    audio_tools = bool(shutil.which('parec') and shutil.which('paplay'))
    voice.set_sensitive(audio_tools)
    b.pack_start(voice, False, False, 0)
    act = Gtk.CheckButton(label='Allow actions after local proposal and Confirm (default is point only)')
    act.set_active(False); b.pack_start(act, False, False, 0)
    start = Gtk.Button(label='Start Gemini'); start.set_sensitive(False); b.pack_start(start, False, False, 0)
    result = []; closed = threading.Event()
    def activate(*_): result.extend(command(voice.get_active(), act.get_active(), os.environ.get("TIPTOUR_OUT"))); w.destroy()
    start.connect('clicked', activate)
    def finish(*_): closed.set(); Gtk.main_quit()
    w.connect('destroy', finish); w.show_all()
    def inspect():
        checks = readiness()
        # This is not a permission claim: opening the X display is only a local capability probe.
        d = None
        try:
            from Xlib import display
            d = display.Display(); d.screen().root.get_geometry(); available = True
        except Exception: available = False
        finally:
            if d: d.close()
        checks.append(('Voice tools (optional)', True, 'parec/paplay found; microphone capture not tested.' if audio_tools else 'Voice disabled: parec/paplay missing.'))
        checks.append(('X11 connection', available, 'Connected locally; capture and app accessibility can still fail at use.'))
        def apply():
            if closed.is_set(): return False
            status.set_text('\n'.join(('%s: %s. %s' % (name, 'found' if ok else 'missing', detail)) for name, ok, detail in checks))
            start.set_sensitive(original is not None and all(ok for _, ok, _ in checks)); return False
        GLib.idle_add(apply)
    threading.Thread(target=inspect, daemon=True).start(); Gtk.main()
    if result:
        if not original or target_identity(original[0]) != original:
            print('Launch refused: original target unavailable. Focus an app and reopen setup.'); return
        try:
            p = subprocess.run(['xdotool', 'windowactivate', '--sync', str(original[0])], timeout=2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if p.returncode or window_id() != original[0] or target_identity(original[0]) != original: return
        except (OSError, subprocess.TimeoutExpired): return
        os.execv(sys.executable, result)


if __name__ == '__main__': main()
