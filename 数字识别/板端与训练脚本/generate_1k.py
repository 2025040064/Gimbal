# 生成"0-9 一共 1000 张"的均衡数据集（每类 100 张 train + 10 张 val）。
# 复用原 synthesize_digits.py 的合成风格（白底黑字印刷体 + 透视/光度扰动），
# 但每张图只放一个指定数字，保证每类严格均衡。
# 输出：digits_dataset_1k/{images,labels}/{train,val} + digits_1k.yaml
import os, random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "digits_dataset_1k")
W, H = 640, 480

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/simhei.ttf",
]

def load_fonts():
    fonts = []
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                ImageFont.truetype(p, 100)
                fonts.append(p)
            except Exception:
                pass
    if not fonts:
        fonts.append(None)  # PIL 默认字体兜底
    return fonts

FONTS = load_fonts()

def background(rng):
    base = rng.randint(155, 218)
    grad = np.linspace(base + rng.randint(-18, 18), base + rng.randint(-18, 18), W, dtype=np.float32)
    flat = np.random.uniform(-12, 12, (6, 8)).astype(np.float32)
    noise = cv2.resize(flat, (W, H), interpolation=cv2.INTER_CUBIC)
    tint = rng.choice([(1.0, 1.0, 1.0), (1.03, 1.0, 0.96), (0.97, 1.0, 1.03), (1.02, 0.99, 0.95)])
    img = np.stack([np.tile(grad[None, :], (H, 1)) * t + noise for t in tint], axis=-1)
    return np.clip(img, 0, 255).astype(np.uint8)

def paper_layer(rng):
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
    fp = rng.choice(FONTS)
    font = ImageFont.truetype(fp, size) if fp else ImageFont.load_default()
    patch = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(patch)
    ink = rng.randint(10, 55)
    d.text((size // 2, size // 3), str(digit), font=font, fill=(ink, ink, ink, 255))
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

def single_sample(rng, digit):
    bg = Image.fromarray(background(rng)).convert("RGBA")
    paper, rect = paper_layer(rng)
    made = digit_patch(rng, digit, int(min(rect[2], rect[3]) * 0.72))
    if made is None:
        return None
    patch, (bx0, by0, bx1, by1) = made
    if patch.width > rect[2] * 0.85 or patch.height > rect[3] * 0.85:
        return None
    px = rng.randint(rect[0] + 22, max(rect[0] + 23, rect[0] + rect[2] - patch.width - 22))
    py = rng.randint(rect[1] + 22, max(rect[1] + 23, rect[1] + rect[3] - patch.height - 22))
    paper.alpha_composite(patch, (px, py))
    box = (px + bx0, py + by0, px + bx1, py + by1)
    bg.alpha_composite(paper)
    img, boxes = warp(rng, cv2.cvtColor(np.array(bg), cv2.COLOR_RGBA2BGR), [(str(digit), box)])
    if not boxes:
        return None
    img = photometric(rng, img)
    x0, y0, x1, y1 = boxes[0][1]
    xc, yc = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
    bw, bh = (x1 - x0) / W, (y1 - y0) / H
    line = f"{digit} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}"
    return img, line

def make_split(split, per_class):
    img_dir = os.path.join(OUT, "images", split)
    lab_dir = os.path.join(OUT, "labels", split)
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lab_dir, exist_ok=True)
    made = {d: 0 for d in range(10)}
    for d in range(10):
        while made[d] < per_class:
            i = made[d]
            seed = abs(hash((split, d, i))) % (2**31)
            rng = random.Random(seed)
            np.random.seed(seed & 0xFFFF)
            res = single_sample(rng, d)
            if res is None:
                continue
            img, line = res
            stem = f"{split[0]}{d}_{i:04d}"
            cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])[1].tofile(
                os.path.join(img_dir, stem + ".jpg"))
            with open(os.path.join(lab_dir, stem + ".txt"), "w") as f:
                f.write(line + "\n")
            made[d] += 1
    return made

def write_yaml():
    yaml_path = os.path.join(ROOT, "digits_1k.yaml")
    content = (
        "# 0-9 一共 1000 张训练图（每类 100）+ 100 张验证图（每类 10）\n"
        f"path: {OUT}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 10\n"
        "names: ['0','1','2','3','4','5','6','7','8','9']\n"
    )
    with open(yaml_path, "w") as f:
        f.write(content)
    return yaml_path

if __name__ == "__main__":
    print("fonts:", FONTS)
    train_made = make_split("train", 100)
    val_made = make_split("val", 10)
    yaml_path = write_yaml()
    total_train = sum(train_made.values())
    total_val = sum(val_made.values())
    print("train per class:", train_made, "-> total", total_train)
    print("val   per class:", val_made, "-> total", total_val)
    print("yaml:", yaml_path)
