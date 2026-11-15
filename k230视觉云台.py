"""YOLOv8 digit detection with the STM32 contest UART protocol (IDs 0-9)."""

DETECT_WIDTH = 640
DETECT_HEIGHT = 480
SENSOR_WIDTH = 640
SENSOR_HEIGHT = 480
SENSOR_FPS = 30
VFLIP = False
HMIRROR = False
CAMERA_ONLY = False  # Set to True to test the camera and IDE preview alone.
ENABLE_IDE_PREVIEW = True

UART_TX_PIN = 50  # WonderMK external TX -> STM32 PB11.
UART_RX_PIN = 51  # WonderMK external RX <- STM32 PB10.
ONE_WAY = True  # Only TX GPIO50 -> STM32 PB11, plus common ground.
COMMAND_INPUT = "none"
INITIAL_TARGET_ID = None  # One-way mode broadcasts all IDs; STM32 selects locally.
SEND_INTERVAL_MS = 50
DETECT_INTERVAL_MS = 0  # Run each loop; avoid adding 150 ms to inference latency.
CONFIRM_FRAMES = 3
STATUS_INTERVAL_MS = 2000
COMMAND_TIMEOUT_MS = 2000
VISION_IDLE, VISION_SCAN, VISION_TRACK, VISION_FAULT = 0, 1, 2, 3

MODEL_PATH = "/sdcard/examples/kmodel/best_calibrated_50.kmodel"
LABELS = [str(i) for i in range(10)]
CONF_THRESHOLD, NMS_THRESHOLD = 0.25, 0.45
MODEL_INPUT_SIZE = [320, 320]
RECORD_ROOT = "/sdcard/gimbal_records"
RECORD_INTERVAL_MS = 100
RECORD_QUALITY = 50
RECORD_MIN_FREE_BYTES = 16 * 1024 * 1024
MAX_OBSERVATION_MS = 300  # Do not deliver slow, stale coordinates as fresh targets.
FRAME_HEADER = b"\xAA\x55"
FRAME_TAIL = b"\r\n"


def normalize_detections(result):
    """Convert the camera-test YOLO output (boxes/ids/scores) to valid xywh."""
    import math
    if result is None or len(result) < 3:
        return []
    boxes, ids, scores = result[0], result[1], result[2]
    if len(boxes) != len(ids) or len(boxes) != len(scores):
        raise ValueError("YOLO result lengths differ")
    detections = []
    for index in range(len(boxes)):
        digit = int(ids[index])
        score = float(scores[index])
        if not 0 <= digit < 10 or not math.isfinite(score) or score < CONF_THRESHOLD:
            continue
        if len(boxes[index]) != 4:
            raise ValueError("YOLO box must contain x,y,width,height")
        values = [float(value) for value in boxes[index]]
        if not all(math.isfinite(value) for value in values):
            continue
        x, y, width, height = [int(round(value)) for value in values]
        if width <= 0 or height <= 0:
            continue
        right, bottom = min(DETECT_WIDTH, x + width), min(DETECT_HEIGHT, y + height)
        x, y = max(0, x), max(0, y)
        if right > x and bottom > y:
            detections.append((digit, (x, y, right - x, bottom - y)))
    return detections


def open_detector():
    import os
    from libs.YOLO import YOLOv8
    os.stat(MODEL_PATH)
    return YOLOv8(task_type="detect", mode="video", kmodel_path=MODEL_PATH,
                  labels=LABELS, rgb888p_size=[DETECT_WIDTH, DETECT_HEIGHT],
                  model_input_size=MODEL_INPUT_SIZE, display_size=[DETECT_WIDTH, DETECT_HEIGHT],
                  conf_thresh=CONF_THRESHOLD, nms_thresh=NMS_THRESHOLD,
                  max_boxes_num=50, debug_mode=0)


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


