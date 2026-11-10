import os
import time
from media.sensor import Sensor
from media.display import Display
from media.media import MediaManager

sensor = None
display_ready = False
media_ready = False
uart = None

try:
    print('[1] Sensor')
    sensor = Sensor()
    sensor.reset()
    sensor.set_framesize(width=640, height=480)
    sensor.set_pixformat(Sensor.RGB565)

    print('[2] Display')
    Display.init(Display.VIRT, width=640, height=480, fps=30, to_ide=True)
    display_ready = True

    print('[3] MediaManager')
    MediaManager.init()
    media_ready = True

    print('[4] sensor.run')
    sensor.run()
    frame = sensor.snapshot()
    Display.show_image(frame)
    print('[5] FIRST_PREVIEW_OK')

    print('[6] import UART')
    from machine import FPIOA, UART
    fpioa = FPIOA()
    fpioa.set_function(5, FPIOA.UART2_TXD)
    uart = UART(UART.UART2, baudrate=115200, bits=UART.EIGHTBITS,
                parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
    print('[7] UART_OK')

    print('[8] import image')
    import image
    gray = image.Image(640, 480, image.GRAYSCALE)
    print('[9] GRAY_OK')

    last_status = time.ticks_ms()
    while True:
        os.exitpoint()
        frame = sensor.snapshot()
        Display.show_image(frame)
        gray.draw_image(frame, 0, 0)
        now = time.ticks_ms()
        if time.ticks_diff(now, last_status) >= 2000:
            print('[RUN] preview and gray OK')
            last_status = now

except KeyboardInterrupt:
    print('[STOP]')
except BaseException as error:
    print('[ERROR]', error)
    try:
        import sys
        sys.print_exception(error)
    except Exception:
        pass
finally:
    print('[EXIT]')
    if uart is not None:
        try: uart.deinit()
        except Exception: pass
    if sensor is not None:
        try: sensor.stop()
        except Exception: pass
    if display_ready:
        try: Display.deinit()
        except Exception: pass
    if media_ready:
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)
        try: MediaManager.deinit()
        except Exception: pass
