"""Linux-side dump in the same JSON shape as mac-reference/dump_detector.swift."""
import sys, json; sys.path.insert(0, "linux")
from PIL import Image
from tiptour_linux.detector import IconDetector
im = Image.open(sys.argv[2]); r = IconDetector(sys.argv[1]).detect(im)
print(json.dumps({"image": sys.argv[2], "width": im.width, "height": im.height, "detections": [{"conf": e["conf"], "x": e["bbox"][0], "y": e["bbox"][1], "w": e["bbox"][2], "h": e["bbox"][3]} for e in r]}, indent=1))
