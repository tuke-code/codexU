# Platform Strategy

codexU ships native desktop widgets for each supported operating system. Platform implementations are intentionally isolated so Ubuntu, Windows, and macOS can follow their own native UI, packaging, permissions, and desktop-integration rules without sharing business code.

## Support Matrix

| Platform | Status | Notes |
| --- | --- | --- |
| macOS 14+ | Supported | SwiftUI/AppKit desktop widget packaged as DMG. |
| Ubuntu Desktop 24.04+ | Supported | Native GTK4 desktop widget packaged as `.deb`. |
| Windows 10 1903+ / Windows 11 | Supported | Native .NET WPF desktop widget packaged as a release zip. |

Do not mark a platform as supported until CI builds it and the README documents install, permissions, and known limitations.

## Target Architecture

```text
Sources/CodexUsageWidget/
  macOS implementation using SwiftUI/AppKit.

Platforms/Ubuntu/
  Ubuntu Desktop implementation using native GTK.

Platforms/Windows/
  Windows implementation using native WPF.
```

Each platform owns its UI, data readers, path discovery, process execution, packaging, and tests. Code may use the macOS implementation and this document as a product reference, but platform business logic should not be shared through a common module.

## Platform Data Contract

Each platform should independently implement these defaults unless the Codex runtime changes:

- `CODEX_HOME` overrides the Codex data directory when set.
- macOS and Linux default to `$HOME/.codex`.
- Windows defaults to `%USERPROFILE%\.codex`.
- SQLite candidates are `state_5.sqlite` and `sqlite/state_5.sqlite` under the Codex data directory.
- Session candidates are `sessions/**/rollout-*.jsonl` and `archived_sessions/*.jsonl`.
- Automation candidates are `automations/**/automation.toml`.
- Account and quota data should use `codex app-server` when that command is available on the platform.
- If `codex app-server` is unavailable or fails, the app should show a clear diagnostic and continue with local-only data when possible.

## Native Platform Rules

- Ubuntu should target current Ubuntu Desktop conventions first: GTK, `.desktop` launcher metadata, and `.deb` packaging.
- Windows should target current native Windows conventions first: WPF, tray integration where useful, Win32 hotkeys where safe, and zipped published artifacts.
- macOS remains SwiftUI/AppKit with DMG packaging.
- Desktop-layer behavior is platform-specific. If the OS does not expose a reliable desktop layer, implement the closest native behavior and document the limitation.
- Bilingual Chinese/English UI is required on every platform.
- Design tokens and visual hierarchy should follow [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md), adapted to native controls and platform constraints.

## Release Expectations

Every supported platform should provide:

- A local run command.
- A CI-safe verification command.
- A packaging command.
- Clear privacy notes.
- Documented OS limitations for window layering, global hotkeys, tray/menu integration, and local Codex data access.
