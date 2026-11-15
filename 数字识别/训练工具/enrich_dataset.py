# Enrich digits_dataset_v2 train split by +N images (synthetic + real variants).
# Synthetic: generated via synthesize_digits.sample() (white card / black digit 0-9,
#   perspective warp + photometric noise), novel seed so they differ from v1.
# Real variants: photometric-only augmentation of the 25 labeled real photos
#   (brightness / blur / noise). Labels stay valid (no geometry change).
# Writes into digits_dataset_v2/images/train + labels/train with unique stems
# (e* = synthetic, rv* = real variant) so nothing existing is overwritten.
import glob
import os
import random

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "digits_dataset_v2")
REAL = os.path.join(ROOT, "digits_dataset")
SYNTH_COUNT = 800
REAL_VARIANTS = 200
SEED = 20261114

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synthesize_digits import sample as synth_sample  # noqa: E402


def augment(img, rng):
    f = img.astype(np.float32) * rng.uniform(0.80, 1.20) + rng.uniform(-12, 12)
    if rng.random() < 0.5:
        f = cv2.GaussianBlur(f, (0, 0), rng.uniform(0.5, 1.6))
    f += np.random.normal(0, rng.uniform(1, 5), f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


def write(stem, img, lines):
    cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tofile(
        os.path.join(OUT, "images", "train", stem + ".jpg"))
    with open(os.path.join(OUT, "labels", "train", stem + ".txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    rng = random.Random(SEED)
    np.random.seed(SEED)

    real_paths = sorted(glob.glob(os.path.join(REAL, "images", "train", "*.jpg")) +
                        glob.glob(os.path.join(REAL, "images", "val", "*.jpg")))

    def label_path(stem):
        p = os.path.join(REAL, "labels", "train", stem + ".txt")
        if not os.path.exists(p):
            p = os.path.join(REAL, "labels", "val", stem + ".txt")
        return p

    # --- synthetic ---
    s = 0
    for _ in range(SYNTH_COUNT):
        res = synth_sample(rng)
        if res is None:
            continue
        img, lines = res
        write(f"e{s:05d}", img, lines)
        s += 1
    synth_made = s

    # --- real photometric variants ---
    r = 0
    k = 0
    while r < REAL_VARIANTS and real_paths:
        path = real_paths[k % len(real_paths)]
        k += 1
        stem = os.path.basename(path)[:-4]
        lp = label_path(stem)
        if not os.path.exists(lp):
            continue
        lines = open(lp).read().strip().splitlines()
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None or not lines:
            continue
        write(f"rv{r:05d}", augment(img, rng), lines)
        r += 1
    real_made = r

    print(f"added synthetic={synth_made} real_variants={real_made} total={synth_made + real_made}")

    # --- stats ---
    counts = {}
    for lab in glob.glob(os.path.join(OUT, "labels", "train", "*.txt")):
        for line in open(lab):
            parts = line.split()
            if not parts:
                continue
            counts[int(parts[0])] = counts.get(int(parts[0]), 0) + 1
    imgs = len(glob.glob(os.path.join(OUT, "images", "train", "*.jpg")))
    print("train images:", imgs)
    print("train boxes by class:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
