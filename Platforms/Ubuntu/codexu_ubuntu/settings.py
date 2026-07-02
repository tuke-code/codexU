from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .formatting import automatic_language


@dataclass
class WidgetSettings:
    language: str = "en"
    theme: str = "system"

    @classmethod
    def load(cls) -> "WidgetSettings":
        path = _settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(language=automatic_language())

        language = data.get("language")
        theme = data.get("theme")
        return cls(
            language=language if language in {"zh", "en"} else automatic_language(),
            theme=theme if theme in {"system", "light", "dark"} else "system",
        )

    def save(self) -> None:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"language": self.language, "theme": self.theme},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _settings_path() -> Path:
    return Path.home() / ".config" / "codexu-ubuntu" / "settings.json"
