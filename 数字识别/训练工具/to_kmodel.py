# ONNX -> K230 kmodel, following Canaan CanMV K230 AI dev doc (nncase 2.x API).
# Run with the Python 3.10 venv that has nncase==2.9.0 + nncase_kpu==2.9.0.
import argparse
import glob
import os

import numpy as np
from PIL import Image
import nncase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def calibration_data(calib_dir, shape, count):
    files = [p for p in sorted(glob.glob(os.path.join(calib_dir, "*.jpg")))]
    if len(files) < count:
        raise ValueError(f"need {count} calibration images, found {len(files)} in {calib_dir}")
    _, _, h, w = shape
    data = []
    for path in files[:count]:
        img = Image.open(path).convert("RGB").resize((w, h), Image.Resampling.BILINEAR)
        arr = np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)[np.newaxis, ...]
        data.append([arr])
    return np.array(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="ONNX model path")
    ap.add_argument("--dataset", default=os.path.join(ROOT, "digits_dataset_v2", "images", "train"))
    ap.add_argument("--size", type=int, default=320)
    ap.add_argument("--samples", type=int, default=100)
    ap.add_argument("--target", default="k230")
    args = ap.parse_args()

    shape = [1, 3, args.size, args.size]
    opts = nncase.CompileOptions()
    opts.target = args.target
    opts.preprocess = True
    opts.swapRB = False
    opts.input_shape = shape
    opts.input_type = "uint8"
    opts.input_range = [0, 1]
    opts.mean = [0, 0, 0]
    opts.std = [1, 1, 1]
    opts.input_layout = "NCHW"

    compiler = nncase.Compiler(opts)
    with open(args.model, "rb") as f:
        compiler.import_onnx(f.read(), nncase.ImportOptions())

    ptq = nncase.PTQTensorOptions()
    ptq.samples_count = args.samples
    ptq.calibrate_method = "NoClip"
    ptq.quant_type = "uint8"
    ptq.w_quant_type = "uint8"
    ptq.set_tensor_data(calibration_data(args.dataset, shape, args.samples))
    compiler.use_ptq(ptq)
    compiler.compile()

    out = os.path.splitext(args.model)[0] + ".kmodel"
    with open(out, "wb") as f:
        f.write(compiler.gencode_tobytes())
    print("kmodel saved:", out)


if __name__ == "__main__":
    main()
