//
//  TutorialTourLibrary.swift
//  TipTour
//
//  Saved tutorial tours live in
//  ~/Library/Application Support/TipTour/Tutorials/<tour id>/
//  as tour.json plus one PNG per step target. Building a tour costs
//  minutes and real money, so tours are kept until the user deletes them.
//

import Foundation

nonisolated enum TutorialTourLibrary {

    static var libraryDirectoryURL: URL {
        let applicationSupportURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return applicationSupportURL
            .appendingPathComponent("TipTour", isDirectory: true)
            .appendingPathComponent("Tutorials", isDirectory: true)
    }

    static func tourDirectoryURL(forTourID tourID: String) -> URL {
        libraryDirectoryURL.appendingPathComponent(tourID, isDirectory: true)
    }

    static func loadAllTours() -> [TutorialTour] {
        let tourDirectoryURLs = (try? FileManager.default.contentsOfDirectory(
            at: libraryDirectoryURL,
            includingPropertiesForKeys: nil
        )) ?? []
        let jsonDecoder = JSONDecoder()
        jsonDecoder.dateDecodingStrategy = .iso8601
        return tourDirectoryURLs
            .compactMap { tourDirectoryURL in
                guard let tourData = try? Data(contentsOf: tourDirectoryURL.appendingPathComponent("tour.json")) else { return nil }
                return try? jsonDecoder.decode(TutorialTour.self, from: tourData)
            }
            .sorted { $0.createdAt > $1.createdAt }
    }

    /// Writes the crops first, then tour.json, so a half-written tour never
    /// shows up in the list.
    static func save(_ tour: TutorialTour, targetCropPNGDataByFileName: [String: Data]) throws {
        let tourDirectoryURL = tourDirectoryURL(forTourID: tour.id)
        try FileManager.default.createDirectory(at: tourDirectoryURL, withIntermediateDirectories: true)
        for (cropFileName, cropPNGData) in targetCropPNGDataByFileName {
            try cropPNGData.write(to: tourDirectoryURL.appendingPathComponent(cropFileName), options: .atomic)
        }
        let jsonEncoder = JSONEncoder()
        jsonEncoder.dateEncodingStrategy = .iso8601
        jsonEncoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try jsonEncoder.encode(tour).write(to: tourDirectoryURL.appendingPathComponent("tour.json"), options: .atomic)
    }

    static func delete(_ tour: TutorialTour) {
        try? FileManager.default.removeItem(at: tourDirectoryURL(forTourID: tour.id))
    }

    static func targetCropPNGData(for tutorialTourStep: TutorialTourStep, in tour: TutorialTour) -> Data? {
        guard let cropFileName = tutorialTourStep.targetCropFileName else { return nil }
        return try? Data(contentsOf: tourDirectoryURL(forTourID: tour.id).appendingPathComponent(cropFileName))
    }
}
