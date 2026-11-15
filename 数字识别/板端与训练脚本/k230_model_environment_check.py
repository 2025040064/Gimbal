"""Read-only K230 environment check; run from CanMV IDE, not as main.py."""

import os
import sys

MODEL = "/sdcard/examples/kmodel/best_calibrated_50.kmodel"
YOLO_LIB = "/sdcard/libs/YOLO.py"
EXAMPLE = "/sdcard/examples/20-YOLO-Module-Examples/yolov8_det_video.py"


def print_file(path, class_only=False):
    print("\n[FILE]", path)
    try:
        with open(path, "r") as source:
            copying = not class_only
            found = False
            for line in source:
                if class_only and line.startswith("class YOLOv8"):
                    copying = True
                    found = True
                elif class_only and copying and line.startswith("class "):
                    break
                if copying:
                    print(line.rstrip())
            if class_only and not found:
                print("[WARN] class YOLOv8 not found")
    except Exception as error:
        print("[ERROR] cannot read {}: {}".format(path, error))


def main():
    print("[CHECK] K230 YOLO environment")
    print("[INFO] Python:", sys.version)
    try:
        print("[INFO] Firmware:", os.uname())
    except Exception as error:
        print("[WARN] uname:", error)
    try:
        info = os.stat(MODEL)
        print("[OK] MODEL_FOUND size={} path={}".format(info[6], MODEL))
    except Exception as error:
        print("[ERROR] MODEL_NOT_FOUND", MODEL, error)
    print_file(EXAMPLE)
    print_file(YOLO_LIB, class_only=True)
    print("\n[CHECK] DONE")


if __name__ == "__main__":
    main()
