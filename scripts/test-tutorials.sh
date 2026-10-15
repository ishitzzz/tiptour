#!/bin/bash
# Run the pure tutorial-tour tests (Elorian answer parsing, part stitching,
# captions, prompts, client) without building, signing, or launching TipTour.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/tiptour-tutorial-tests.XXXXXX")"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/Sources/TutorialCore" "$test_dir/Tests/TutorialCoreTests"
cat > "$test_dir/Package.swift" <<'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "TutorialCore", platforms: [.macOS(.v14)],
    targets: [.target(name: "TutorialCore"), .testTarget(name: "TutorialCoreTests", dependencies: ["TutorialCore"])],
    swiftLanguageModes: [.v5]
)
SWIFT
cp "$project_dir/TipTour/Tutorials/TutorialTour.swift" "$project_dir/TipTour/Tutorials/ElorianClient.swift" \
   "$project_dir/TipTour/Utilities/KeychainStore.swift" "$test_dir/Sources/TutorialCore/"
sed 's/@testable import TipTour/@testable import TutorialCore/' \
    "$project_dir/TipTourTests/TutorialTourTests.swift" > "$test_dir/Tests/TutorialCoreTests/TutorialTourTests.swift"
swift test --package-path "$test_dir"
