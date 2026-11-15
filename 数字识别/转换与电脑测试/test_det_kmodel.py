import os
import sys
import traceback
import argparse

print(
    "[1] Starting script: {}".format(os.path.abspath(__file__)),
    flush=True
)
print(
    "[2] Python: {}".format(sys.executable),
    flush=True
)

import cv2
print("[3] cv2 imported", flush=True)

import numpy as np
print("[4] numpy imported", flush=True)

import nncase
print("[5] nncase imported", flush=True)


# 如果你的文件不在以下位置，请修改这两个路径。
MODEL_PATH = r"E:\yolo\best.kmodel"
IMAGE_PATH = r"E:\yolo\test_yolov8\calibration_data\t0_0000.jpg"

# 结果图片保存在本脚本所在目录。
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "kmodel_det_result.jpg"
)

INPUT_WIDTH = 320
INPUT_HEIGHT = 320

CLASS_NAMES = [
    "0", "1", "2", "3", "4",
    "5", "6", "7", "8", "9"
]

CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45

# 必须与生成 KMODEL 时的输入设置一致：
#
# 1.0         表示输入 RGB 像素值为 0～255。
# 1.0 / 255.0 表示模型直接接收 0～1 的浮点数。
#
# 如果归一化已经包含在 KMODEL 内部，不要再次除以 255。
INPUT_SCALE = 1.0


def preprocess(image, width, height):
    """
    将图片等比例缩放并居中填充到模型输入尺寸。

    返回：
        CHW 格式的 RGB 输入数据、
        缩放比例、
        左侧填充、
        顶部填充。
    """
    original_h, original_w = image.shape[:2]

    scale = min(
        width / original_w,
        height / original_h
    )

    new_w = max(1, int(round(original_w * scale)))
    new_h = max(1, int(round(original_h * scale)))

    resized = cv2.resize(
        image,
        (new_w, new_h),
        interpolation=cv2.INTER_LINEAR
    )

    left = int(round((width - new_w) / 2 - 0.1))
    top = int(round((height - new_h) / 2 - 0.1))

    canvas = np.full(
        (height, width, 3),
        114,
        dtype=np.uint8
    )

    canvas[
        top:top + new_h,
        left:left + new_w
    ] = resized

    # OpenCV 读取的是 BGR，转换为 RGB。
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)

    # HWC -> NCHW。
    chw = np.transpose(rgb, (2, 0, 1))
    chw = chw[None, ...]

    return np.ascontiguousarray(chw), scale, left, top


