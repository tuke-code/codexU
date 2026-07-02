// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "codexU",
    defaultLocalization: "en",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "codexU", targets: ["CodexUsageWidget"])
    ],
    targets: [
        .executableTarget(
            name: "CodexUsageWidget",
            path: "Sources/CodexUsageWidget"
        )
    ]
)
