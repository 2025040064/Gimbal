from media.media import MediaManager
from media.sensor import Sensor

sensor = Sensor()
media_ready = False
try:
    print("[TEST] sensor reset")
    sensor.reset()
    sensor.set_framesize(width=640, height=480)
    sensor.set_pixformat(Sensor.RGB565)
    print("[TEST] media init")
    MediaManager.init()
    media_ready = True
    print("[TEST] sensor.run")
    sensor.run()
    print("[TEST] snapshot")
    frame = sensor.snapshot()
    print("[OK] FRAME", frame.width(), frame.height())
finally:
    try:
        sensor.stop()
    finally:
        if media_ready:
            MediaManager.deinit()
