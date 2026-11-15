# Measure how the off-the-shelf digit detector performs on our real printed cards.
import glob
import os

import cv2
import numpy as np
import onnxruntime as ort

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "pretrained", "yolov8_digits_hwd.onnx")
DATA = os.path.join(ROOT, "digits_dataset")

sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name


def detect(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    blob = cv2.cvtColor(cv2.resize(img, (256, 256)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    out = sess.run(None, {input_name: blob.transpose(2, 0, 1)[None]})[0][0]
    boxes, logits = out[:4].T, out[4:].T
    scores = logits if logits.max() <= 1.0001 else 1 / (1 + np.exp(-logits))
    conf, cls = scores.max(axis=1), scores.argmax(axis=1)
    keep = conf > 0.25
    boxes, conf, cls = boxes[keep], conf[keep], cls[keep]
    if len(boxes) == 0:
        return [], (h, w)
    # boxes from a 256x256 input: cx,cy,w,h -> xyxy in original pixels
    cx, cy, bw, bh = boxes.T
    xyxy = np.stack([(cx - bw / 2) * w / 256, (cy - bh / 2) * h / 256,
                     (cx + bw / 2) * w / 256, (cy + bh / 2) * h / 256], axis=1)
    idx = cv2.dnn.NMSBoxes(xyxy.tolist(), conf.tolist(), 0.25, 0.45)
    if len(idx) == 0:
        return [], (h, w)
    return [(int(cls[i]), float(conf[i]), xyxy[i].tolist()) for i in np.array(idx).flatten()], (h, w)


def iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0


total, detected, correct = 0, 0, 0
for img_path in sorted(glob.glob(os.path.join(DATA, "images", "*", "*.jpg"))):
    label_path = img_path.replace("images", "labels").replace(".jpg", ".txt")
    gt = []
    for line in open(label_path):
        c, xc, yc, bw, bh = map(float, line.split())
        gt.append((int(c), [ (xc-bw/2), (yc-bh/2), (xc+bw/2), (yc+bh/2) ]))
    preds, (h, w) = detect(img_path)
    total += 1
    if preds:
        detected += 1
    hit = False
    for cls, conf, box in preds:
        nb = [box[0] / w, box[1] / h, box[2] / w, box[3] / h]
        for gc, gb in gt:
            if cls == gc and iou(nb, gb) > 0.25:
                hit = True
    correct += hit
    pred_text = str([(p[0], round(p[1], 2)) for p in preds[:3]])
    print(f"{os.path.basename(img_path):14s} GT={[g[0] for g in gt]} pred={pred_text:35s} {'OK' if hit else 'MISS'}")
print(f"\ntotal={total} detected={detected} correct={correct} accuracy={correct/total:.1%}")
