# codexU for Windows

Native Windows desktop widget for codexU, implemented with .NET 8 WPF.

## Supported OS

- Windows 10 1903 or later
- Windows 11
- Native Windows desktop only. WSL is not a supported runtime target.

## Prerequisites

- .NET 8 SDK to build from source
- Optional: Codex CLI or Codex Windows app on `PATH` for account quota reads through `codex app-server`
- Local Codex data under `%USERPROFILE%\.codex`, or set `CODEX_HOME` to another Codex home directory

The app reads:

- `state_5.sqlite`
- `sqlite\state_5.sqlite`
- `sessions\**\rollout-*.jsonl`
- `archived_sessions\*.jsonl`
- `automations\**\automation.toml`

If `codex app-server` is unavailable or fails, the widget shows a diagnostic and continues with local token and task-board data.

## Run

```powershell
cd Platforms\Windows\CodexU.Windows
dotnet run
```

## Build

```powershell
cd Platforms\Windows
.\scripts\verify.ps1
```

## Package zip

Framework-dependent:

```powershell
cd Platforms\Windows
.\scripts\package-zip.ps1
```

Self-contained:

```powershell
cd Platforms\Windows
.\scripts\package-zip.ps1 -SelfContained
```

The zip is written under `Platforms\Windows\artifacts`.

## Widget behavior

- Borderless WPF window
- Top-right placement on first launch
- Drag by the header area
- Refresh button
- Close button hides to tray
- Tray menu: show/hide, pin topmost, refresh, quit
- Global hotkey: `Ctrl+Alt+U`
- Language toggle: Chinese / English
- Appearance: system / light / dark

## Desktop-layer limitation

Windows does not provide a safe, supported equivalent to the macOS desktop-window layer for a normal WPF application. This build implements the closest native behavior:

- Normal desktop widget mode: borderless tool window, hidden from the taskbar and Alt-Tab, restored from tray
- Pinned mode: WPF `Topmost=true`

The app intentionally does not attach itself behind desktop icons or to Explorer's undocumented WorkerW/Progman windows because that path is fragile across Windows updates and can break shell behavior.

## Privacy

All data is read locally from the Codex home directory and optional local `codex app-server` process. The Windows widget does not send telemetry or upload local session data.

## Installer status

This worker-owned implementation ships zip packaging only. MSI/MSIX packaging is left for a future repo-level packaging pass because it usually requires signing and installer-specific project wiring.
