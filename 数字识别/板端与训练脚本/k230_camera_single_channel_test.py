"""Single-channel camera startup test, without model, UART, or motor control."""

ENABLE_IDE_PREVIEW = True


def main():
    import gc
    import os
    import time
    from media.media import MediaManager
    from media.sensor import Sensor

    sensor = None
    media_ready = False
    running = False
    stage = "SENSOR_CONFIG"
    try:
        print("[TEST] SINGLE_CHANNEL IDE_PREVIEW={}".format(ENABLE_IDE_PREVIEW))
        print("[BOOT]", stage)
        sensor = Sensor(width=640, height=480, fps=30)
        sensor.reset()
        sensor.set_vflip(False)
        sensor.set_hmirror(False)
        sensor.set_framesize(width=640, height=480, chn=0)
        sensor.set_pixformat(Sensor.RGB565, chn=0)
        stage = "MEDIA_INIT"
        print("[BOOT]", stage)
        MediaManager.init()
        media_ready = True
        stage = "SENSOR_RUN"
        print("[BOOT]", stage)
        sensor.run()
        running = True
        print("[OK] SENSOR_RUN")
        start = time.ticks_ms()
        frames = 0
        while time.ticks_diff(time.ticks_ms(), start) < 10000:
            os.exitpoint()
            stage = "SNAPSHOT"
            frame = sensor.snapshot(chn=0, timeout=3000)
            if ENABLE_IDE_PREVIEW:
                stage = "PREVIEW"
                frame.compress_for_ide()
            frames += 1
            if frames == 1:
                print("[OK] FIRST_FRAME")
            del frame
        print("[OK] TEST_DONE frames={}".format(frames))
    except KeyboardInterrupt:
        print("[STOP] Interrupted")
    except Exception as error:
        print("[ERROR] stage={} error={}".format(stage, error))
        raise
    finally:
        if running:
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
        print("[EXIT] SINGLE_CHANNEL")


if __name__ == "__main__":
    main()
