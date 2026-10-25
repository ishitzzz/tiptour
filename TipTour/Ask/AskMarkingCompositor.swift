//
//  AskMarkingCompositor.swift
//  TipTour
//
//  Draws the user's scribble onto a captured screenshot. ScreenCaptureKit
//  captures exclude TipTour's own windows, so the visible focus-highlight
//  trail is never in the raw capture; it has to be composited here.
//
//  The stroke style mirrors FocusHighlightTrailView / CursorStreakTrailView
//  in OverlayWindow.swift: the same smoothed Catmull-Rom path, the same
//  three halo/bloom/core layers in the same blue, and the same quadratic
//  tail fade, so the pasted image shows the markings the user saw.
//

import AppKit
import CoreImage

enum AskMarkingCompositor {
    private static let trailPointLimit = 220
    private static let opacityFadeBandCount = 28
    private static let strokeColor = CGColor(red: 0x4F / 255, green: 0x8E / 255, blue: 0xF7 / 255, alpha: 1)

    private struct StrokeLayer {
        let lineWidthInPoints: CGFloat
        let maxStrokeOpacity: Double
        let blurRadiusInPoints: CGFloat
    }

    private static let strokeLayers: [StrokeLayer] = [
        StrokeLayer(lineWidthInPoints: 54.0, maxStrokeOpacity: 0.11, blurRadiusInPoints: 30),
        StrokeLayer(lineWidthInPoints: 32.0, maxStrokeOpacity: 0.26, blurRadiusInPoints: 12),
        StrokeLayer(lineWidthInPoints: 18.0, maxStrokeOpacity: 0.72, blurRadiusInPoints: 0)
    ]

    /// Maps a global AppKit point (bottom-left origin) into pixel
    /// coordinates of a capture whose `displayFrame` is in AppKit points.
    /// The pixel/point ratio absorbs Retina scaling.
    static func pixelPoint(
        forGlobalAppKitPoint globalPoint: CGPoint,
        displayFrame: CGRect,
        imageWidthInPixels: Int,
        imageHeightInPixels: Int
    ) -> CGPoint {
        let mapped = AskCoordinateMapping.mapped(
            globalX: Double(globalPoint.x),
            globalY: Double(globalPoint.y),
            frameMinX: Double(displayFrame.minX),
            frameMinY: Double(displayFrame.minY),
            frameWidth: Double(displayFrame.width),
            frameHeight: Double(displayFrame.height),
            pixelWidth: Double(imageWidthInPixels),
            pixelHeight: Double(imageHeightInPixels)
        )
        return CGPoint(x: mapped.x, y: mapped.y)
    }

    /// Returns the capture with the trail drawn on it, or the original
    /// capture when there is nothing to draw.
    static func compositingTrail(
        _ globalAppKitPoints: [CGPoint],
        onto image: CGImage,
        displayFrame: CGRect
    ) -> CGImage {
        let visiblePoints = globalAppKitPoints
            .suffix(trailPointLimit)
            .filter { displayFrame.insetBy(dx: -24, dy: -24).contains($0) }
        guard visiblePoints.count >= 2 else { return image }

        let scale = CGFloat(image.width) / displayFrame.width
        let pixelPoints = visiblePoints.map {
            pixelPoint(
                forGlobalAppKitPoint: $0,
                displayFrame: displayFrame,
                imageWidthInPixels: image.width,
                imageHeightInPixels: image.height
            )
        }

        let imageSize = CGSize(width: image.width, height: image.height)
        guard let baseContext = makeBitmapContext(size: imageSize) else { return image }
        baseContext.draw(image, in: CGRect(origin: .zero, size: imageSize))

        for layer in strokeLayers {
            let strokeImage = renderStrokeLayerImage(
                layer,
                pixelPoints: pixelPoints,
                imageSize: imageSize,
                scale: scale
            )
            if let strokeImage {
                baseContext.draw(strokeImage, in: CGRect(origin: .zero, size: imageSize))
            }
        }

        return baseContext.makeImage() ?? image
    }

