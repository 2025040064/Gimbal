# Synthesize printed white-card / black-digit images with YOLO boxes.
# Simulates the gimbal camera: paper perspective, distance, lighting, blur, background.
import argparse
import os
import random
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "synth_data")
W, H = 640, 480
FONT_FILES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/times.ttf",
]


@lru_cache(maxsize=None)
def base_font(path):
    return ImageFont.truetype(path, 100)


def background(rng):
    """Neutral desk/floor/wall tones: low saturation, no artificial colours."""
    base = rng.randint(155, 218)
    grad = np.linspace(base + rng.randint(-18, 18), base + rng.randint(-18, 18), W, dtype=np.float32)
    flat = np.random.uniform(-12, 12, (6, 8)).astype(np.float32)
    noise = cv2.resize(flat, (W, H), interpolation=cv2.INTER_CUBIC)
    tint = rng.choice([(1.0, 1.0, 1.0), (1.03, 1.0, 0.96), (0.97, 1.0, 1.03), (1.02, 0.99, 0.95)])
    img = np.stack([np.tile(grad[None, :], (H, 1)) * t + noise for t in tint], axis=-1)
    return np.clip(img, 0, 255).astype(np.uint8)


def paper_layer(rng):
    """Return RGBA paper with a white rounded-ish rectangle and soft shadow."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pw, ph = rng.randint(int(W * 0.45), int(W * 0.95)), rng.randint(int(H * 0.5), int(H * 0.95))
    x0, y0 = (W - pw) // 2 + rng.randint(-40, 40), (H - ph) // 2 + rng.randint(-30, 30)
    shade = rng.randint(215, 252)
    d.rectangle([x0 + 8, y0 + 10, x0 + pw + 8, y0 + ph + 10], fill=(60, 60, 60, 90))
    d.rectangle([x0, y0, x0 + pw, y0 + ph], fill=(shade, shade, shade, 255))
    return layer, (x0, y0, pw, ph)


def digit_patch(rng, digit, max_size):
    size = rng.randint(60, max(61, min(250, max_size)))
    font = base_font(rng.choice(FONT_FILES)).font_variant(size=size)
    patch = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(patch)
    ink = rng.randint(10, 55)
    d.text((size // 2, size // 3), digit, font=font, fill=(ink, ink, ink, 255))
    box = patch.getbbox()
    if box is None:
        return None
    patch = patch.crop(box)
    angle = rng.uniform(-15, 15)
    patch = patch.rotate(angle, expand=True, resample=Image.BICUBIC)
    alpha = np.array(patch.split()[-1])
    ys, xs = np.nonzero(alpha > 30)
    if len(xs) < 20:
        return None
    return patch, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def place_digits(rng, layer, paper_rect):
    """Paste 1-3 digits on the paper, return boxes in canvas coordinates."""
    x0, y0, pw, ph = paper_rect
    boxes = []
    for _ in range(rng.choice([1, 1, 1, 2, 2, 3])):
        digit = str(rng.randint(0, 9))
        made = digit_patch(rng, digit, int(min(pw, ph) * 0.72))
        if made is None:
            continue
        patch, (bx0, by0, bx1, by1) = made
        if patch.width > pw * 0.85 or patch.height > ph * 0.85:
            continue
        for _ in range(30):
            px = rng.randint(x0 + 22, max(x0 + 23, x0 + pw - patch.width - 22))
            py = rng.randint(y0 + 22, max(y0 + 23, y0 + ph - patch.height - 22))
            box = (px + bx0, py + by0, px + bx1, py + by1)
            clear = True
            for _, b in boxes:
                if (max(0, min(box[2] + 8, b[2]) - max(box[0] - 8, b[0])) *
                        max(0, min(box[3] + 8, b[3]) - max(box[1] - 8, b[1]))) > 0:
                    clear = False
                    break
            if clear:
                break
        else:
            continue
        layer.alpha_composite(patch, (px, py))
        boxes.append((digit, box))
    return boxes


def warp(rng, img, boxes):
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[rng.randint(0, 35), rng.randint(0, 35)],
                      [W - rng.randint(0, 35), rng.randint(0, 35)],
                      [W - rng.randint(0, 35), H - rng.randint(0, 35)],
                      [rng.randint(0, 35), H - rng.randint(0, 35)]])
    m = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, m, (W, H), borderValue=(190, 190, 190))
    warped = []
    for digit, (x0, y0, x1, y1) in boxes:
        pts = np.float32([[[x0, y0]], [[x1, y0]], [[x1, y1]], [[x0, y1]]])
        t = cv2.perspectiveTransform(pts, m).reshape(-1, 2)
        nx0, ny0 = np.clip([t[:, 0].min(), t[:, 1].min()], 0, [W, H])
        nx1, ny1 = np.clip([t[:, 0].max(), t[:, 1].max()], 0, [W, H])
        if nx1 - nx0 >= 10 and ny1 - ny0 >= 10:
            warped.append((digit, (nx0, ny0, nx1, ny1)))
    return out, warped


def photometric(rng, img):
    f = img.astype(np.float32)
    light = np.linspace(rng.uniform(0.80, 1.0), rng.uniform(0.9, 1.15), W, dtype=np.float32)
    f *= np.tile(light[None, :, None], (H, 1, 1)) * rng.uniform(0.92, 1.08)
    if rng.random() < 0.35:
        k = rng.randint(3, 9)
        kernel = np.zeros((k, k), np.float32)
        kernel[k // 2, :] = 1 if rng.random() < 0.5 else 0
        if kernel.sum() == 0:
            kernel[:, k // 2] = 1
        f = cv2.filter2D(f, -1, kernel / kernel.sum())
    if rng.random() < 0.25:
        f = cv2.GaussianBlur(f, (0, 0), rng.uniform(0.6, 1.8))
    f += np.random.normal(0, rng.uniform(1.5, 6.0), f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


def sample(rng):
    bg = Image.fromarray(background(rng)).convert("RGBA")
    paper, rect = paper_layer(rng)
    boxes = place_digits(rng, paper, rect)
    if not boxes:
        return None
    bg.alpha_composite(paper)
    img, boxes = warp(rng, cv2.cvtColor(np.array(bg), cv2.COLOR_RGBA2BGR), boxes)
    if not boxes:
        return None
    img = photometric(rng, img)
    lines = []
    for digit, (x0, y0, x1, y1) in boxes:
        xc, yc = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
        bw, bh = (x1 - x0) / W, (y1 - y0) / H
        lines.append(f"{digit} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return img, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=20261113)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    np.random.seed(args.seed)
    for sub in ("images", "labels"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    made = 0
    for i in range(args.count):
        result = sample(rng)
        if result is None:
            continue
        img, lines = result
        stem = f"s{made:05d}"
        cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])[1].tofile(
            os.path.join(OUT, "images", stem + ".jpg"))
        with open(os.path.join(OUT, "labels", stem + ".txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        made += 1
    print(f"generated {made} samples in {OUT}")


if __name__ == "__main__":
    main()