class USBCommandInput:
    def __init__(self, stream, poller, pollin):
        self.stream = stream
        self.poller = poller
        self.pollin = pollin

    def __call__(self, limit):
        data = bytearray()
        for _ in range(limit):
            events = self.poller.poll(0)
            if not events or not events[0][1] & self.pollin:
                break
            chunk = self.stream.read(1)
            if not chunk:
                break
            data.extend(chunk.encode() if isinstance(chunk, str) else chunk)
        return data


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


class UARTCommandInput:
    def __init__(self, uart):
        self.uart = uart

    def __call__(self, limit):
        available = self.uart.any()
        return self.uart.read(min(limit, available)) if available else None


def open_command_input(uart):
    if COMMAND_INPUT == "none":
        return None
    if COMMAND_INPUT == "uart3":
        return UARTCommandInput(uart)
    if COMMAND_INPUT != "usb":
        raise ValueError("COMMAND_INPUT must be none, uart3 or usb")
    try:
        import sys
        try:
            import select
        except ImportError:
            import uselect as select
        poller = select.poll()
        poller.register(sys.stdin, select.POLLIN)
        return USBCommandInput(sys.stdin, poller, select.POLLIN)
    except (ImportError, AttributeError, OSError, TypeError, ValueError) as error:
        print("COMMAND_INPUT_ERROR,USB", error)
        return None


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
            # The STM32 contest protocol selects IDs 0-9.
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
        if ONE_WAY:
            return broadcast_frame(confirmed, self.sequence, self.mode == VISION_FAULT)
        selected = confirmed.get(self.target_id) if self.mode == VISION_TRACK else None
        return coordinate_frame(selected, confirmed, self.mode, self.target_id, self.sequence)


def broadcast_frame(confirmed, sequence, fault=False):
    items = [] if fault else sorted(confirmed.items())
    fields = ["ALL", str(DETECT_WIDTH), str(DETECT_HEIGHT), str(sequence), "3" if fault else "0", str(len(items))]
    for digit, rect in items:
        cx, cy = center(rect)
        fields.extend(str(value) for value in (digit, cx, cy, rect[2], rect[3]))
    return FRAME_HEADER + ",".join(fields).encode() + FRAME_TAIL


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