    /// One stroke layer rendered on its own transparent canvas so the
    /// blurred layers can be blurred before landing on the base image.
    private static func renderStrokeLayerImage(
        _ layer: StrokeLayer,
        pixelPoints: [CGPoint],
        imageSize: CGSize,
        scale: CGFloat
    ) -> CGImage? {
        guard let layerContext = makeBitmapContext(size: imageSize) else { return nil }

        // Pixel coordinates are top-left-origin, but a raw CGContext's user
        // space is bottom-left-origin; flip so stroke paths land on the same
        // pixels the mapping above computed.
        layerContext.translateBy(x: 0, y: imageSize.height)
        layerContext.scaleBy(x: 1, y: -1)

        layerContext.setStrokeColor(strokeColor)
        layerContext.setLineWidth(layer.lineWidthInPoints * scale)
        layerContext.setLineCap(.butt)
        layerContext.setLineJoin(.round)

        let pointCount = pixelPoints.count
        for bandIndex in 0..<opacityFadeBandCount {
            let bandOpacity = AskCoordinateMapping.bandOpacity(
                bandIndex: bandIndex,
                bandCount: opacityFadeBandCount,
                maxOpacity: layer.maxStrokeOpacity
            )
            guard bandOpacity > 0.001 else { continue }

            let bandRange = AskCoordinateMapping.bandIndexRange(
                bandIndex: bandIndex,
                bandCount: opacityFadeBandCount,
                pointCount: pointCount
            )
            let bandStartIndex = bandRange.start
            let bandEndIndex = bandRange.end
            guard bandEndIndex > bandStartIndex else { continue }

            let bandPoints = Array(pixelPoints[bandStartIndex...bandEndIndex])
            layerContext.setAlpha(CGFloat(bandOpacity))
            layerContext.addPath(smoothedPath(through: bandPoints))
            layerContext.strokePath()
        }

        guard let strokedImage = layerContext.makeImage() else { return nil }

        if layer.blurRadiusInPoints > 0 {
            return blurredImage(strokedImage, radiusInPixels: layer.blurRadiusInPoints * scale) ?? strokedImage
        }
        return strokedImage
    }

    private static func smoothedPath(through points: [CGPoint]) -> CGPath {
        let path = CGMutablePath()
        guard points.count > 1 else { return path }

        if points.count == 2 {
            path.move(to: points[0])
            path.addLine(to: points[1])
            return path
        }

        // Centripetal-Catmull-Rom-derived cubic segments identical to
        // buildContinuousSmoothTrailPath in OverlayWindow.swift.
        path.move(to: points[0])
        let lastIndex = points.count - 1
        for segmentIndex in 0..<lastIndex {
            let segmentStart = points[segmentIndex]
            let segmentEnd = points[segmentIndex + 1]
            let pointBeforeStart = segmentIndex == 0 ? points[0] : points[segmentIndex - 1]
            let pointAfterEnd = (segmentIndex + 2) <= lastIndex ? points[segmentIndex + 2] : points[lastIndex]

            let tangentAtStart = CGPoint(
                x: (segmentEnd.x - pointBeforeStart.x) / 2.0,
                y: (segmentEnd.y - pointBeforeStart.y) / 2.0
            )
            let tangentAtEnd = CGPoint(
                x: (pointAfterEnd.x - segmentStart.x) / 2.0,
                y: (pointAfterEnd.y - segmentStart.y) / 2.0
            )

            path.addCurve(
                to: segmentEnd,
                control1: CGPoint(
                    x: segmentStart.x + tangentAtStart.x / 3.0,
                    y: segmentStart.y + tangentAtStart.y / 3.0
                ),
                control2: CGPoint(
                    x: segmentEnd.x - tangentAtEnd.x / 3.0,
                    y: segmentEnd.y - tangentAtEnd.y / 3.0
                )
            )
        }
        return path
    }

    private static func blurredImage(_ image: CGImage, radiusInPixels: CGFloat) -> CGImage? {
        let extent = CGRect(x: 0, y: 0, width: image.width, height: image.height)
        let clamped = CIImage(cgImage: image).clampedToExtent()
        guard let blurFilter = CIFilter(name: "CIGaussianBlur") else { return nil }
        blurFilter.setValue(clamped, forKey: kCIInputImageKey)
        blurFilter.setValue(radiusInPixels, forKey: kCIInputRadiusKey)
        guard let output = blurFilter.outputImage else { return nil }
        let context = CIContext(options: [.useSoftwareRenderer: false])
        return context.createCGImage(output.cropped(to: extent), from: extent)
    }

    private static func makeBitmapContext(size: CGSize) -> CGContext? {
        CGContext(
            data: nil,
            width: Int(size.width),
            height: Int(size.height),
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    }
}
