"""Convert TipTour's UIElementDetector.mlpackage (YOLO11m, CoreML mlprogram) to ONNX
without retraining: weights are read byte-for-byte from weight.bin (fp16 -> fp32).
Only the 17 MIL op types present in this model are supported; anything else raises.
The Core ML NMS stage is NOT converted (done separately in detector.py)."""
import sys, struct, numpy as np, onnx
from onnx import helper as H, TensorProto as TP, numpy_helper as NH
import coremltools as ct

PKG = sys.argv[1]; OUT = sys.argv[2]
spec = ct.models.MLModel(PKG, skip_model_load=True).get_spec()
prog = spec.pipeline.models[0].mlProgram
fn = prog.functions["main"]; ops = fn.block_specializations[fn.opset].operations
blob = open(PKG + "/Data/com.apple.CoreML/weights/weight.bin", "rb").read()
DT = {"FLOAT16": np.float16, "FLOAT32": np.float32, "INT32": np.int32, "BOOL": np.bool_}

def read_blob(off):
    magic, dtype, size, data_off = struct.unpack_from("<IIQQ", blob, off)
    assert magic == 0xDEADBEEF, hex(magic)
    return blob[data_off:data_off + size]

consts = {}
def const_val(o):
    v = o.attributes["val"]; k = v.WhichOneof("value")
    tt = v.type.tensorType; dt = TP.DataType.Name(tt.dataType) if False else None
    import coremltools.proto.MIL_pb2 as M
    dtn = M.DataType.Name(tt.dataType)
    shape = [d.constant.size for d in tt.dimensions]
    if k == "blobFileValue":
        arr = np.frombuffer(read_blob(v.blobFileValue.offset), dtype=DT[dtn]).reshape(shape)
    else:
        t = v.immediateValue.tensor; w = t.WhichOneof("value")
        if w == "bytes": arr = np.frombuffer(t.bytes.values, dtype=DT[dtn]).reshape(shape)
        elif w == "strings": return list(t.strings.values)[0] if not shape else list(t.strings.values)
        else:
            vals = list(getattr(t, w).values); arr = np.array(vals, dtype=DT.get(dtn, np.float32)).reshape(shape)
    return arr

nodes, inits = [], []
rank_cache = {}
def arg(o, name):
    a = o.inputs[name].arguments[0]
    return a.name if a.WhichOneof("binding") == "name" else None
def c(o, name):
    n = arg(o, name); return consts[n]
def as_list(x): return [int(i) for i in np.atleast_1d(x)]
def init(name, arr): inits.append(NH.from_array(np.asarray(arr), name)); return name