class ContestRecorder:
    """Raw MJPEG plus timestamps; a new directory for every task, never overwrite."""
    def __init__(self, root, ticks_ms, ticks_diff):
        import os
        self.root, self.clock, self.diff = root, ticks_ms, ticks_diff
        self.video = self.events = None
        self.folder = None
        self.frames = 0
        self.write_ms = self.encode_ms = self.gap_ms = 0
        self.total_ms = 0
        try:
            os.mkdir(root)
        except OSError as error:
            if not error.args or error.args[0] != 17:
                raise
        self.check_space()
        self.reserve()
        # Probe the reserved, newly created directory before advertising readiness.
        probe = self.folder + "/write_check"
        with open(probe, "wb") as stream:
            self.write_all(stream, b"ready")
            stream.flush()
        os.remove(probe)

    def reserve(self):
        import os
        for number in range(1, 100000):
            folder = self.root + "/gimbal_{:05d}".format(number)
            try:
                os.mkdir(folder)
                self.folder = folder
                return
            except OSError as error:
                if not error.args or error.args[0] != 17:
                    raise
        raise OSError("Recording directory limit reached")

    def check_space(self):
        import os
        stats = os.statvfs(self.root)
        if stats[1] * stats[4] < RECORD_MIN_FREE_BYTES:
            raise OSError("Recording storage low")

    @staticmethod
    def write_all(stream, data):
        if stream.write(data) != len(data):
            raise OSError("Recording short write")

    def start(self, mode, target_id, now):
        if self.video is not None:
            return
        if self.folder is None:
            self.reserve()
        self.check_space()
        self.started = self.last_flush = now
        self.last_frame = None
        self.frames = 0
        try:
            self.video = open(self.folder + "/camera.mjpeg", "wb")
            self.events = open(self.folder + "/events.csv", "wb")
            self.event(now, "START", mode, target_id)
            self.events.flush()
        except Exception:
            self.close(now, "OPEN_ERROR")
            raise
        print("[RECORD]", self.folder)

    def event(self, now, name, *values):
        if self.events is not None:
            line = ",".join([str(self.diff(now, self.started)), name] + [str(value) for value in values]) + "\n"
            self.write_all(self.events, line.encode())

    def capture(self, frame, captured_at):
        if self.video is None:
            return
        if self.last_frame is not None and self.diff(captured_at, self.last_frame) < RECORD_INTERVAL_MS:
            return
        began = started = self.clock()
        jpeg = frame.compressed(quality=RECORD_QUALITY)
        data = memoryview(jpeg)
        if len(data) < 4 or bytes(data[:2]) != b"\xff\xd8" or bytes(data[-2:]) != b"\xff\xd9":
            raise ValueError("Invalid JPEG recording frame")
        self.encode_ms = self.diff(self.clock(), started)
        started = self.clock()
        self.write_all(self.video, data)
        self.frames += 1
        self.gap_ms = 0 if self.last_frame is None else self.diff(captured_at, self.last_frame)
        self.last_frame = captured_at
        self.write_ms = self.diff(self.clock(), started)
        self.event(captured_at, "FRAME", self.frames, len(data), self.gap_ms, self.encode_ms, self.write_ms)
        if self.diff(captured_at, self.last_flush) >= 1000:
            self.check_space()
            self.video.flush()
            self.events.flush()
            self.last_flush = captured_at
        self.total_ms = self.diff(self.clock(), began)

    def close(self, now, reason="STOP"):
        error = None
        active = self.video is not None or self.events is not None
        try:
            self.event(now, "END", reason, self.frames)
        except Exception as failure:
            error = failure
        for stream in (self.video, self.events):
            if stream is not None:
                try:
                    stream.close()
                except Exception as failure:
                    error = failure
        self.video = self.events = None
        if active:
            self.folder = None
        elif self.folder is not None:
            import os
            os.rmdir(self.folder)  # Only the empty directory reserved by this instance.
            self.folder = None
        if error is not None:
            raise error