def postprocess(
    predictions,
    scale,
    left,
    top,
    image,
    class_names,
    conf_threshold,
    iou_threshold
):
    """
    处理 YOLOv8 检测输出。

    假设输出为：
        [1, 4 + 类别数, 检测点数]
    或：
        [1, 检测点数, 4 + 类别数]

    前 4 个数为 cx、cy、w、h，后面是各类别分数。
    """
    predictions = np.asarray(predictions)

    if predictions.ndim == 3 and predictions.shape[0] == 1:
        predictions = predictions[0]

    if predictions.ndim != 2:
        raise ValueError(
            "Unexpected output shape: {}".format(predictions.shape)
        )

    channels = 4 + len(class_names)

    if predictions.shape[0] == channels:
        predictions = predictions.T
    elif predictions.shape[1] != channels:
        raise ValueError(
            "Expected YOLOv8 output with {} channels, got {}".format(
                channels,
                predictions.shape
            )
        )

    predictions = predictions.astype(np.float32)

    boxes = predictions[:, :4]
    class_scores = predictions[:, 4:]

    if len(boxes) == 0:
        return []

    scores = np.max(class_scores, axis=1)
    class_ids = np.argmax(class_scores, axis=1)

    # 过滤低置信度和非有限值。
    keep = (
        (scores >= conf_threshold)
        & np.isfinite(predictions).all(axis=1)
    )

    boxes = boxes[keep]
    scores = scores[keep]
    class_ids = class_ids[keep]

    if len(boxes) == 0:
        return []

    cx, cy, w, h = boxes.T

    image_h, image_w = image.shape[:2]

    # 移除填充并映射回原图坐标。
    x1 = np.clip(
        (cx - w / 2 - left) / scale,
        0,
        image_w - 1
    )
    y1 = np.clip(
        (cy - h / 2 - top) / scale,
        0,
        image_h - 1
    )
    x2 = np.clip(
        (cx + w / 2 - left) / scale,
        0,
        image_w - 1
    )
    y2 = np.clip(
        (cy + h / 2 - top) / scale,
        0,
        image_h - 1
    )

    boxes = np.column_stack((x1, y1, x2, y2))

    valid = (x2 > x1) & (y2 > y1)

    boxes = boxes[valid]
    scores = scores[valid]
    class_ids = class_ids[valid]

    detections = []

    # 每个类别分别进行 NMS。
    for class_id in range(len(class_names)):
        indices = np.where(class_ids == class_id)[0]

        if len(indices) == 0:
            continue

        current_boxes = boxes[indices]
        current_scores = scores[indices]

        # OpenCV NMSBoxes 接收 x、y、width、height。
        xywh = current_boxes.copy()
        xywh[:, 2] -= xywh[:, 0]
        xywh[:, 3] -= xywh[:, 1]

        selected = cv2.dnn.NMSBoxes(
            xywh.tolist(),
            current_scores.tolist(),
            conf_threshold,
            iou_threshold
        )

        if selected is None or len(selected) == 0:
            continue

        for index in np.asarray(selected).reshape(-1):
            detections.append({
                "box": current_boxes[index],
                "score": float(current_scores[index]),
                "class_id": class_id
            })

    return sorted(
        detections,
        key=lambda item: item["score"],
        reverse=True
    )


