"""CanMV K230 vision for white cards numbered 0-9, using a YOLOv8n kmodel.

This replaces the template-matching detector in `k230视觉云台.py` with a
YOLOv8n INT8 kmodel (digits 0-9, class index == digit ID). The sensor/UART
setup, the STM32 command protocol (SCAN / ID,n / STOP) and the serial frame
format are kept identical to the proven `k230视觉云台.py` so the cloud-side
state machine (A/B/C/D/J/T) is untouched.

Frame sent to STM32 (parsed by HARDWARE/K230/k230.c K230_Parse):
    b"\xAA\x55" + "width,height,x,y,box_w,box_h,ids,mode,id,sequence" + b"\r\n"
  mode: 0=IDLE 1=SCAN 2=TRACK 3=FAULT 4=LEGACY
  ids : bitmask, bit d set when digit d is detected
  x,y  : centre of the selected box (-1 if none); box_w,box_h : its size

Flashing checklist (cannot be tested on PC, verify on the K230):
  * Copy `best.kmodel` to the SD card root; set MODEL_PATH to its path.
  * Confirm the CanMV firmware's YOLO helper import path / constructor
    signature below matches your image (see YoloDetector). If `libs.YOLO`
    differs, adapt that one class only.
"""

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DETECT_WIDTH = 640
DETECT_HEIGHT = 480
SENSOR_WIDTH = 640
SENSOR_HEIGHT = 480
SENSOR_FPS = 30
VFLIP = False
HMIRROR = False
ENABLE_IDE_PREVIEW = True

UART_TX_PIN = 50          # WonderMK external TX -> STM32 PB11
UART_RX_PIN = 51          # WonderMK external RX <- STM32 PB10
COMMAND_INPUT = "uart3"   # STM32 sends STOP / SCAN / ID,n on this port
MODEL_PATH = "/sd/best.kmodel"   # <-- kmodel on the K230 SD card

SEND_INTERVAL_MS = 50
DETECT_INTERVAL_MS = 150
CONFIRM_FRAMES = 3
STATUS_INTERVAL_MS = 2000

# YOLOv8n class order. Index == digit ID (0-9), matching digits.yaml.
LABELS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
INPUT_SIZE = [320, 320]   # must equal training imgsz
CONF_THRESHOLD = 0.35
NMS_THRESHOLD = 0.45
# model_type is firmware-specific in CanMV. Common values: "yolov8" or
# "k230_jpeg_decoder" (for JPEG input). Leave as "" if your firmware infers it.
MODEL_TYPE = "yolov8"

VISION_IDLE, VISION_SCAN, VISION_TRACK, VISION_FAULT = 0, 1, 2, 3

FRAME_HEADER = b"\xAA\x55"
FRAME_TAIL = b"\r\n"

MAX_MATCH_DISTANCE = 46    # kept for reference; not used by YOLO path
MIN_MATCH_MARGIN = 14


# ---------------------------------------------------------------------------
# YOLO detector (the only part that differs from k230视觉云台.py)
# ---------------------------------------------------------------------------
class YoloDetector:
    """Wraps the CanMV K230 YOLO helper and returns [(digit, (x, y, w, h)), ...]."""

    def __init__(self, model_path):
        # Adapt this import/constructor if your firmware's YOLO API differs.
        from libs.YOLO import YOLO
        self.yolo = YOLO(
            model_path=model_path,
            labels=LABELS,
            model_type=MODEL_TYPE,
            input_size=INPUT_SIZE,
            confidence_threshold=CONF_THRESHOLD,
            nms_threshold=NMS_THRESHOLD,
        )

    def detect(self, img):
        """img: 640x480 frame from sensor.snapshot(). Returns list of (digit, rect)."""
        # The CanMV YOLO helper resizes internally to INPUT_SIZE and maps the
        # boxes back to the original frame coordinates, so rect is in 640x480.
        raw = self.yolo.run(img)
        out = []
        for r in raw:
            # Typical layout: (x, y, w, h, class_id, score)
            x, y, w, h = int(r[0]), int(r[1]), int(r[2]), int(r[3])
            cls = int(r[4])
            if 0 <= cls < len(LABELS):
                out.append((cls, (x, y, w, h)))
        return out


# ---------------------------------------------------------------------------
# Below: protocol / session / UART code identical to the proven k230视觉云台.py
# ---------------------------------------------------------------------------
def center(rect):
    x, y, width, height = rect
    return x + width // 2, y + height // 2


def nearby(previous, current):
    old_x, old_y = center(previous)
    new_x, new_y = center(current)
    return (abs(new_x - old_x) <= max(previous[2], current[2])
            and abs(new_y - old_y) <= max(previous[3], current[3]))


class CommandReader:
    def __init__(self):
        self.line = bytearray()
        self.discard = False

    def feed(self, data):
        for value in data or b"":
            if value in (10, 13):
                if self.line and not self.discard:
                    yield bytes(self.line)
                self.line = bytearray()
                self.discard = False
            elif not self.discard:
                if len(self.line) < 8:
                    self.line.append(value)
                else:
                    self.discard = True


