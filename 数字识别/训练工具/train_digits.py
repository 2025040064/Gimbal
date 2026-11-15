from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".ultralytics"))


def main():
    import torch
    from ultralytics import YOLO

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; refusing to silently train on CPU")

    print("GPU:", torch.cuda.get_device_name(0), flush=True)
    model = YOLO(str(ROOT / "yolov8n.pt"))
    model.train(
        data=str(ROOT / "digits_train.yaml"),
        project=str(ROOT / "runs"),
        name="digits_yolov8n_320",
        exist_ok=False,
        epochs=80,
        patience=20,
        imgsz=320,
        batch=16,
        device=0,
        workers=0,
        fliplr=0.0,
        flipud=0.0,
        seed=20261113,
    )


if __name__ == "__main__":
    main()
