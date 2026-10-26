"""Linux runner for TipTour's own UIElementDetector (YOLO11m 'icon' detector, Ultralytics, AGPL-3.0).
Mirrors NativeElementDetector.swift: scaleFill to 640x640, conf>=0.25, NMS IoU 0.7.
Weights: converted from the repo's CoreML package by tools/mil_to_onnx.py (not retrained)."""
import numpy as np
from PIL import Image

class IconDetector:
    def __init__(self, onnx_path, conf=0.25, iou=0.7):
        import onnxruntime as ort
        self.s = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"]); self.conf = conf; self.iou = iou
    def detect(self, img: Image.Image):
        W, H = img.size
        a = np.asarray(img.convert("RGB").resize((640, 640), Image.BILINEAR), dtype=np.float32)  # scaleFill; graph itself multiplies by 1/255 (const image__scaled__)
        conf, xywh = self.s.run(None, {"image": a.transpose(2, 0, 1)[None]})
        conf = conf[:, 0]; keep = conf >= self.conf
        conf, xywh = conf[keep], xywh[keep]
        order = np.argsort(-conf); conf, xywh = conf[order], xywh[order]
        cx, cy, w, h = xywh.T; box = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
        sel = []
        for i in range(len(box)):
            ok = True
            for j in sel:
                ix = max(0, min(box[i, 2], box[j, 2]) - max(box[i, 0], box[j, 0])); iy = max(0, min(box[i, 3], box[j, 3]) - max(box[i, 1], box[j, 1]))
                inter = ix * iy; u = w[i] * h[i] + w[j] * h[j] - inter
                if u > 0 and inter / u > self.iou: ok = False; break
            if ok: sel.append(i)
        return [{"conf": float(conf[i]), "bbox": [float(box[i, 0] * W), float(box[i, 1] * H), float((box[i, 2] - box[i, 0]) * W), float((box[i, 3] - box[i, 1]) * H)],
                 "center": [float(cx[i] * W), float(cy[i] * H)], "source": "yolo"} for i in sel]
