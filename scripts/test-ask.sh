#!/bin/bash
# Run the pure ask-harness tests without building, signing, or launching TipTour.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/tiptour-ask-tests.XXXXXX")"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/Sources/AskCore" "$test_dir/Tests/AskCoreTests"
cat > "$test_dir/Package.swift" <<'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "AskCore", platforms: [.macOS(.v14)],
    targets: [.target(name: "AskCore"), .testTarget(name: "AskCoreTests", dependencies: ["AskCore"])],
    swiftLanguageModes: [.v5]
)
SWIFT
cp "$project_dir/TipTour/Ask/AskCoordinateMapping.swift" "$test_dir/Sources/AskCore/"
sed 's/@testable import TipTour/@testable import AskCore/' \
    "$project_dir/TipTourTests/AskCoordinateMappingTests.swift" > "$test_dir/Tests/AskCoreTests/AskCoordinateMappingTests.swift"
swift test --package-path "$test_dir"
