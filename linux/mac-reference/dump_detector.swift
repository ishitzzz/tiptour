// Mac-side reference dump for the Linux detector parity check. UNTESTED here (no Swift toolchain in the Linux sandbox).
// Usage:  xcrun coremlcompiler compile TipTour/UIElementDetector.mlpackage /tmp/mlc
//         swiftc -O dump_detector.swift -o dump_detector && ./dump_detector /tmp/mlc/UIElementDetector.mlmodelc icons.png > mac-detections.json
// Mirrors NativeElementDetector.swift: VNCoreMLRequest, imageCropAndScaleOption = .scaleFill, confidence >= 0.25,
// Vision bottom-left normalized box -> top-left pixels.
import Foundation, CoreML, Vision, AppKit
let args = CommandLine.arguments
guard args.count == 3, let nsImage = NSImage(contentsOfFile: args[2]),
      let cg = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil) else { fatalError("usage: dump_detector <model.mlmodelc> <image.png>") }
let model = try VNCoreMLModel(for: MLModel(contentsOf: URL(fileURLWithPath: args[1])))
let req = VNCoreMLRequest(model: model); req.imageCropAndScaleOption = .scaleFill
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
let W = Double(cg.width), H = Double(cg.height)
let rows = (req.results as? [VNRecognizedObjectObservation] ?? []).filter { $0.confidence >= 0.25 }.map { o -> [String: Double] in
    let b = o.boundingBox
    return ["conf": Double(o.confidence), "x": b.origin.x * W, "y": (1 - b.origin.y - b.height) * H, "w": b.width * W, "h": b.height * H]
}.sorted { $0["conf"]! > $1["conf"]! }
print(String(data: try JSONSerialization.data(withJSONObject: ["image": args[2], "width": W, "height": H, "detections": rows], options: [.prettyPrinted]), encoding: .utf8)!)
