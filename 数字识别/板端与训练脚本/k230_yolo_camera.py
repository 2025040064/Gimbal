"""K230 YOLOv8 camera test. Run in CanMV IDE; does not control the gimbal."""

MODEL_PATH = "/sdcard/examples/kmodel/best_calibrated_50.kmodel"
LABELS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
FRAME_WIDTH, FRAME_HEIGHT = 640, 480
ENABLE_IDE_PREVIEW = True
CONF_THRESHOLD, NMS_THRESHOLD = 0.25, 0.45


def normalize_detections(result):
    if result is None or len(result) < 3:
        return []
    boxes, ids, scores = result[0], result[1], result[2]
    detections = []
    for index in range(len(boxes)):
        digit = int(ids[index])
        if 0 <= digit < len(LABELS):
            rect = tuple(int(round(float(value))) for value in boxes[index])
            detections.append((digit, float(scores[index]), rect))
    return detections


def main():
    import gc
    import os
    import time
    from media.media import MediaManager
    from media.sensor import Sensor
    from libs.YOLO import YOLOv8

    sensor = None
    detector = None
    media_ready = False
    sensor_running = False
    stage = "START"
    try:
        print("[BOOT] K230 YOLO CAMERA TEST; IDE_PREVIEW={}".format(ENABLE_IDE_PREVIEW))
        print("[BOOT] MODEL_PATH={}".format(MODEL_PATH))
        os.stat(MODEL_PATH)

        stage = "SENSOR_CONFIG"
        print("[BOOT]", stage)
        sensor = Sensor(width=FRAME_WIDTH, height=FRAME_HEIGHT, fps=30)
        sensor.reset()
        sensor.set_vflip(False)
        sensor.set_hmirror(False)
        sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT, chn=0)
        sensor.set_pixformat(Sensor.RGB565, chn=0)
        sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT, chn=2)
        sensor.set_pixformat(Sensor.RGBP888, chn=2)

        stage = "MEDIA_INIT"
        print("[BOOT]", stage)
        MediaManager.init()
        media_ready = True
        stage = "SENSOR_RUN"
        print("[BOOT]", stage)
        sensor.run()
        sensor_running = True
        print("[OK] SENSOR_RUN")
        time.sleep_ms(200)

        stage = "FIRST_PREVIEW"
        print("[BOOT]", stage)
        preview = sensor.snapshot(chn=0, timeout=3000)
        if ENABLE_IDE_PREVIEW:
            preview.compress_for_ide()
        print("[OK] FIRST_PREVIEW")
        del preview

        stage = "MODEL_LOAD"
        print("[BOOT]", stage)
        detector = YOLOv8(task_type="detect", mode="video", kmodel_path=MODEL_PATH,
                          labels=LABELS, rgb888p_size=[FRAME_WIDTH, FRAME_HEIGHT],
                          model_input_size=[320, 320], display_size=[FRAME_WIDTH, FRAME_HEIGHT],
                          conf_thresh=CONF_THRESHOLD, nms_thresh=NMS_THRESHOLD,
                          max_boxes_num=50, debug_mode=0)
        print("[OK] MODEL_LOADED")
        stage = "PREPROCESS_CONFIG"
        print("[BOOT]", stage)
        detector.config_preprocess()
        print("[OK] PREPROCESS_CONFIG")

        frames = 0
        last_report = time.ticks_ms()
        while True:
            os.exitpoint()
            stage = "AI_SNAPSHOT"
            if frames == 0:
                print("[BOOT]", stage)
            ai_frame = sensor.snapshot(chn=2, timeout=3000)
            ai_input = ai_frame.to_numpy_ref()
            if frames == 0:
                print("[OK] AI_SNAPSHOT shape={}".format(ai_input.shape))
            stage = "INFERENCE"
            if frames == 0:
                print("[BOOT]", stage)
            start = time.ticks_ms()
            results = detector.run(ai_input)
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            detections = normalize_detections(results)
            del ai_input, ai_frame
            if frames == 0:
                print("[OK] FIRST_INFERENCE {} ms".format(elapsed))

            stage = "PREVIEW_SNAPSHOT"
            preview = sensor.snapshot(chn=0, timeout=3000)
            for digit, score, rect in detections:
                preview.draw_rectangle(rect, color=(0, 255, 0), thickness=2)
                preview.draw_string(rect[0], max(0, rect[1] - 18),
                                    "{} {:.2f}".format(digit, score),
                                    color=(0, 255, 0), scale=2)
            if ENABLE_IDE_PREVIEW:
                stage = "PREVIEW"
                preview.compress_for_ide()
            del preview
            frames += 1
            now = time.ticks_ms()
            if time.ticks_diff(now, last_report) >= 2000:
                print("[STATUS] frames={} inference_ms={} detections={}".format(
                    frames, elapsed, detections))
                last_report = now
            gc.collect()
    except KeyboardInterrupt:
        print("[STOP] Interrupted")
    except Exception as error:
        print("[ERROR] stage={} error={}".format(stage, error))
        raise
    finally:
        if detector is not None:
            try:
                detector.deinit()
            except Exception as error:
                print("[CLEANUP] detector", error)
        if sensor_running:
            try:
                sensor.stop()
            except Exception as error:
                print("[CLEANUP] sensor", error)
        if media_ready:
            try:
                os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
                time.sleep_ms(100)
                MediaManager.deinit()
            except Exception as error:
                print("[CLEANUP] media", error)
        gc.collect()
        print("[EXIT] CAMERA TEST")


if __name__ == "__main__":
    main()
