# Gimbal 云台项目｜物资总表（BOM）



## 1. 项目定位与清单口径

- 项目：双轴 STM32 + K230 视觉追踪云台。
- STM32：`STM32F103C8T6`，使用 HAL；
- 视觉：仓库根目录 [k230视觉云台.py](../k230视觉云台.py)，
- 步进电机：英鹏飞 TPS 42 - 40P -5

## 2. 采购清单（保留原 Word 的 13 项）

| # | 物资 | 原清单型号/规格 | 数量 | 功能/对应模块 | 参考链接 |
|---|---|---|---|---|---|
| 1 | 微型轴承 | MR128ZZ，内径 8 mm / 外径 12 mm / 高 3.5 mm（截图商品选项为 10 只） |  | 云台旋转机构 | [原商品](https://e.tb.cn/h.RroWUt0zijFEDSQ?tk=Fm5hghltNYW) |
| 2 | OLED 显示屏 | 0.96 寸，SSD1315，I²C，商品标注 3.3 V | 1 | OLED 显示 | [原商品](https://e.tb.cn/h.RqGldJY3bZBwf6w?tk=HosFghAL2N5) |
| 3 | STM32 核心板 | STM32F103C8T6 | 1 | 主控 | [原商品](https://e.tb.cn/h.RKzAZl8ee2SLyvV?tk=nfcughAJ1EJ) |
| 4 | 24 V 电源 | 24 V 锂电池，截图商品约 2200 mAh；商品标题含“25.2 伏”，须核实标称/充满电压 | 1 组 | 电机供电候选 | [原商品](https://e.tb.cn/h.RI1PSwTh4Qr4gnR?tk=hybFghAJuuy) |
| 5 | 陀螺仪模块 | MPU6050 | 1 | 姿态数据采集与显示 | [原商品](https://e.tb.cn/h.RKA14kO1djlGxI3?tk=AV25ghAHarA) |
| 6 | 双轴摇杆 | PS2 摇杆模块（带按键） | 1 | X/Y 手动控制与按键 | [原商品](https://e.tb.cn/h.RI1M4UCV7uxRWnr?tk=HJcTghAGMEs) |
| 7 | AI 视觉板 | K230，原文可选不带屏幕版，视觉方案可替换 | 1 | 红色目标检测和串口输出 | [原商品](https://e.tb.cn/h.RqGJDC7nmrcxVBp?tk=YUAdghAFg9G) |
| 8 | Type-C 线 | USB-C 转 USB-C，原文用于 K230 供电 | 1 | K230 供电 | [原商品](https://e.tb.cn/h.RqGH88OVdBqi0DS?tk=tcH7ghAEHP5) |
| 9 | A2508H 端子线 | 2.5 mm 间距，需确定 2P/3P/4P/5P | **2 根** | 模块接线 | [原商品](https://e.tb.cn/h.RI1IOhf0y0JZnSb?tk=arEZghAxHtX) |
| 10 | PH2.0 转杜邦 2.54 母端 | **4P、5P 各 1 根** | **共 2 根** | 模块连接 | [原商品](https://e.tb.cn/h.RJrK6XOB0c4NxsE?tk=FN8bghAz17u) |
| 11 | 法兰盘 | 铝合金法兰联轴器，原商品可选多种轴径 | 2 | 两轴联轴及机械固定 | [原商品](https://e.tb.cn/h.RKASc1LYWgVWmE2?tk=qa8EghAADay) |
| 12 | 42 步进电机 | **TST42-40-40P-5**，原图标注轴径 5 mm、产品涉及闭环驱动/编码器 | **2 个** | 云台两个转轴 | [原商品](https://e.tb.cn/h.RIc1SpZpb5pIc59?tk=73DhgSa5RYl) |
| 13 | 螺丝及固定件 | M3×10：24 颗；M3×16：4 颗；M3 螺母：24 颗；M3×5+6 尼龙柱：4 颗；M3×5 尼龙柱：4 颗；另有 M3 螺母：4 颗 |  | 机构及 PCB 固定，PCB 优先尼龙柱 | 原文未提供商品链接 |





## 库内资源对应

| 类型 | 仓库位置 | 用途 |
|---|---|---|
| 采购原始电子元件 BOM | [BOM_Board1_Schematic1_2026-10-01.xlsx](../BOM_Board1_Schematic1_2026-10-01.xlsx) | PCB 元件级清单，**须进一步校验** |
| 原理图 | [原理图.pdf](../原理图.pdf) | 电气设计复核 |
| PCB 设计主文件 | [ProPrj_云台PCB文件_10.1_2026-10-01.epro](../ProPrj_云台PCB文件_10.1_2026-10-01.epro) | 立创 EDA 设计 |
| PCB 其他源/备份 | [云台PCB文件.eprj2](../云台PCB文件.eprj2) / [云台PCB文件.eprj_backup](../云台PCB文件.eprj_backup) | 保留旧版，不随意覆盖 |
| 机械结构 | [云台.step](../云台.step) / [底盘.3mf](../底盘.3mf) | 模型与打印/加工 |
| 完整功能版本 | [8.目标追踪【闭环】](../8.目标追踪【闭环】/) | STM32 HAL 软件 |
| K230 脚本 | [k230视觉云台.py](../k230视觉云台.py) | K230 端识别 |

