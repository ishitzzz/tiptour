# Generates synthetic test speech with the Gemini TTS REST API (free-tier vault key via glob; never printed). usage: tts_gemini.py "text" out.wav
import sys, json, glob, base64, urllib.request, wave
key = open(sorted(glob.glob('/home/sandbox/.vault/gemini-*/password'))[0]).read().strip()
text, out = sys.argv[1], sys.argv[2]
body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}}}
req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
try:
    r = json.load(urllib.request.urlopen(req, timeout=60))
    pcm = base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    w = wave.open(out, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close(); print("ok", len(pcm))
except Exception as e:
    print("ERR", type(e).__name__, str(getattr(e, "code", ""))[:20]); 
    try: print(e.read().decode()[:300].replace(key, "***"))
    except Exception: pass
