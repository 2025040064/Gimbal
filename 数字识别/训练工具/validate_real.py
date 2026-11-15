# Validate the trained model on real photos, simulating K230's 640x480 sensor feed.
# Real phone shots are huge; resizing them to 640x480 first is the only way the
# accuracy number means anything for the deployed pipeline.
import glob
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K230_W, K230_H = 640, 480
MODEL = os.path.join(ROOT, "runs", "digits_v8n", "weights", "best.pt")

# Same class mapping as label_digits.py; None means the card was lying on its side.
LABELS = {
    150: None, 151: None, 176: None, 177: 6, 178: 6, 179: 6,
    180: None, 181: None, 182: None, 183: 5, 184: 5, 185: 5, 186: 5,
    187: 4, 188: 4, 189: 4, 190: 4, 191: 4, 192: 4,
    193: 3, 194: 3, 195: None, 196: 3, 197: None,
    198: 2, 199: 2, 200: 2, 201: 2, 202: 2,
    203: 1, 204: 1, 205: None, 206: 1, 207: 1,
}


def imread_cn(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_cn(path, img):
    cv2.imencode(".jpg", img)[1].tofile(path)


def photo_index(path):
    """Extract the sequence number from the WeChat filename.

    Format: 微信图片_<timestamp>_<seq>_<batch>.jpg
    The last numeric token (_169) is the WeChat batch, not the sequence;
    the real index is the second-to-last numeric token.
    """
    name = os.path.basename(path)[:-4]  # strip ".jpg"
    parts = name.split("_")
    for part in reversed(parts[:-1]):  # skip trailing WeChat batch token
        if part.isdigit():
            return int(part)
    return -1


def fit_to_k230(img):
    """Letterbox to exactly 640x480, the way the sensor frames the scene."""
    h, w = img.shape[:2]
    scale = min(K230_W / w, K230_H / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((K230_H, K230_W, 3), 114, dtype=np.uint8)
    x0, y0 = (K230_W - nw) // 2, (K230_H - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = resized
    return canvas


def main():
    from ultralytics import YOLO

    if not os.path.isfile(MODEL):
        sys.exit("model not found: " + MODEL)
    model = YOLO(MODEL)

    photos = sorted(glob.glob(os.path.join(ROOT, "*.jpg")))
    tiles = []
    total = hit_top1 = hit_any = 0
    wrong_ids = []

    for path in photos:
        idx = photo_index(path)
        gt = LABELS.get(idx)
        if gt is None:
            continue
        img = fit_to_k230(imread_cn(path))
        result = model.predict(img, imgsz=320, conf=0.25, iou=0.45, verbose=False)[0]

        preds = []
        for box in result.boxes:
            cls = int(box.cls.item())
            conf = float(box.conf.item())
            xyxy = box.xyxy[0].tolist()
            preds.append((cls, conf, xyxy))
        preds.sort(key=lambda p: -p[1])

        total += 1
        if preds:
            hit_any += 1
        top1_ok = bool(preds) and preds[0][0] == gt
        hit_top1 += top1_ok
        if preds and not top1_ok:
            wrong_ids.append((os.path.basename(path), gt, preds[0][0], round(preds[0][1], 2)))

        # Visual check: green = correct top-1, red = wrong, grey = nothing found.
        vis = img.copy()
        for cls, conf, (x0, y0, x1, y1) in preds[:3]:
            color = (0, 200, 0) if cls == gt else (0, 0, 255)
            cv2.rectangle(vis, (int(x0), int(y0)), (int(x1), int(y1)), color, 2)
            cv2.putText(vis, f"{cls} {conf:.2f}", (int(x0), max(12, int(y0) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(vis, f"GT={gt}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        tiles.append(cv2.resize(vis, (320, 240)))

        status = "OK" if top1_ok else ("WRONG" if preds else "MISS")
        top = f"{preds[0][0]}:{preds[0][1]:.2f}" if preds else "-"
        print(f"{os.path.basename(path):40s} GT={gt} top1={top:10s} n={len(preds)} {status}")

    if tiles:
        cols = 4
        rows = []
        for i in range(0, len(tiles), cols):
            row = tiles[i:i + cols]
            while len(row) < cols:
                row.append(np.zeros((240, 320, 3), dtype=np.uint8))
            rows.append(np.hstack(row))
        imwrite_cn(os.path.join(ROOT, "_verify", "real_validate.jpg"), np.vstack(rows))

    print()
    print(f"images tested : {total}")
    print(f"top-1 correct : {hit_top1}/{total} = {hit_top1 / max(total, 1):.1%}")
    print(f"any detection : {hit_any}/{total} = {hit_any / max(total, 1):.1%}")
    if wrong_ids:
        print("wrong top-1:")
        for name, gt, pred, conf in wrong_ids:
            print(f"  {name}: GT={gt} pred={pred} conf={conf}")
    print(f"montage -> {os.path.join(ROOT, '_verify', 'real_validate.jpg')}")


if __name__ == "__main__":
    main()