def draw_boxes(image, detections, class_names):
    for det in detections:
        x1, y1, x2, y2 = map(int, det["box"])
        class_id = det["class_id"]

        label = "{}: {:.2f}".format(
            class_names[class_id],
            det["score"]
        )

        color = (0, 255, 0)

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            color,
            2
        )

        cv2.putText(
            image,
            label,
            (x1, max(y1 - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1
        )

    return image


def main():
    global MODEL_PATH, IMAGE_PATH, OUTPUT_PATH
    parser = argparse.ArgumentParser(description="Run a digit detector KMODEL in nncase Simulator")
    parser.add_argument("--model", default=MODEL_PATH, help="KMODEL file")
    parser.add_argument("--image", default=IMAGE_PATH, help="input image; default is a digit calibration sample")
    parser.add_argument("--output", default=OUTPUT_PATH, help="result image path")
    args = parser.parse_args()
    MODEL_PATH, IMAGE_PATH, OUTPUT_PATH = args.model, args.image, args.output
    print("[6] Entered main()", flush=True)

    if not os.path.isfile(MODEL_PATH):
        raise FileNotFoundError(
            "KMODEL not found: {}".format(MODEL_PATH)
        )

    if not os.path.isfile(IMAGE_PATH):
        raise FileNotFoundError(
            "Image not found: {}".format(IMAGE_PATH)
        )

    print("[7] Creating simulator", flush=True)
    sim = nncase.Simulator()

    print(
        "[8] Reading KMODEL: {}".format(MODEL_PATH),
        flush=True
    )

    with open(MODEL_PATH, "rb") as f:
        kmodel = f.read()

    if not kmodel:
        raise ValueError("KMODEL file is empty")

    print(
        "[9] Loading KMODEL ({} bytes)".format(len(kmodel)),
        flush=True
    )

    sim.load_model(kmodel)

    print("[10] KMODEL loaded", flush=True)

    print(
        "[11] Reading image: {}".format(IMAGE_PATH),
        flush=True
    )

    image = cv2.imread(IMAGE_PATH)

    if image is None:
        raise ValueError(
            "OpenCV could not read image: {}".format(IMAGE_PATH)
        )

    print(
        "[12] Image shape: {}".format(image.shape),
        flush=True
    )

    input_data, scale, left, top = preprocess(
        image,
        INPUT_WIDTH,
        INPUT_HEIGHT
    )

    input_desc = sim.get_input_desc(0)
    dtype = np.dtype(input_desc.dtype)

    print(
        "[13] Model input dtype: {}".format(dtype),
        flush=True
    )
    print(
        "[14] Model input shape: {}".format(
            getattr(input_desc, "shape", "unavailable")
        ),
        flush=True
    )

    if INPUT_SCALE != 1.0:
        if not np.issubdtype(dtype, np.floating):
            raise ValueError(
                "INPUT_SCALE requires a floating-point model input"
            )

        input_data = input_data.astype(np.float32) * INPUT_SCALE

    input_data = np.ascontiguousarray(
        input_data,
        dtype=dtype
    )

    print(
        "[15] Prepared input shape: {}, dtype: {}, range: {} ~ {}".format(
            input_data.shape,
            input_data.dtype,
            input_data.min(),
            input_data.max()
        ),
        flush=True
    )

    print("[16] Setting input tensor", flush=True)

    tensor = nncase.RuntimeTensor.from_numpy(input_data)
    sim.set_input_tensor(0, tensor)

    print("[17] Running inference", flush=True)
    sim.run()

    print(
        "[18] Inference completed; reading output 0",
        flush=True
    )

    predictions = sim.get_output_tensor(0).to_numpy()

    print(
        "[19] Output shape: {}, dtype: {}".format(
            predictions.shape,
            predictions.dtype
        ),
        flush=True
    )

    if predictions.size == 0:
        raise ValueError("Model output is empty")

    print(
        "[20] Output range: {} ~ {}".format(
            predictions.min(),
            predictions.max()
        ),
        flush=True
    )

    output = np.asarray(predictions)
    if output.ndim == 3 and output.shape[0] == 1:
        output = output[0]
    if output.ndim == 2 and output.shape[0] == 4 + len(CLASS_NAMES):
        output = output.T
    if output.ndim == 2 and output.shape[1] == 4 + len(CLASS_NAMES):
        class_scores = output[:, 4:]
        best_scores = np.max(class_scores, axis=1)
        best_classes = np.argmax(class_scores, axis=1)
        top_indices = np.argsort(best_scores)[-10:][::-1]
        print('[DEBUG] Class score range: {:.6f} ~ {:.6f}'.format(
            class_scores.min(), class_scores.max()), flush=True)
        print('[DEBUG] Candidates >= {}: {}'.format(
            CONF_THRESHOLD, np.count_nonzero(best_scores >= CONF_THRESHOLD)), flush=True)
        print('[DEBUG] Top 10 candidates:', flush=True)
        for index in top_indices:
            print('  class={} score={:.6f} xywh={}'.format(
                CLASS_NAMES[int(best_classes[index])],
                float(best_scores[index]),
                output[index, :4].tolist()), flush=True)
    else:
        print('[DEBUG] Unexpected output shape: {}'.format(output.shape), flush=True)

    detections = postprocess(
        predictions,
        scale,
        left,
        top,
        image,
        CLASS_NAMES,
        CONF_THRESHOLD,
        IOU_THRESHOLD
    )

    print(
        "[21] Detection count: {}".format(len(detections)),
        flush=True
    )

    for det in detections:
        print(
            "Digit: {} | Confidence: {:.4f} | Box: {}".format(
                CLASS_NAMES[det["class_id"]],
                det["score"],
                det["box"].astype(int).tolist()
            ),
            flush=True
        )

    result = draw_boxes(
        image.copy(),
        detections,
        CLASS_NAMES
    )

    if not cv2.imwrite(OUTPUT_PATH, result):
        raise RuntimeError(
            "Could not save result: {}".format(OUTPUT_PATH)
        )

    print(
        "[22] Result saved: {}".format(OUTPUT_PATH),
        flush=True
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
