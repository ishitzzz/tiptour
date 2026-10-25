#!/bin/bash
# Run the pure Gemini key-pool tests without building, signing, or launching TipTour.
# Works with any Swift 5/6 toolchain on macOS or Linux (no Apple frameworks needed).
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/tiptour-key-pool-tests.XXXXXX")"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/Sources/KeyPoolCore" "$test_dir/Tests/KeyPoolCoreTests"
cat > "$test_dir/Package.swift" <<'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "KeyPoolCore", platforms: [.macOS(.v14)],
    targets: [.target(name: "KeyPoolCore"), .testTarget(name: "KeyPoolCoreTests", dependencies: ["KeyPoolCore"])],
    swiftLanguageModes: [.v5]
)
SWIFT
# Only the pool itself: it gates Combine/Security/Keychain behind canImport,
# so this package also builds with a plain Linux Swift toolchain.
cp "$project_dir/TipTour/Voice/GeminiKeyPool.swift" "$test_dir/Sources/KeyPoolCore/"
sed 's/@testable import TipTour/@testable import KeyPoolCore/' \
    "$project_dir/TipTourTests/GeminiKeyPoolTests.swift" > "$test_dir/Tests/KeyPoolCoreTests/GeminiKeyPoolTests.swift"
swift test --package-path "$test_dir"
