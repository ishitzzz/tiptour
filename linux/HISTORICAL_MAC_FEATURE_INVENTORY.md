# Mac feature inventory vs Linux port (source-backed, orientation only)
Basis: file headers and line counts under TipTour/ at the pinned commit 6e97782. "Impact" is what a user would notice on Linux. Status uses PARITY.md evidence classes; nothing here is a pass claim.
Verified-by-run items are only those named in PARITY.md (virtual audio / Xvfb, no physical hardware, X11 only).

| Mac area (lines) | Linux status | User impact |
|---|---|---|
| Voice/Gemini Live (2738) | ported: client, key pool, mic/PTT toggle, playback; virtual audio only | works end to end only in tests with virtual devices; speaker echo not handled |
| Perception: detector, OCR, AX resolver, browser resolver, continuity (2669) | ported in spirit: YOLO ONNX + OCR, AT-SPI, CDP DOM stage; target continuity cache and perceptual-hash not ported | pointing mostly matches; no cross-turn target memory across small UI shifts |
| Utilities: highlight (Ctrl+Shift), push-to-talk (Ctrl+Alt) shortcuts | ported on X11 polling | no Wayland; no global hotkeys under Wayland |
| Utilities: text-command shortcut and radial input switcher (Ctrl+Opt+Cmd) | NOT ported | no typed-question popup and no input-mode wheel; typed asks only via FIFO/CLI |
| Ask harness (2237) | ported except scribble (excluded by user) and on-device SFSpeech (Vosk instead) | works in virtual tests; transcription quality differs from Mac |
| UI: panel, menu bar, onboarding, provider setup, design system (6587) | NOT ported; tiny GTK settings window and untested tray only | no first-run setup, no provider UI; keys come from a vault glob / env |
| UI: overlay cursor, trail, Neko mode, detection overlay | cursor + trail ported; Neko sprites not wired (BSD-2 assets present in repo), detection overlay not ported | original blue cursor look only; no cat, no debug boxes |
| Actions: ActionExecutor, action driver (1243) | actions.py exists, never run live; --act off | no click/type automation; point-only |
| Workflow: plans, element resolver, runner, ClickDetector (2490) | NOT ported | no multi-step guided workflows, no auto-advance on user click |
| Core: engine, agent contract, modes (4280) | tracer-bullet equivalent only (app.py), single request loop | Mac mode switching (teaching/autopilot) absent |
| Tutorials + Elorian client (2512) | NOT ported | no tutorial-video tours; needs Elorian service access |
| Jev (761) | NOT ported | alternative grounding/pointer-loop provider unavailable |
| Harness server on local port (1128) | NOT ported | external orchestrators cannot drive TipTour via HTTP |
| Skills (markdown app skills, blender) | NOT ported | no per-app skill hints |
| Analytics, keychain | not ported (keychain replaced by vault files) | none intended |

Largest user-visible gaps for a "same TipTour": workflows/teaching mode, text-command and radial input, onboarding/menu panel, actions. These are large (each hundreds to thousands of Swift lines) and need a scoping decision, not an open queue.
Hard limits independent of code: no physical mic/speakers/keyboard here, X11/XWayland only, no Wayland, no Windows, no tray host.
