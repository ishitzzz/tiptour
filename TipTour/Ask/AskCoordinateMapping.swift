//
//  AskCoordinateMapping.swift
//  TipTour
//
//  Pure arithmetic for the ask harness, isolated without framework
//  imports beyond Foundation so it can be unit-tested on any Swift
//  toolchain.
//

import Foundation

enum AskCoordinateMapping {
    /// Maps a global AppKit point (bottom-left origin) into pixel
    /// coordinates (top-left origin) of a capture of a display whose
    /// frame is in AppKit points. The pixel/point ratio absorbs Retina
    /// scaling and secondary-display capture downscaling.
    static func mapped(
        globalX: Double,
        globalY: Double,
        frameMinX: Double,
        frameMinY: Double,
        frameWidth: Double,
        frameHeight: Double,
        pixelWidth: Double,
        pixelHeight: Double
    ) -> (x: Double, y: Double) {
        let scaleX = pixelWidth / frameWidth
        let scaleY = pixelHeight / frameHeight
        return (
            (globalX - frameMinX) * scaleX,
            (frameHeight - (globalY - frameMinY)) * scaleY
        )
    }

    /// Point-index range for one opacity band. Consecutive bands share one
    /// boundary point so butt-capped sub-paths join without a seam; the
    /// first band starts at point 0 and the last ends at pointCount - 1.
    static func bandIndexRange(
        bandIndex: Int,
        bandCount: Int,
        pointCount: Int
    ) -> (start: Int, end: Int) {
        let lastIndex = pointCount - 1
        let startFraction = Double(bandIndex) / Double(bandCount)
        let endFraction = Double(bandIndex + 1) / Double(bandCount)
        let start = max(0, Int(startFraction * Double(lastIndex)))
        let end = min(lastIndex, Int((endFraction * Double(lastIndex)).rounded(.up)))
        return (start, end)
    }

    /// Band opacity: quadratic ramp from 0 at the tail (oldest point) to
    /// maxOpacity at the head, matching the overlay trail's fade.
    static func bandOpacity(
        bandIndex: Int,
        bandCount: Int,
        maxOpacity: Double
    ) -> Double {
        let centerFraction = (Double(bandIndex) + 0.5) / Double(bandCount)
        return maxOpacity * pow(centerFraction, 1.8)
    }
}
