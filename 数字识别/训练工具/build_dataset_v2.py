# Merge synthetic images with real photos into the final YOLO dataset.
# Real photos are augmented photometrically only (geometry/labels stay valid).
import glob
import os
import random
import shutil

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNTH = os.path.join(ROOT, "synth_data")
REAL = os.path.join(ROOT, "digits_dataset")
OUT = os.path.join(ROOT, "digits_dataset_v2")
SYNTH_VAL = 600
REAL_COPIES = 6
rng = random.Random(20261113)
np.random.seed(20261113)

for split in ("train", "val"):
    for sub in ("images", "labels"):
        os.makedirs(os.path.join(OUT, sub, split), exist_ok=True)


def write(stem, split, img, lines):
    cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tofile(
        os.path.join(OUT, "images", split, stem + ".jpg"))
    with open(os.path.join(OUT, "labels", split, stem + ".txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def augment(img):
    f = img.astype(np.float32) * rng.uniform(0.80, 1.20) + rng.uniform(-12, 12)
    if rng.random() < 0.5:
        f = cv2.GaussianBlur(f, (0, 0), rng.uniform(0.5, 1.6))
    f += np.random.normal(0, rng.uniform(1, 5), f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


synth_imgs = sorted(glob.glob(os.path.join(SYNTH, "images", "*.jpg")))
rng.shuffle(synth_imgs)
for i, path in enumerate(synth_imgs):
    stem = os.path.basename(path)[:-4]
    lines = open(os.path.join(SYNTH, "labels", stem + ".txt")).read().strip().splitlines()
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    write(stem, "val" if i < SYNTH_VAL else "train", img, lines)

for split in ("train", "val"):
    for path in sorted(glob.glob(os.path.join(REAL, "images", split, "*.jpg"))):
        stem = os.path.basename(path)[:-4]
        lines = open(os.path.join(REAL, "labels", split, stem + ".txt")).read().strip().splitlines()
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        write("r" + stem, "val", img, lines)
        if split == "train":
            for k in range(REAL_COPIES - 1):
                write(f"r{stem}_v{k}", "train", augment(img), lines)

with open(os.path.join(OUT, "digits.yaml"), "w", encoding="utf-8") as f:
    f.write("path: .\ntrain: images/train\nval: images/val\n"
            "nc: 10\nnames: ['0','1','2','3','4','5','6','7','8','9']\n")

for split in ("train", "val"):
    counts = {}
    for lab in glob.glob(os.path.join(OUT, "labels", split, "*.txt")):
        for line in open(lab):
            c = int(line.split()[0])
            counts[c] = counts.get(c, 0) + 1
    imgs = len(glob.glob(os.path.join(OUT, "images", split, "*.jpg")))
    print(split, imgs, "images,", sum(counts.values()), "boxes", dict(sorted(counts.items())))
print("dataset at", OUT)
