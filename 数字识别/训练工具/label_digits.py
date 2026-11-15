# Auto-label digit cards: threshold dark digit on white paper, pick centered dark blob.
# Classes reviewed by eye; heavily rotated (>45 deg) shots are excluded from training.
import cv2
import numpy as np
import os
import math

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(SRC, "_verify")
os.makedirs(VERIFY, exist_ok=True)

# filename number -> class id; None = exclude (digit lying on its side, no valid shape)
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


def find_digit_box(img):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    # lower thresholds handle dark paper shadows merging everything into one blob
    for threshold in (110, 90, 70):
        mask = (gray < threshold).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_score = None, 0.0
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area = bw * bh / (w * h)
            if area < 0.003 or area > 0.20:
                continue
            dc = math.hypot((x + bw / 2 - w / 2) / w, (y + bh / 2 - h / 2) / h)
            score = math.sqrt(area) * math.exp(-(dc ** 2) / 0.08)
            if score > best_score:
                best_score, best = score, (x, y, bw, bh)
        if best is not None:
            break
    if best is None:
        return None
    x, y, bw, bh = best
    pad = int(0.10 * max(bw, bh))
    x0 = max(0, x - pad); y0 = max(0, y - pad)
    x1 = min(w, x + bw + pad); y1 = min(h, y + bh + pad)
    return x0, y0, x1 - x0, y1 - y0


kept, skipped, failed = [], [], []
tiles = []
for num, cls in sorted(LABELS.items()):
    matches = [f for f in os.listdir(SRC) if f.endswith(".jpg") and f"_{num}_" in f]
    if len(matches) != 1:
        print(f"WARN: number {num} matched {matches}")
        continue
    path = os.path.join(SRC, matches[0])
    img = imread_cn(path)
    if img is None:
        print(f"WARN: cannot read {matches[0]}")
        continue
    if cls is None:
        skipped.append(num)
        continue
    box = find_digit_box(img)
    if box is None:
        failed.append(num)
        tiles.append(cv2.resize(img, (270, 360)))
        continue
    h, w = img.shape[:2]
    x, y, bw, bh = box
    xc, yc = (x + bw / 2) / w, (y + bh / 2) / h
    kept.append((matches[0], cls, xc, yc, bw / w, bh / h))
    vis = img.copy()
    cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 0, 255), 4)
    cv2.putText(vis, str(cls), (x, max(30, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 4)
    tiles.append(cv2.resize(vis, (270, 360)))

# verification montages, 9 tiles each
for page in range(0, len(tiles), 9):
    group = tiles[page:page + 9]
    while len(group) < 9:
        group.append(np.zeros((360, 270, 3), np.uint8))
    montage = np.vstack([np.hstack(group[i:i + 3]) for i in range(0, 9, 3)])
    imwrite_cn(os.path.join(VERIFY, f"montage_{page // 9 + 1}.jpg"), montage)

with open(os.path.join(SRC, "labels.csv"), "w", encoding="utf-8") as f:
    for name, cls, xc, yc, nw, nh in kept:
        f.write(f"{name},{cls},{xc:.6f},{yc:.6f},{nw:.6f},{nh:.6f}\n")

print(f"kept {len(kept)}, excluded {len(skipped)} {skipped}, failed {len(failed)} {failed}")
