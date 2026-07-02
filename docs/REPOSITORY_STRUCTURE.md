# Repository Structure

codexU is organized as a multi-platform native desktop repository. Each supported operating system owns its implementation, data readers, UI, packaging, and verification commands.

## Current Layout

```text
.
├── Package.swift                 # SwiftPM package metadata
├── Makefile                      # Local build, packaging, and CI entrypoints
├── Sources/
│   └── CodexUsageWidget/         # macOS SwiftUI/AppKit implementation
├── Platforms/
│   ├── Ubuntu/                   # Ubuntu Desktop GTK4/PyGObject implementation
│   └── Windows/                  # Windows .NET WPF implementation
├── Resources/                    # macOS app bundle resources
├── scripts/                      # DMG packaging and notarization helpers
├── docs/                         # Architecture, design, and release notes
└── .github/                      # CI, release, issue, PR, and ownership metadata
```

## Build Outputs

Generated outputs stay out of git:

- `build/`
- `dist/`
- `.build/`
- `.swiftpm/`
- `*.dmg`
- `Platforms/Ubuntu/dist/`
- `Platforms/Windows/artifacts/`

Release artifacts should be attached to GitHub Releases or CI artifacts instead of committed.

## Platform Rules

Use these rules when changing existing platforms or adding additional app surfaces:

- Keep platform business code isolated by directory.
- Do not share parsing, pricing, path resolution, or data-reader code across macOS, Ubuntu, and Windows.
- Treat the macOS implementation and [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) as product/design references, not as shared code.
- Keep platform-specific file locations, executable discovery, permissions, window behavior, and packaging inside the owning platform directory.
- Add CI coverage for every supported platform before marking it supported.

## Platform Commands

```text
make ci                          # macOS CI checks
make ci-ubuntu                   # Ubuntu headless checks
make package-ubuntu              # Ubuntu .deb
make ci-windows                  # Windows WPF build check, requires pwsh/dotnet
make package-windows             # Windows self-contained zip, requires pwsh/dotnet
```

GitHub Actions runs these checks on native runners where required.