class UARTCommandInput:
    def __init__(self, uart):
        self.uart = uart

    def __call__(self, limit):
        available = self.uart.any()
        return self.uart.read(min(limit, available)) if available else None


def open_uart():
    print("[BOOT] UART_IMPORT")
    from machine import FPIOA, UART
    print("[OK] UART_IMPORT")
    print("[BOOT] UART_FPIOA")
    fpioa = FPIOA()
    print("[BOOT] UART_TX GPIO", UART_TX_PIN)
    fpioa.set_function(UART_TX_PIN, FPIOA.UART3_TXD, oe=1)
    print("[OK] UART_TX")
    if COMMAND_INPUT == "uart3":
        print("[BOOT] UART_RX GPIO", UART_RX_PIN)
        fpioa.set_function(UART_RX_PIN, FPIOA.UART3_RXD, ie=1)
        print("[OK] UART_RX")
    print("[BOOT] UART_OPEN UART3 115200 8N1")
    uart = UART(UART.UART3, baudrate=115200, bits=UART.EIGHTBITS,
                parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
    print("[OK] UART3_READY")
    return uart


def open_command_input(uart):
    if COMMAND_INPUT == "none":
        return None
    if COMMAND_INPUT == "uart3":
        return UARTCommandInput(uart)
    raise ValueError("COMMAND_INPUT must be none or uart3")


class VisionSession:
    def __init__(self, ticks_diff):
        self.ticks_diff = ticks_diff
        self.target_id = None
        self.scan_started = None
        self.seen = set()
        self.streaks = {}
        self.scan_result = None
        self.mode = VISION_IDLE
        self.sequence = 0

    def command(self, line, now):
        if line == b"SCAN":
            if self.scan_started is not None:
                return True
            self.scan_started = now
            self.seen.clear()
            self.target_id = None
            self.mode = VISION_SCAN
        elif line == b"STOP":
            self.finish_scan()
            self.target_id = None
            self.mode = VISION_IDLE
        elif len(line) == 4 and line[:3] == b"ID," and 48 <= line[3] <= 57:
            target_id = line[3] - 48
            if target_id == self.target_id:
                return True
            self.target_id = target_id
            self.finish_scan()
            self.mode = VISION_TRACK
        else:
            return False
        self.streaks = {}
        return True

    def finish_scan(self):
        if self.scan_started is not None:
            self.scan_result = tuple(sorted(self.seen))
            self.scan_started = None

    def take_scan_result(self):
        result = self.scan_result
        self.scan_result = None
        return result

    def observe(self, detections, now):
        # STM32 owns the scan deadline. Stay in SCAN until its next command.
        self.sequence = (self.sequence + 1) & 0xFFFF

        by_id = {}
        duplicates = set()
        for digit, rect in detections:
            if digit in by_id:
                duplicates.add(digit)
            by_id[digit] = rect

        confirmed = {}
        streaks = {}
        for digit, rect in by_id.items():
            if digit in duplicates:
                continue
            previous = self.streaks.get(digit)
            count = 1
            if previous is not None and nearby(previous[0], rect):
                count = min(CONFIRM_FRAMES, previous[1] + 1)
            streaks[digit] = (rect, count)
            if count == CONFIRM_FRAMES:
                confirmed[digit] = rect
        self.streaks = streaks

        new_ids = ()
        if self.scan_started is not None:
            new_ids = tuple(sorted(set(confirmed) - self.seen))
            self.seen.update(new_ids)
        return confirmed, new_ids, self.take_scan_result()

    def packet(self, confirmed):
        selected = confirmed.get(self.target_id) if self.mode == VISION_TRACK else None
        return coordinate_frame(selected, confirmed, self.mode, self.target_id, self.sequence)


def coordinate_frame(rect, ids, mode, target_id, sequence):
    mask = 0
    for digit in ids:
        mask |= 1 << digit
    if mode != VISION_TRACK:
        rect, target_id = None, -1
    if rect is None:
        cx = cy = width = height = -1
    else:
        cx, cy = center(rect)
        width, height = rect[2:]
    payload = "{},{},{},{},{},{},{},{},{},{}".format(
        DETECT_WIDTH, DETECT_HEIGHT, cx, cy, width, height,
        mask, mode, target_id, sequence
    )
    return FRAME_HEADER + payload.encode() + FRAME_TAIL


def send_coordinates(uart, session, confirmed):
    frame = session.packet(confirmed)
    sent = uart.write(frame)
    if sent != len(frame):
        raise OSError("UART3 short write: {} of {}".format(sent, len(frame)))


def draw_overlay(frame, confirmed, target_id):
    for digit, rect in confirmed.items():
        color = (0, 255, 0) if digit == target_id else (255, 255, 0)
        frame.draw_rectangle(rect, color=color, thickness=2)
        frame.draw_string(rect[0], max(0, rect[1] - 18), str(digit), color=color, scale=2)
    if target_id in confirmed:
        cx, cy = center(confirmed[target_id])
        frame.draw_cross(cx, cy, color=(0, 255, 0))


def cleanup(action, *args):
    try:
        action(*args)
    except Exception as error:
        print("CLEANUP_ERROR", error)


def report_scan_result(result):
    if result is not None:
        print("SCAN_RESULT,{}".format(",".join([str(digit) for digit in result])))


def main():
    import gc
    import os
    import time
    from media.media import MediaManager
    from media.sensor import Sensor

    uart = sensor = None
    media_ready = sensor_running = False
    session = VisionSession(time.ticks_diff)
    reader = CommandReader()
    confirmed = {}
    read_commands = None
    stage = "START"
    detector = None
    try:
        print("[BOOT] K230_YOLO_VISION 640x480 UART3 GPIO50/51")
        print("[BOOT] MODEL_PATH={}".format(MODEL_PATH))
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError("kmodel not found: " + MODEL_PATH)
        print("[BOOT] CAMERA_ONLY=False IDE_PREVIEW={}".format(ENABLE_IDE_PREVIEW))

        stage = "UART_INIT"
        uart = open_uart()
        read_commands = open_command_input(uart)
        stage = "UART_FIRST_TX"
        print("[BOOT]", stage)
        send_coordinates(uart, session, confirmed)
        print("[OK] UART_FIRST_TX (local write only)")

        stage = "SENSOR_CONFIG"
        print("[BOOT]", stage)
        sensor = Sensor(width=SENSOR_WIDTH, height=SENSOR_HEIGHT, fps=SENSOR_FPS)
        sensor.reset()
        sensor.set_vflip(VFLIP)
        sensor.set_hmirror(HMIRROR)
        sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT, chn=0)
        sensor.set_pixformat(Sensor.RGB565, chn=0)
        stage = "MEDIA_INIT"
        print("[BOOT]", stage)
        MediaManager.init()
        media_ready = True
        stage = "SENSOR_RUN"
        print("[BOOT]", stage)
        sensor.run()
        sensor_running = True
        print("[OK]", stage)
        time.sleep_ms(200)

        stage = "MODEL_LOAD"
        print("[BOOT]", stage)
        detector = YoloDetector(MODEL_PATH)
        print("[OK] MODEL_LOADED")

        last_send = last_detect = None
        tracked_id = None
        last_status = time.ticks_ms()
        frames = command_count = detect_ms = 0
        print("[BOOT] FIRST_SNAPSHOT")
        while True:
            os.exitpoint()
            stage = "COMMAND_READ"
            if read_commands is not None:
                for command in reader.feed(read_commands(32)):
                    before = (session.mode, session.target_id)
                    if session.command(command, time.ticks_ms()):
                        command_count += 1
                        if command_count == 1 or before != (session.mode, session.target_id):
                            print("[RX]", command.decode())
                        if before != (session.mode, session.target_id) or command == b"STOP":
                            confirmed = {}
                            last_detect = None
                        report_scan_result(session.take_scan_result())
                        stage = "COMMAND_REPLY"
                        send_coordinates(uart, session, confirmed)
                        last_send = time.ticks_ms()
                    else:
                        print("[RX] INVALID_COMMAND", command)

            stage = "SNAPSHOT"
            frame = sensor.snapshot(chn=0)
            frames += 1

            now = time.ticks_ms()
            if last_detect is None or time.ticks_diff(now, last_detect) >= DETECT_INTERVAL_MS:
                stage = "RECOGNITION"
                started = time.ticks_ms()
                detections = detector.detect(frame)
                now = time.ticks_ms()
                detect_ms = time.ticks_diff(now, started)
                confirmed, new_ids, scan_result = session.observe(detections, now)
                last_detect = now
                for digit in new_ids:
                    print("FOUND,{}".format(digit))
                report_scan_result(scan_result)

            active_id = session.target_id if session.target_id in confirmed else None
            if tracked_id != active_id:
                if tracked_id is not None:
                    print("LOST,{}".format(tracked_id))
                if active_id is not None:
                    print("TRACK,{}".format(active_id))
                tracked_id = active_id
            stage = "UART_TX"
            if last_send is None or time.ticks_diff(now, last_send) >= SEND_INTERVAL_MS:
                send_coordinates(uart, session, confirmed)
                last_send = now
            draw_overlay(frame, confirmed, active_id)

            if ENABLE_IDE_PREVIEW:
                stage = "PREVIEW"
                frame.compress_for_ide()
            now = time.ticks_ms()
            if time.ticks_diff(now, last_status) >= STATUS_INTERVAL_MS:
                print("[STATUS] frames={} mode={} id={} rx_commands={} seq={} detect_ms={} cards={}".format(
                    frames, session.mode, session.target_id, command_count,
                    session.sequence, detect_ms, sorted(confirmed)))
                last_status = now
            del frame
            time.sleep_ms(1)

    except KeyboardInterrupt:
        print("STOPPED")
    except Exception as error:
        print("[ERROR]", stage, error)
        raise
    finally:
        print("[EXIT] cleanup")
        if uart is not None:
            session.mode = VISION_FAULT
            cleanup(send_coordinates, uart, session, {})
            cleanup(uart.deinit)
        if sensor_running:
            cleanup(sensor.stop)
        gc.collect()
        if media_ready:
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            time.sleep_ms(100)
            cleanup(MediaManager.deinit)


if __name__ == "__main__":
    main()