for o in ops:
    out = o.outputs[0].name; t = o.type
    if t == "const":
        v = const_val(o); consts[out] = v
        if isinstance(v, np.ndarray) and v.dtype == np.float16:
            init(out, v.astype(np.float32))
        continue
    I = lambda n: arg(o, n)
    if t == "cast": nodes.append(H.make_node("Identity", [I("x")], [out]))
    elif t in ("mul", "add", "sub"):
        ins = []
        for n in ("x", "y"):
            nm = I(n)
            if nm in consts and nm not in [i.name for i in inits]:
                nm = init(nm + "_f", np.asarray(consts[nm]).astype(np.float32).reshape(consts[nm].shape))
            ins.append(nm)
        nodes.append(H.make_node(t.capitalize(), ins, [out]))
    elif t == "conv":
        ins = [I("x"), I("weight")] + ([I("bias")] if "bias" in o.inputs else [])
        pt = c(o, "pad_type"); at = {"strides": as_list(c(o, "strides")), "dilations": as_list(c(o, "dilations")), "group": int(c(o, "groups"))}
        if pt == "custom":
            p = as_list(c(o, "pad")); at["pads"] = [p[0], p[2], p[1], p[3]]
        elif pt == "valid": at["pads"] = [0, 0, 0, 0]
        elif pt == "same": at["auto_pad"] = "SAME_UPPER"
        else: raise SystemExit("pad_type " + pt)
        nodes.append(H.make_node("Conv", ins, [out], **at))
    elif t == "silu":
        s = out + "_sig"; nodes += [H.make_node("Sigmoid", [I("x")], [s]), H.make_node("Mul", [I("x"), s], [out])]
    elif t == "sigmoid": nodes.append(H.make_node("Sigmoid", [I("x")], [out]))
    elif t == "split":
        sizes = init(out + "_sz", np.array(as_list(c(o, "split_sizes")), dtype=np.int64))
        nodes.append(H.make_node("Split", [I("x"), sizes], [x.name for x in o.outputs], axis=int(c(o, "axis"))))
    elif t == "concat":
        vals = [a.name for a in o.inputs["values"].arguments]
        nodes.append(H.make_node("Concat", vals, [out], axis=int(c(o, "axis"))))
    elif t == "reshape":
        sh = init(out + "_shape", np.array(as_list(c(o, "shape")), dtype=np.int64))
        nodes.append(H.make_node("Reshape", [I("x"), sh], [out]))
    elif t == "transpose": nodes.append(H.make_node("Transpose", [I("x")], [out], perm=as_list(c(o, "perm"))))
    elif t == "max_pool":
        p = as_list(c(o, "pad")); pt = c(o, "pad_type")
        at = {"kernel_shape": as_list(c(o, "kernel_sizes")), "strides": as_list(c(o, "strides")), "ceil_mode": int(bool(c(o, "ceil_mode")))}
        if pt == "custom": at["pads"] = [p[0], p[2], p[1], p[3]]
        elif pt == "same": at["auto_pad"] = "SAME_UPPER"
        nodes.append(H.make_node("MaxPool", [I("x")], [out], **at))
    elif t == "matmul":
        a, b = I("x"), I("y")
        if bool(c(o, "transpose_x")): na = out + "_ta"; nodes.append(H.make_node("Transpose", [a], [na], perm=[0, 1, 3, 2])); a = na
        if bool(c(o, "transpose_y")): nb = out + "_tb"; nodes.append(H.make_node("Transpose", [b], [nb], perm=[0, 1, 3, 2])); b = nb
        nodes.append(H.make_node("MatMul", [a, b], [out]))
    elif t == "softmax": nodes.append(H.make_node("Softmax", [I("x")], [out], axis=int(c(o, "axis"))))
    elif t == "upsample_nearest_neighbor":
        sc = init(out + "_sc", np.array([1, 1, float(c(o, "scale_factor_height")), float(c(o, "scale_factor_width"))], dtype=np.float32))
        roi = init(out + "_roi", np.array([], dtype=np.float32))
        nodes.append(H.make_node("Resize", [I("x"), roi, sc], [out], mode="nearest", coordinate_transformation_mode="asymmetric", nearest_mode="floor"))
    elif t == "slice_by_index":
        b = as_list(c(o, "begin")); e = as_list(c(o, "end")); sq = [bool(x) for x in c(o, "squeeze_mask")] if "squeeze_mask" in o.inputs else [False] * len(b)
        em = [bool(x) for x in c(o, "end_mask")] if "end_mask" in o.inputs else [False] * len(b)
        bm = [bool(x) for x in c(o, "begin_mask")] if "begin_mask" in o.inputs else [False] * len(b)
        big = 2 ** 31 - 1
        st = [0 if bm[i] else b[i] for i in range(len(b))]; en = [big if em[i] else e[i] for i in range(len(b))]
        ax = list(range(len(b)))
        # squeeze dims: end = begin+1
        en = [st[i] + 1 if sq[i] else en[i] for i in range(len(b))]
        sl = out + "_sl" if any(sq) else out
        nodes.append(H.make_node("Slice", [I("x"), init(out + "_b", np.array(st, np.int64)), init(out + "_e", np.array(en, np.int64)), init(out + "_a", np.array(ax, np.int64))], [sl]))
        if any(sq): nodes.append(H.make_node("Squeeze", [sl, init(out + "_sqa", np.array([i for i in ax if sq[i]], np.int64))], [out]))
    else: raise SystemExit("unsupported MIL op: " + t)

# fp32 scalar consts used by mul/add as raw (fp16 scalars come via bytes -> ndarray size 1)
inp = H.make_tensor_value_info("image", TP.FLOAT, [1, 3, 640, 640])
outs = [H.make_tensor_value_info("var_1423_1", TP.FLOAT, [8400, 1]), H.make_tensor_value_info("var_1427", TP.FLOAT, [8400, 4])]
g = H.make_graph(nodes, "uielement", [inp], outs, inits)
m = H.make_model(g, opset_imports=[H.make_opsetid("", 17)]); m.ir_version = 8
onnx.checker.check_model(m); onnx.save(m, OUT); print("saved", OUT, len(nodes), "nodes", len(inits), "initializers")
