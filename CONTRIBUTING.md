# Contributing

Thanks for helping improve codexU.

## Development

Validate package metadata:

```sh
swift package dump-package
```

Build the app:

```sh
make build
```

Run locally:

```sh
make run
```

Check the local data reader:

```sh
make probe
```

Run the same local checks used by CI:

```sh
make ci
```

## Pull Requests

- Keep changes focused on one bug fix or feature.
- Run `make ci` before opening a pull request when touching Swift code, packaging, or repository metadata.
- Update `README.md` or `DISTRIBUTION.md` when behavior, installation, permissions, or packaging changes.
- Update [docs/PLATFORM_STRATEGY.md](docs/PLATFORM_STRATEGY.md) when platform support status or data-location rules change.
- Avoid committing local build outputs from `build/` or `dist/`.

## Platform Boundaries

- Keep platform business code isolated in the owning platform directory.
- Do not share data models, token accounting, path resolution, parsing, or UI code across macOS, Ubuntu, and Windows.
- Keep platform-specific permissions, executable discovery, sqlite access, desktop-window behavior, and packaging inside the platform implementation.
- Do not add a platform as supported until CI builds or verifies that platform and the README documents runtime requirements.

## Privacy

codexU reads local Codex files from `~/.codex/`. Do not include real account data, thread titles, local paths, screenshots with private task names, or local SQLite data in issues or pull requests.
