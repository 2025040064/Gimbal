# Build YOLO-format dataset from labels.csv (auto boxes verified via _verify/montages).
import csv
import os
import random
import shutil

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SRC, "digits_dataset")
VAL_PER_CLASS = 1
SEED = 42

rows = []
with open(os.path.join(SRC, "labels.csv"), encoding="utf-8") as f:
    for row in csv.reader(f):
        name, cls, xc, yc, nw, nh = row
        num = int(name.split("_")[2])
        rows.append((name, int(cls), num, float(xc), float(yc), float(nw), float(nh)))

by_class = {}
for r in rows:
    by_class.setdefault(r[1], []).append(r)

rng = random.Random(SEED)
val_rows = []
for cls, group in sorted(by_class.items()):
    group = sorted(group, key=lambda r: r[2])
    rng.shuffle(group)
    val_rows.extend(group[:VAL_PER_CLASS])

for split in ("train", "val"):
    for sub in ("images", "labels"):
        os.makedirs(os.path.join(OUT, sub, split), exist_ok=True)

counts = {"train": {}, "val": {}}
for name, cls, num, xc, yc, nw, nh in rows:
    split = "val" if (name, cls, num) in {(v[0], v[1], v[2]) for v in val_rows} else "train"
    stem = f"d{cls}_{num}"
    shutil.copyfile(os.path.join(SRC, name), os.path.join(OUT, "images", split, stem + ".jpg"))
    with open(os.path.join(OUT, "labels", split, stem + ".txt"), "w") as f:
        f.write(f"{cls} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}\n")
    counts[split][cls] = counts[split].get(cls, 0) + 1

yaml_text = (
    "path: .\n"
    "train: images/train\n"
    "val: images/val\n"
    "nc: 10\n"
    "names: ['0','1','2','3','4','5','6','7','8','9']\n"
)
with open(os.path.join(OUT, "digits.yaml"), "w", encoding="utf-8") as f:
    f.write(yaml_text)

print("train:", sum(counts["train"].values()), dict(sorted(counts["train"].items())))
print("val:  ", sum(counts["val"].values()), dict(sorted(counts["val"].items())))
print("missing classes:", [c for c in range(10) if c not in by_class])
