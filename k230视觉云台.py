# Single Red Color Tracking with UART output
# Tracks the largest red blob and sends coordinates + screen size via serial.
# 仅修复立创K230 CanMV v1.2.2串口问题，其他功能完全不变
# 新增：无目标时发送-1，所有发送数据在终端打印
# 新增：添加帧头帧尾校验，防止数据错乱

import time, os, gc, sys, math
from media.sensor import *
from media.display import *
from media.media import *
from machine import UART, FPIOA  # 仅添加了FPIOA导入

DETECT_WIDTH = 640
DETECT_HEIGHT = 480

# 红色阈值（Lab），根据实际环境可微调
red_threshold = (3, 99, 65, 35, 1, 58)

# --------------------------
# 串口帧格式定义（防止数据错乱）
# 帧结构：[0xAA][0x55][数据字符串][0x0D][0x0A]
# --------------------------
FRAME_HEADER = b'\xAA\x55'  # 2字节帧头
FRAME_TAIL = b'\x0D\x0A'    # 2字节帧尾（回车换行）

# --------------------------
# 仅添加的串口修复部分（必须）
# --------------------------
fpioa = FPIOA()
fpioa.set_function(5, FPIOA.UART2_TXD)  # IO5(17脚)=UART2_TXD
fpioa.set_function(6, FPIOA.UART2_RXD)  # IO6(20脚)=UART2_RXD

# 串口初始化（修复为K230正确写法，其他参数不变）
uart = UART(
    UART.UART2,
    baudrate=115200,
    bits=UART.EIGHTBITS,
    parity=UART.PARITY_NONE,
    stop=UART.STOPBITS_ONE
)
# --------------------------
# 串口修复部分结束
# --------------------------

sensor = None

try:
    sensor = Sensor(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.reset()
    sensor.set_vflip(True)          # 修正上下颠倒
    sensor.set_hmirror(True)        # 左右镜像（修正左右颠倒）
    sensor.set_framesize(width=DETECT_WIDTH, height=DETECT_HEIGHT)
    sensor.set_pixformat(Sensor.RGB565)

    Display.init(Display.ST7701, to_ide=True)   # LCD 显示，可改为 LT9611 若用 HDMI
    MediaManager.init()
    sensor.run()

    fps = time.clock()
    last_send_time = time.ticks_ms()   # 用于控制串口发送频率

    print("✅ 程序启动成功")
    print("✅ 串口帧格式：[AA 55] 数据 [0D 0A]")
    print("✅ 数据格式：屏幕宽,屏幕高,中心x,中心y,宽度,高度")
    print("✅ 无目标时：640,480,-1,-1,-1,-1\n")

    while True:
        fps.tick()
        os.exitpoint()
        img = sensor.snapshot()

        # 寻找所有红色色块
        blobs = img.find_blobs([red_threshold], pixels_threshold=100, area_threshold=100)

        # 每200ms发送一次数据，无论是否找到目标
        if time.ticks_diff(time.ticks_ms(), last_send_time) > 200:
            if blobs:
                # 按面积（像素数）排序，取最大的色块
                largest_blob = max(blobs, key=lambda b: b.pixels())

                # 绘制最大色块的矩形、中心十字和旋转角度
                img.draw_rectangle([v for v in largest_blob.rect()], color=(0,255,0))
                img.draw_cross(largest_blob.cx(), largest_blob.cy(), color=(0,255,0))
                img.draw_keypoints(
                    [(largest_blob.cx(), largest_blob.cy(), int(math.degrees(largest_blob.rotation())))],
                    size=20, color=(0,255,0)
                )

                # 数据格式：屏幕宽,屏幕高,中心x,中心y,宽度,高度
                data_str = "{},{},{},{},{},{}".format(
                    DETECT_WIDTH, DETECT_HEIGHT,
                    largest_blob.cx(), largest_blob.cy(),
                    largest_blob.w(), largest_blob.h()
                )
            else:
                # 无目标时，中心xy和宽高都设为-1
                data_str = "{},{},-1,-1,-1,-1".format(DETECT_WIDTH, DETECT_HEIGHT)

            # --------------------------
            # 组装完整帧（防止数据错乱的核心）
            # --------------------------
            # 1. 将数据字符串转换为字节
            data_bytes = data_str.encode('ascii')
            # 2. 组装完整帧：帧头 + 数据 + 帧尾
            full_frame = FRAME_HEADER + data_bytes + FRAME_TAIL

            # 3. 发送完整帧
            uart.write(full_frame)

            # 4. 终端打印调试信息（修正了嵌套f-string语法错误）
            print("发送数据: {}".format(data_str))
            hex_str = ' '.join(['{:02X}'.format(b) for b in full_frame])
            print("完整帧(HEX): {}\n".format(hex_str))

            last_send_time = time.ticks_ms()

        Display.show_image(img)
        gc.collect()

except KeyboardInterrupt as e:
    print("\nuser stop")
except BaseException as e:
    print("\nException '{}'".format(e))
    import sys
    sys.print_exception(e)
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    MediaManager.deinit()
