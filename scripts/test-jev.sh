#!/bin/bash
# Run the pure JEV tests without building, signing, or launching TipTour.
#
# Requirements (checked below, with a clear error instead of a confusing
# compiler failure):
#   - macOS: the copied sources use Apple's Security framework (KeychainStore)
#     and CoreGraphics, so this harness is not portable to Linux.
#   - Swift toolchain >= 6.1 (Xcode 16.4+): the sources use type-level
#     `nonisolated`, which earlier toolchains reject.
set -euo pipefail

if [ "$(uname -s)" != "Darwin" ]; then
    echo "error: scripts/test-jev.sh requires macOS (Security/Keychain and CoreGraphics are Apple-only)." >&2
    exit 1
fi
if ! command -v swift >/dev/null 2>&1; then
    echo "error: no Swift toolchain found. Install Xcode 16.4+ (Swift 6.1) or select it with xcode-select." >&2
    exit 1
fi
swift_version="$(swift --version 2>/dev/null | sed -n 's/.*Swift version \([0-9][0-9.]*\).*/\1/p' | head -n 1)"
if ! awk -v v="$swift_version" 'BEGIN { split(v, a, "."); exit !((a[1] + 0) > 6 || ((a[1] + 0) == 6 && (a[2] + 0) >= 1)) }'; then
    echo "error: Swift >= 6.1 required (found: ${swift_version:-unknown}); the sources use type-level nonisolated." >&2
    exit 1
fi

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/tiptour-jev-tests.XXXXXX")"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/Sources/JevCore" "$test_dir/Tests/JevCoreTests"
cat > "$test_dir/Package.swift" <<'SWIFT'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "JevCore", platforms: [.macOS(.v14)],
    targets: [.target(name: "JevCore"), .testTarget(name: "JevCoreTests", dependencies: ["JevCore"])],
    swiftLanguageModes: [.v5]
)
SWIFT
cp "$project_dir/TipTour/Jev/JevClient.swift" "$project_dir/TipTour/Jev/JevGrounding.swift" "$project_dir/TipTour/Jev/JevConnection.swift" \
   "$project_dir/TipTour/Perception/LocalTargetContinuity.swift" "$project_dir/TipTour/Core/TipTourMode.swift" "$project_dir/TipTour/Utilities/KeychainStore.swift" "$test_dir/Sources/JevCore/"
sed 's/@testable import TipTour/@testable import JevCore/' \
    "$project_dir/TipTourTests/JevTests.swift" > "$test_dir/Tests/JevCoreTests/JevTests.swift"
swift test --package-path "$test_dir"
