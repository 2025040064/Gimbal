import os
import argparse
import numpy as np
import cv2
import onnxsim
import onnx
import nncase
import shutil
import math
import tempfile

def parse_model_input_output(model_file,input_shape):
    onnx_model = onnx.load(model_file)
    input_all = [node.name for node in onnx_model.graph.input]
    input_initializer = [node.name for node in onnx_model.graph.initializer]
    input_names = list(set(input_all) - set(input_initializer))
    input_tensors = [
        node for node in onnx_model.graph.input if node.name in input_names]

    # input
    inputs = []
    for _, e in enumerate(input_tensors):
        onnx_type = e.type.tensor_type
        input_dict = {}
        input_dict['name'] = e.name
        input_dict['dtype'] = onnx.mapping.TENSOR_TYPE_TO_NP_TYPE[onnx_type.elem_type]
        input_dict['shape'] = [(i.dim_value if i.dim_value != 0 else d) for i, d in zip(
            onnx_type.shape.dim, input_shape)]
        inputs.append(input_dict)

    return onnx_model, inputs


def onnx_simplify(model_file, dump_dir,input_shape):
    onnx_model, inputs = parse_model_input_output(model_file,input_shape)
    onnx_model = onnx.shape_inference.infer_shapes(onnx_model)
    input_shapes = {}
    for input in inputs:
        input_shapes[input['name']] = input['shape']

    onnx_model, check = onnxsim.simplify(onnx_model, input_shapes=input_shapes)
    assert check, "Simplified ONNX model could not be validated"

    model_file = os.path.join(dump_dir, 'simplified.onnx')
    onnx.save_model(onnx_model, model_file)
    return model_file


def read_model_file(model_file):
    with open(model_file, 'rb') as f:
        model_content = f.read()
    return model_content

def generate_data_ramdom(shape, batch):
    data = []
    for i in range(batch):
        data.append([np.random.randint(0, 256, shape).astype(np.uint8)])
    return data


def generate_data(shape, batch, calib_dir):
    extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    img_paths = sorted(os.path.join(calib_dir, p) for p in os.listdir(calib_dir)
                       if os.path.splitext(p)[1].lower() in extensions
                       and os.path.isfile(os.path.join(calib_dir, p)))
    if batch <= 0 or len(img_paths) < batch:
        raise ValueError('Need at least {} calibration images; found {}'.format(batch, len(img_paths)))
    data = []
    for i in np.linspace(0, len(img_paths) - 1, batch, dtype=int):
        image = cv2.imread(img_paths[i])
        if image is None:
            raise ValueError('Could not read calibration image: {}'.format(img_paths[i]))
        h, w = image.shape[:2]
        scale = min(shape[3] / w, shape[2] / h)
        new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        left = int(round((shape[3] - new_w) / 2 - 0.1))
        top = int(round((shape[2] - new_h) / 2 - 0.1))
        canvas = np.full((shape[2], shape[3], 3), 114, dtype=np.uint8)
        canvas[top:top + new_h, left:left + new_w] = cv2.resize(image, (new_w, new_h))
        img_data = np.transpose(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB), (2, 0, 1))
        data.append([img_data[np.newaxis, ...]])
    print('Calibration: {} images, first: {}, last: {}'.format(batch, img_paths[0], img_paths[-1]))
    return np.array(data)


def main():
    parser = argparse.ArgumentParser(prog="nncase")
    parser.add_argument("--target", default="k230",type=str, help='target to run,k230/cpu')
    parser.add_argument("--model",type=str, help='model file')
    parser.add_argument("--output", type=str, help='output KMODEL path (default: model path with .kmodel extension)')
    parser.add_argument("--dataset", type=str, default="../calibration_data", help='calibration_dataset')
    parser.add_argument("--input_width", type=int, default=320, help='input_width')
    parser.add_argument("--input_height", type=int, default=320, help='input_height')
    parser.add_argument("--ptq_option", type=int, default=0, help='ptq_option:0,1,2,3,4,5')
    parser.add_argument("--samples", type=int, default=50, help='number of calibration images')

    args = parser.parse_args()

    # 更新参数为32倍数
    input_width = int(math.ceil(args.input_width / 32.0)) * 32
    input_height = int(math.ceil(args.input_height / 32.0)) * 32

    # 模型的输入shape，维度要跟input_layout一致
    input_shape=[1,3,input_height,input_width]

    dump_dir = tempfile.mkdtemp(prefix='nncase_tmp_', dir='.')

    # onnx simplify
    model_file = onnx_simplify(args.model, dump_dir,input_shape)

    # compile_options
    compile_options = nncase.CompileOptions()
    compile_options.target = args.target
    # preprocess
    # 是否采用模型做预处理
    compile_options.preprocess = True
    compile_options.swapRB = False
    # 输入图像的shape
    compile_options.input_shape = input_shape
    # 模型输入格式‘uint8’或者‘float32’
    compile_options.input_type = 'uint8'

    # 如果输入是‘uint8’格式，输入反量化之后的范围
    compile_options.input_range = [0, 1]

    # 预处理的mean/std值，每个channel一个
    compile_options.mean = [0, 0, 0] 
    compile_options.std = [1, 1, 1]

    # 设置输入的layout，onnx默认‘NCHW’即可
    compile_options.input_layout = "NCHW"
    # compile_options.output_layout = "NHWC"

    # compile_options.dump_ir = True
    # compile_options.dump_asm = True
    # compile_options.dump_dir = dump_dir
    compile_options.quant_type = 'uint8'

    # compiler
    compiler = nncase.Compiler(compile_options)

    # import
    model_content = read_model_file(model_file)
    import_options = nncase.ImportOptions()
    compiler.import_onnx(model_content, import_options)

    # ptq_options
    ptq_options = nncase.PTQTensorOptions()
    ptq_options.samples_count = args.samples

    if args.ptq_option == 0:
        ptq_options.calibrate_method = 'NoClip'
        ptq_options.w_quant_type = 'uint8'
        ptq_options.quant_type = 'uint8'
    elif args.ptq_option == 1:
        ptq_options.calibrate_method = 'NoClip'
        ptq_options.w_quant_type = 'int16'
    elif args.ptq_option == 2:
        ptq_options.calibrate_method = 'NoClip'
        ptq_options.quant_type = 'int16'
    elif args.ptq_option == 3:
        ptq_options.calibrate_method = 'Kld'
        ptq_options.w_quant_type = 'uint8'
        ptq_options.quant_type = 'uint8'
    elif args.ptq_option == 4:
        ptq_options.calibrate_method = 'Kld'
        ptq_options.w_quant_type = 'int16'
    elif args.ptq_option == 5:
        ptq_options.calibrate_method = 'Kld'
        ptq_options.quant_type = 'int16'
    else:
        raise ValueError("ptq_option must be 0,1,2,3,4,5")

    # 使用随机数据进行校准
    #ptq_options.set_tensor_data(generate_data_ramdom(input_shape, ptq_options.samples_count))
    # 使用数据集进行校准
    ptq_options.set_tensor_data(generate_data(input_shape, ptq_options.samples_count, args.dataset))
    compiler.use_ptq(ptq_options)

    # compile
    compiler.compile()

    # kmodel
    kmodel = compiler.gencode_tobytes()
    base,ext=os.path.splitext(args.model)
    kmodel_name=args.output or base+".kmodel"
    with open(kmodel_name, 'wb') as f:
        f.write(kmodel)

    shutil.rmtree(dump_dir)


if __name__ == '__main__':
    main()
