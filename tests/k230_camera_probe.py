"""Run online in CanMV IDE to test the WonderMK camera."""

import os
import time

from media.media import MediaManager
from media.sensor import Sensor


PREVIEW = False
SENSOR_WIDTH = 1920
SENSOR_HEIGHT = 1080
SENSOR_FPS = 30
FRAME_WIDTH = 640
FRAME_HEIGHT = 480


def main():
    sensor = display = None
    media_ready = False
    stage = "SENSOR_CONFIG"
    try:
        print("[CAMERA TEST]", SENSOR_WIDTH, SENSOR_HEIGHT, SENSOR_FPS, "preview", PREVIEW)
        sensor = Sensor(width=SENSOR_WIDTH, height=SENSOR_HEIGHT, fps=SENSOR_FPS)
        sensor.reset()
        sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT,chn =0)
        sensor.set_pixformat(Sensor.RGB565,chn = 0)

        if PREVIEW:
            stage = "DISPLAY_INIT"
            from media.display import Display

            Display.init(Display.VIRT, width=FRAME_WIDTH, height=FRAME_HEIGHT, fps=30, to_ide=True)
            display = Display

        stage = "MEDIA_INIT"
        print("[TEST]", stage)
        MediaManager.init()
        media_ready = True
        stage = "SENSOR_RUN"
        print("[TEST]", stage)
        sensor.run()
        print("[OK]", stage)

        started = time.ticks_ms()
        frames = 0
        while time.ticks_diff(time.ticks_ms(), started) < 5000:
            os.exitpoint()
            stage = "SNAPSHOT"
            frame = sensor.snapshot(chn=0, timeout=3000)
            frames += 1
            if frames == 1:
                print("[OK] FIRST_SNAPSHOT", frame.width(), frame.height())
            if display is not None:
                stage = "PREVIEW"
                display.show_image(frame)
        print("[OK] FRAMES", frames)
    except Exception as error:
        print("[ERROR]", stage, error)
        raise
    finally:
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("[CLEANUP] SENSOR", error)
        if display is not None:
            display.deinit()
        if media_ready:
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            time.sleep_ms(100)
            MediaManager.deinit()


if __name__ == "__main__":
    main()
