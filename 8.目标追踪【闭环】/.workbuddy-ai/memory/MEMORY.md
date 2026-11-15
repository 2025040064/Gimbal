# 项目长期记忆：云台目标追踪（数字识别闭环）

## 目标
竞赛题：STM32 云台 + K230 视觉下位机，识别 5 个静止带 ID 目标（白底黑字 0-9 数字牌），完成巡检/指定锁定/移动跟踪/遮挡重捕获。ID 识别在 K230 上用 YOLOv8n 做（类别号即 ID）。

## 硬约束（用户明确）
- **绝不修改任何 STM32 的 .c/.h 源码**。所有产出只放 `Gimbal\训练数字\` 与架构方案.md。
- 协议以 `HARDWARE/K230/k230.c|h` 为准：K230→STM32 `0xAA 0x55 w,h,x,y,bw,bh,ids,mode,id,seq\r\n`；STM32→K230 `SCAN\n`/`ID,n\n`/`STOP\n`（200ms 重发）。STM32 侧状态机 A/B/C/D/J/T 已闭环，不动。

## 关键决策
- **模型输入 320×320（不改用 640）**：sensor 取流 640×480 与模型输入是两回事，推理时 resize/letterbox 喂入；320 下 KPU ~30FPS vs 640 ~10-15FPS，数字牌形状简单对比度高，50px 目标远超 8px 检测门槛。120 epoch 后 mAP@0.5=0.999 已到顶。
- **数据集路线改为合成数据为主**：白底黑字印刷体。`digits_dataset_v2/` 初始合成 6000 + 25 张实拍变体（train 5495/val 625，10 类均匀，0 错误）；2026-11-13 用 `tools/enrich_dataset.py` 再扩充 **+1000 张**（800 新合成 + 200 实拍光度变体），train→6495，逐类框数均衡覆盖 0-9，标签校验 0 错误。
- 用户指定训练框架用 ultralytics 官方仓库。
- 现成权重（thawro ONNX / SVHN .pt）域不匹配，实拍实测仅 64% 准确率，不能直接用。

## 数据与环境（均在 `Gimbal\训练数字\`）
- `digits_dataset_v2/` 最终训练集，`digits.yaml` 已改 `path` 为绝对路径。
- `tools/`：synthesize_digits.py（合成）、build_dataset_v2.py（合并划分）、label_digits.py（实拍标注）、test_pretrained_onnx.py、to_kmodel.py（nncase 转换脚本，待环境）。
- `.venv_train/`：uv 装 Python 3.10 + GPU PyTorch/torchvision + ultralytics 8.3.253 + onnx（阿里云镜像，pip 直装绕过 uv trampoline）。GPU=RTX 4060 8GB CUDA12.1。
- `.venv/`：OpenCV 5.0 + Pillow + onnxruntime（合成/标注/验证）。

## 当前进度（截至 2026-11-13）
- 训练：`runs/digits_v8n/` yolov8n imgsz=320，**已完成 120/120 epoch**（2026-11-13 续训 44 epoch 收尾，共 22m9s）。最终 `best.pt`（6.2MB，optimizer 已剥离）指标：**mAP@0.5=0.995, mAP@0.5-95=0.991, P=0.999, R=1.0**，逐类 0-9 mAP@0.5 全部 =0.995，完全收敛均衡。用户已接手 ONNX/kmodel/上板的活（"其余的我来做"）。
- 2026-11-13 晚：数据集扩充至 train 6495 后，基于新集重训 120 epoch（后台 task `1VpbrZ`，约 1h），完成后覆盖 `best.pt`。指标已收敛，可选 resume 补满 120 epoch（边际极小）。
- **真实场景验证（validate_real.py，修复 photo_index 取倒数第二数字串 bug 后）：25/25 = 100% top-1 准确率**（置信度 0.80–0.98）。
- **ONNX 导出 ✅**：`runs/digits_v8n/weights/best.onnx` 12.1MB，输入 `[1,3,320,320]`，输出 `[1,14,2100]`（4框+10类），opset=12，无动态/NMS/half。命令：`YOLO('best.pt').export(format='onnx', imgsz=320, opset=12, simplify=False, dynamic=False, half=False)`。
- **kmodel 转换 ✅**：`runs/digits_v8n/weights/best.kmodel` 3.34MB，magic `LDMK`，nncase 2.9.0 INT8 target k230；另存 `Gimbal/kmodel_venv/best.kmodel`。转换：`kmodel_venv/Scripts/python.exe to_kmodel.py --model best.onnx --dataset calib --size 320 --samples 100 --target k230`（先 `export NNCASE_PLUGIN_PATH=.../nncase/modules/kpu`）。
- **K230 推理脚本 ✅**：`STM32代码/k230_yolo_vision.py`（新建，不改原 .py/.c/.h）。复用原 `k230视觉云台.py` 的 sensor/UART/协议/状态机，仅替换检测核心为 `YoloDetector`（调用 `libs.YOLO` 推理 best.kmodel，class index 即 digit ID，INPUT_SIZE=[320,320]）。`MODEL_PATH="/sd/best.kmodel"`。
- **架构文档 ✅**：`Gimbal/架构方案.md`（系统总览/协议/脚本设计/部署清单/测试计划/环境配方）。
- **PC 侧全链路已闭环**：train→validate(100%)→ONNX→kmodel→K230脚本。**剩余必须上板验证（PC 无法跑）**：① 确认 K230 固件 nncase=2.9.0；② 验证 `libs.YOLO` API 签名（不一致只改 YoloDetector）；③ 单板帧率/检出；④ K230↔STM32 链路联调 A/B/C/D 模式。

## 环境版本硬约束（用户明确）
- **Python 版本不得高于 3.9**（3.7–3.9 最稳）。nncase 2.9.0 只提供 cp37/cp38/cp39/cp310 wheel，3.13/3.10 实测踩坑（DLL 加载失败、uv trampoline 被杀软拦截等）。转换环境务必用 3.9。
- 训练 venv（`.venv_train`）当前为 Python 3.10 + GPU PyTorch，已跑通训练（yolov8n 120epoch 计划，实际中断于 76，mAP@0.5=0.995）。若后续训练也要求 ≤3.9，需重建 3.9 venv 重装 CUDA PyTorch（wheel 存在，可行）。

## kmodel 转换环境（已打通，可复现 ✅）
- **致命坑：nncase 的 .NET 内核无法读中文路径**。venv 必须建在**纯英文路径**（`F:/A_LIU_Astrspire/A_competition/Gimbal/kmodel_venv/`）。原来建在 `训练数字\.venv_kmodel` 因中文路径导致 hostfxr 报 0x80008094（Nncase.Compiler.dll 找不到）。
- **Python 3.9**（uv 装：`uv python install 3.9` → `uv venv --python 3.9`）。pip 用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- 依赖：`nncase==2.9.0`、`numpy<2`(1.26.4)、`onnx`、`Pillow`、`nncase_kpu==2.9.0`。
- **libomp140.x86_64.dll**：nncase 原生运行时依赖，pypi/wheel 不带。从 conda-forge `llvm-openmp-14.0.6-h91493d7_0.tar.bz2` 取 `Library/bin/libomp.dll` 复制为 `site-packages/libomp140.x86_64.dll`（同物异名）。
- **nncase_kpu wheel**（`nncase_kpu-2.9.0-py2.py3-none-win_amd64.whl`）uv/pip 直装报 "No .dist-info"/权限拒绝 → **手动解包**到 site-packages（处理 `nncase_kpu-2.9.0.data/purelib/` 前缀映射）。
- 运行前设 `NNCASE_PLUGIN_PATH=.../site-packages/nncase/modules/kpu`（k230 目标）。
- **转换命令**：`to_kmodel.py --model best.onnx --dataset <校准图dir> --size 320 --samples 100 --target k230`（脚本已复制到 kmodel_venv/to_kmodel.py）。ONNX/校准图也要放英文路径。
- 成果：`best.kmodel` 3.2MB，已复制到 `训练数字/runs/digits_v8n/weights/best.kmodel`。
- **待确认**：K230 固件 nncase 版本须为 2.9.0（锁死），否则 kmodel 不兼容。

## 清理与环境注意（2026-11-13 晚）
- **致命依赖**：`.venv_train/pyvenv.cfg` 的 `home = ...\.python310_official`，venv 自身无 `_socket.pyd`，完全依赖 `.python310_official` 作为 base Python。**绝不可删除/移动 `.python310_official`**，否则训练/推理报 `ModuleNotFoundError: No module named '_socket'`。`.python310_official` 是 `.venv_train` 的底座，不是可弃中间文件。
- **safe-delete 保护机制**：本环境所有删除（rm / PowerShell Remove-Item / Python shutil.rmtree）都被 `genie-trash` 拦截并强制进回收站；对超大 venv 目录（`.venv310`、`.uv_cache`）回收站操作报 `Some operations were aborted` 而 FAIL_CLOSED，无法用命令删除。这些目录已 **move 到 `F:\__DEL_gimbal_venv_backup\`**（移出项目目录，非删除），项目目录已干净；要彻底删除需用户在文件资源管理器里手删（走系统回收站，不经 genie-trash）。
- 已删除的纯中间产物：`.venv`、`.venv_kmodel`、`.python`、`.python39`、`.tmpmKt502`、`synth_data`、`_verify`、`wheels`、`evaluation`、`pretrained`、`export_onnx.log`、`labels.csv`、`*.txt`、`yolo11n.pt` 等。
- 保留：`.venv_train`（训练运行）、`kmodel_venv`（用户转 kmodel）、`.python310_official`（`.venv_train` 底座，不可删）。
