from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodexDataLocations:
    codex_home: Path

    @classmethod
    def current(cls, codex_home: str | Path | None = None) -> "CodexDataLocations":
        if codex_home is not None:
            return cls(Path(codex_home).expanduser())

        override = os.environ.get("CODEX_HOME", "").strip()
        if override:
            return cls(Path(override).expanduser())

        return cls(Path.home() / ".codex")

    @property
    def state_database_candidates(self) -> list[Path]:
        return [
            self.codex_home / "state_5.sqlite",
            self.codex_home / "sqlite" / "state_5.sqlite",
        ]

    @property
    def automations_directory(self) -> Path:
        return self.codex_home / "automations"

    @property
    def session_rollout_patterns(self) -> list[str]:
        return [
            "sessions/**/rollout-*.jsonl",
            "archived_sessions/*.jsonl",
            "archived_sessions/**/*.jsonl",
        ]

    def first_existing_database(self) -> Path | None:
        for candidate in self.state_database_candidates:
            if candidate.exists():
                return candidate
        return None

    def discover_session_logs(self) -> list[Path]:
        discovered: list[Path] = []
        seen: set[Path] = set()
        for pattern in self.session_rollout_patterns:
            for path in self.codex_home.glob(pattern):
                resolved = path.expanduser()
                if resolved.is_file() and resolved not in seen:
                    seen.add(resolved)
                    discovered.append(resolved)
        return discovered
