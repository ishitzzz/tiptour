import XCTest
@testable import TipTour

final class AskCoordinateMappingTests: XCTestCase {

    func testRetinaDisplayMapsCenterToPixelCenter() {
        let mapped = AskCoordinateMapping.mapped(
            globalX: 756, globalY: 491,
            frameMinX: 0, frameMinY: 0, frameWidth: 1512, frameHeight: 982,
            pixelWidth: 3024, pixelHeight: 1964
        )
        XCTAssertEqual(mapped.x, 1512, accuracy: 0.001)
        XCTAssertEqual(mapped.y, 982, accuracy: 0.001)
    }

    func testAppKitTopEdgeMapsToPixelRowZero() {
        let mapped = AskCoordinateMapping.mapped(
            globalX: 100, globalY: 982,
            frameMinX: 0, frameMinY: 0, frameWidth: 1512, frameHeight: 982,
            pixelWidth: 3024, pixelHeight: 1964
        )
        XCTAssertEqual(mapped.x, 200, accuracy: 0.001)
        XCTAssertEqual(mapped.y, 0, accuracy: 0.001)
    }

    func testSecondaryDisplayWithNegativeOrigin() {
        let mapped = AskCoordinateMapping.mapped(
            globalX: -1440, globalY: 0,
            frameMinX: -1440, frameMinY: 0, frameWidth: 1440, frameHeight: 900,
            pixelWidth: 2560, pixelHeight: 1600
        )
        XCTAssertEqual(mapped.x, 0, accuracy: 0.001)
        XCTAssertEqual(mapped.y, 1600, accuracy: 0.001)
    }

    func testDownscaledCaptureMapsProportionally() {
        let mapped = AskCoordinateMapping.mapped(
            globalX: 360, globalY: 450,
            frameMinX: 0, frameMinY: 0, frameWidth: 1440, frameHeight: 900,
            pixelWidth: 1280, pixelHeight: 800
        )
        XCTAssertEqual(mapped.x, 320, accuracy: 0.001)
        XCTAssertEqual(mapped.y, 400, accuracy: 0.001)
    }

    func testBandRangesTilePointListWithoutGaps() {
        for pointCount in [2, 3, 29, 220] {
            let bandCount = 28
            let ranges = (0..<bandCount).map {
                AskCoordinateMapping.bandIndexRange(bandIndex: $0, bandCount: bandCount, pointCount: pointCount)
            }
            XCTAssertEqual(ranges.first?.start, 0, "pointCount \(pointCount)")
            XCTAssertEqual(ranges.last?.end, pointCount - 1, "pointCount \(pointCount)")
            for band in 0..<(bandCount - 1) {
                XCTAssertGreaterThanOrEqual(ranges[band].end, ranges[band + 1].start,
                                            "gap between bands \(band) and \(band + 1), pointCount \(pointCount)")
            }
        }
    }

    func testBandOpacityRampsFromTailToHead() {
        let bandCount = 28
        var previous = 0.0
        for band in 0..<bandCount {
            let opacity = AskCoordinateMapping.bandOpacity(bandIndex: band, bandCount: bandCount, maxOpacity: 0.72)
            XCTAssertGreaterThanOrEqual(opacity, previous)
            previous = opacity
        }
        XCTAssertLessThan(
            AskCoordinateMapping.bandOpacity(bandIndex: 0, bandCount: bandCount, maxOpacity: 0.72),
            0.003
        )
        let head = AskCoordinateMapping.bandOpacity(bandIndex: bandCount - 1, bandCount: bandCount, maxOpacity: 0.72)
        XCTAssertGreaterThan(head, 0.69)
        XCTAssertLessThanOrEqual(head, 0.72)
    }
}
