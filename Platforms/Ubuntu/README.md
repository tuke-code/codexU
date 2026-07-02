# codexU Ubuntu Desktop

Native Ubuntu Desktop implementation of codexU using Python 3 and GTK4 via PyGObject.

## Supported OS

- Ubuntu Desktop 24.04 LTS or newer.
- GNOME on Wayland or X11.
- Native Ubuntu only. This target is not designed for WSL.

## Dependencies

Install common distro packages:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0
```

No Tauri, Electron, Flutter, Qt, or shared cross-platform UI framework is used.

## Run

```bash
cd Platforms/Ubuntu
python3 -m codexu_ubuntu
```

Useful data-only commands:

```bash
python3 -m codexu_ubuntu --dump-json
python3 -m codexu_ubuntu --dump-json --no-app-server
CODEX_HOME=/path/to/codex-home python3 -m codexu_ubuntu --check --no-app-server
```

## Data Sources

The Ubuntu reader is implemented independently under `Platforms/Ubuntu/codexu_ubuntu`.
It reads:

- `CODEX_HOME`, or `~/.codex` by default.
- `state_5.sqlite` or `sqlite/state_5.sqlite`.
- `sessions/**/rollout-*.jsonl`.
- `archived_sessions/*.jsonl` and nested archived session JSONL files.
- `automations/**/automation.toml`.
- Optional `codex app-server` JSON-RPC when `codex` is present in `PATH`, `/usr/bin`, `/usr/local/bin`, or `~/.local/bin`.

If the app-server is missing or fails, the widget displays local token/task data and diagnostics instead of crashing.

## Package

Build a local `.deb`:

```bash
cd Platforms/Ubuntu
./scripts/build-deb.sh
```

Install the generated package:

```bash
sudo apt install ./dist/codexu-ubuntu_0.1.0_all.deb
```

The package installs:

- `/usr/bin/codexu-ubuntu`
- `/usr/lib/codexu-ubuntu/codexu_ubuntu`
- `/usr/share/applications/codexu-ubuntu.desktop`
- `/usr/share/icons/hicolor/scalable/apps/codexu.svg`

## Verify

Headless checks suitable for CI:

```bash
cd Platforms/Ubuntu
./scripts/verify.sh
```

This compiles Python files, runs the data/parser tests, and runs a `--dump-json --no-app-server` smoke check without a display server.

## Desktop-Layer Limitations

GNOME Shell on Wayland does not expose a stable, distro-default GTK4 API for placing a normal app window on the true desktop layer, and global hotkeys are intentionally restricted by the compositor. This implementation uses the closest native behavior available without adding non-common dependencies:

- Borderless GTK4 widget window.
- Draggable by the widget background.
- Refresh and close controls in the header.
- In-app `Ctrl+R` refresh shortcut.
- Appearance toggle: system/light/dark.
- Language toggle: `zh`/`en`.

True desktop-layer pinning or global hotkeys would require compositor-specific integration or an additional protocol library such as layer-shell, which is intentionally not introduced here.

## Privacy

All parsing is local. The app reads Codex state files and optional local `codex app-server` data. It does not send usage data to a network service.