def main():
    import gc
    import os
    import time
    from media.media import MediaManager
    from media.sensor import Sensor

    if INITIAL_TARGET_ID is not None and (
        type(INITIAL_TARGET_ID) is not int or not 0 <= INITIAL_TARGET_ID <= 9
    ):
        raise ValueError("INITIAL_TARGET_ID must be None or 0-9 for STM32")

    uart = sensor = detector = recorder = None
    media_ready = sensor_running = False
    session = VisionSession(time.ticks_diff)
    reader = CommandReader()
    confirmed = {}
    read_commands = None
    stage = "START"
    exit_reason = "EXIT"
    try:
        print("[BOOT] WONDERMK_CONTEST_TX_V6 640x480 UART3 GPIO50 TX")
        print("[BOOT] CAMERA_ONLY={} IDE_PREVIEW={}".format(CAMERA_ONLY, ENABLE_IDE_PREVIEW))
        # Set up the external UART before starting the camera's capture engine.
        if not CAMERA_ONLY:
            stage = "UART_INIT"
            uart = open_uart()
            read_commands = None if ONE_WAY else open_command_input(uart)

        stage = "SENSOR_CONFIG"
        print("[BOOT]", stage)
        sensor = Sensor(width=SENSOR_WIDTH, height=SENSOR_HEIGHT, fps=SENSOR_FPS)
        sensor.reset()
        sensor.set_vflip(VFLIP)
        sensor.set_hmirror(HMIRROR)
        sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT, chn=0)
        sensor.set_pixformat(Sensor.RGB565, chn=0)
        if not CAMERA_ONLY:
            sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT, chn=2)
            sensor.set_pixformat(Sensor.RGBP888, chn=2)
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

        first_frame = first_detection = True
        first_frame_retries = 2
        last_send = last_detect = None
        tracked_id = None
        last_status = time.ticks_ms()
        frames = command_count = detect_ms = 0
        last_command = None
        print("[BOOT] FIRST_SNAPSHOT")
        while True:
            os.exitpoint()
            stage = "COMMAND_READ"
            if read_commands is not None and detector is not None:
                for command in reader.feed(read_commands(32)):
                    before = (session.mode, session.target_id)
                    if session.command(command, time.ticks_ms()):
                        last_command = time.ticks_ms()
                        command_count += 1
                        if command_count == 1 or before != (session.mode, session.target_id):
                            print("[RX]", command.decode())
                        if before != (session.mode, session.target_id) or command == b"STOP":
                            confirmed = {}
                            last_detect = None
                        if recorder is not None:
                            stamp = time.ticks_ms()
                            if session.mode == VISION_IDLE:
                                recorder.event(stamp, "COMMAND", command.decode())
                                recorder.close(stamp)
                            else:
                                if before != (session.mode, session.target_id) and recorder.video is not None:
                                    recorder.close(stamp, "CHANGE")
                                recorder.start(session.mode, session.target_id, stamp)
                                recorder.event(stamp, "COMMAND", command.decode())
                        report_scan_result(session.take_scan_result())
                        stage = "COMMAND_REPLY"
                        send_coordinates(uart, session, confirmed)
                        last_send = time.ticks_ms()
                    else:
                        print("[RX] INVALID_COMMAND", command)

            if (session.mode in (VISION_SCAN, VISION_TRACK) and last_command is not None
                    and time.ticks_diff(time.ticks_ms(), last_command) >= COMMAND_TIMEOUT_MS):
                raise OSError("STM32 command heartbeat lost")

            stage = "SNAPSHOT"
            try:
                frame = sensor.snapshot(chn=0, timeout=3000)
                captured_at = time.ticks_ms()
            except RuntimeError as error:
                if not first_frame or not first_frame_retries or not str(error).endswith("failed(3)"):
                    raise
                first_frame_retries -= 1
                print("[RETRY] FIRST_SNAPSHOT", error)
                time.sleep_ms(100)
                continue
            frames += 1
            if first_frame:
                print("[OK] FIRST_SNAPSHOT", frame.width(), frame.height())
                if ENABLE_IDE_PREVIEW:
                    stage = "FIRST_PREVIEW"
                    frame.compress_for_ide()
                    print("[OK] FIRST_PREVIEW")
                first_frame = False
                if not CAMERA_ONLY:
                    stage = "MODEL_LOAD"
                    print("[BOOT] MODEL_PATH={}".format(MODEL_PATH))
                    detector = open_detector()
                    print("[OK] MODEL_LOADED")
                    stage = "PREPROCESS_CONFIG"
                    detector.config_preprocess()
                    print("[OK] PREPROCESS_CONFIG")
                    stage = "RECORD_PREPARE"
                    recorder = ContestRecorder(RECORD_ROOT, time.ticks_ms, time.ticks_diff)
                    print("[OK] RECORD_READY")
                    if ONE_WAY:
                        recorder.start("ALL", -1, time.ticks_ms())
                    # First normal frame is sent only after model/camera/storage are ready.
                    send_coordinates(uart, session, {})
                    last_send = time.ticks_ms()
                    print("[LINK] Broadcasting all IDs; STM32 selects target" if ONE_WAY else "[LINK] Waiting for STM32 commands")
                del frame
                continue

            if not CAMERA_ONLY:
                now = time.ticks_ms()
                if last_detect is None or time.ticks_diff(now, last_detect) >= DETECT_INTERVAL_MS:
                    stage = "RECOGNITION"
                    if first_detection:
                        print("[BOOT] FIRST_DETECTION")
                    started = time.ticks_ms()
                    stage = "AI_SNAPSHOT"
                    ai_frame = sensor.snapshot(chn=2, timeout=3000)
                    ai_input = ai_frame.to_numpy_ref()
                    try:
                        stage = "INFERENCE"
                        detections = normalize_detections(detector.run(ai_input))
                    finally:
                        del ai_input, ai_frame
                    now = time.ticks_ms()
                    detect_ms = time.ticks_diff(now, started)
                    if detect_ms > MAX_OBSERVATION_MS:
                        detections = []
                        print("[WARN] STALE_INFERENCE {} ms".format(detect_ms))
                    confirmed, new_ids, scan_result = session.observe(detections, now)
                    observation_gap = 0 if last_detect is None else time.ticks_diff(now, last_detect)
                    last_detect = now
                    selected = confirmed.get(session.target_id)
                    cx, cy = center(selected) if selected is not None else (-1, -1)
                    recorder.event(now, "OBS", session.sequence, session.target_id, cx, cy,
                                   selected[2] if selected else -1, selected[3] if selected else -1)
                    recorder.event(now, "TIMING", detect_ms, observation_gap)
                    if ONE_WAY:
                        for digit, rect in sorted(confirmed.items()):
                            recorder.event(now, "DETECTION", session.sequence, digit, *rect)
                    if first_detection:
                        print("[OK] FIRST_DETECTION", detect_ms, "ms")
                        first_detection = False
                    for digit in new_ids:
                        print("FOUND,{}".format(digit))
                    report_scan_result(scan_result)

                active_id = session.target_id if session.target_id in confirmed else None
                if tracked_id != active_id:
                    if tracked_id is not None:
                        print("LOST,{}".format(tracked_id))
                        recorder.event(now, "LOST", tracked_id)
                    if active_id is not None:
                        print("TRACK,{}".format(active_id))
                        recorder.event(now, "TRACK", active_id)
                    tracked_id = active_id
                stage = "UART_TX"
                if last_send is None or time.ticks_diff(now, last_send) >= SEND_INTERVAL_MS:
                    send_coordinates(uart, session, confirmed)
                    last_send = now
                stage = "RECORD_FRAME"
                recorder.capture(frame, captured_at)
                draw_overlay(frame, confirmed, active_id)

            if ENABLE_IDE_PREVIEW:
                stage = "PREVIEW"
                frame.compress_for_ide()
            now = time.ticks_ms()
            if time.ticks_diff(now, last_status) >= STATUS_INTERVAL_MS:
                if ONE_WAY:
                    print("[STATUS] frames={} link=TX_ALL seq={} detect_ms={} cards={}".format(
                        frames, session.sequence, detect_ms, sorted(confirmed)))
                else:
                    print("[STATUS] frames={} mode={} id={} rx_commands={} seq={} detect_ms={} cards={}".format(
                        frames, session.mode, session.target_id, command_count,
                        session.sequence, detect_ms, sorted(confirmed)))
                if recorder is not None:
                    print("[RECORD_STATUS] frames={} gap_ms={} encode_ms={} write_ms={} total_ms={}".format(
                        recorder.frames, recorder.gap_ms, recorder.encode_ms, recorder.write_ms, recorder.total_ms))
                last_status = now
            del frame
            gc.collect()
            time.sleep_ms(1)

    except KeyboardInterrupt:
        exit_reason = "INTERRUPTED"
        print("STOPPED")
    except Exception as error:
        exit_reason = "ERROR_" + stage
        # IDE interrupt must leave the loop; never silently disable detection.
        print("[ERROR]", stage, error)
        raise
    finally:
        print("[EXIT] cleanup")
        if uart is not None:
            session.mode = VISION_FAULT
            cleanup(send_coordinates, uart, session, {})
            cleanup(uart.deinit)
        if recorder is not None:
            cleanup(recorder.close, time.ticks_ms(), exit_reason)
        if detector is not None:
            cleanup(detector.deinit)
        if sensor_running:
            cleanup(sensor.stop)
        gc.collect()
        if media_ready:
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            time.sleep_ms(100)
            cleanup(MediaManager.deinit)


if __name__ == "__main__":
    main()
