from __future__ import annotations

import locale
import re
from datetime import datetime
from pathlib import Path

from .models import TaskColumnKind


def automatic_language() -> str:
    language, _encoding = locale.getlocale()
    if language and language.lower().startswith("zh"):
        return "zh"
    return "en"


def text(language: str, zh: str, en: str) -> str:
    return zh if language == "zh" else en


def format_tokens(value: int | None) -> str:
    if value is None:
        return "--"
    abs_value = abs(float(value))
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def format_usd(value: float | None) -> str:
    if value is None:
        return "--"
    if abs(value) >= 1_000:
        return f"${value:.0f}"
    return f"${value:.2f}"


def format_compact_usd(value: float | None) -> str:
    if value is None:
        return "--"
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs_value >= 10_000:
        return f"${value / 1_000:.1f}K"
    if abs_value >= 1_000:
        return f"${value:.0f}"
    return f"${value:.0f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "--"
    if 0 < value < 1:
        return "<1%"
    return f"{round(value):.0f}%"


def time_only(value: datetime | None) -> str:
    if value is None:
        return "--"
    return value.astimezone().strftime("%H:%M")


def reset_date_time(value: datetime | None) -> str:
    if value is None:
        return "--"
    local = value.astimezone()
    today = datetime.now(local.tzinfo).date()
    if local.date() == today:
        return local.strftime("%H:%M")
    return local.strftime("%-m/%-d %H:%M")


def relative_time(value: datetime | None, language: str) -> str:
    if value is None:
        return "--"
    seconds = max(0, int((datetime.now(value.astimezone().tzinfo) - value.astimezone()).total_seconds()))
    if seconds < 60:
        return text(language, "刚刚", "just now")
    minutes = seconds // 60
    if minutes < 60:
        return text(language, f"{minutes} 分钟前", f"{minutes}m ago")
    hours = minutes // 60
    if hours < 24:
        return text(language, f"{hours} 小时前", f"{hours}h ago")
    days = hours // 24
    return text(language, f"{days} 天前", f"{days}d ago")


def normalized_title(title: str | None, fallback: str | None = None) -> str:
    raw = next(
        (
            value.strip()
            for value in (title, fallback)
            if isinstance(value, str) and value.strip()
        ),
        "Untitled",
    )
    single_line = re.sub(r"\s+", " ", raw.replace("\n", " "))
    if len(single_line) <= 48:
        return single_line
    return single_line[:45] + "..."


def short_workspace_name(path: str | None) -> str:
    if not path:
        return ""
    name = Path(path).name
    return name or path


def schedule_summary(rrule: str | None, language: str = "zh") -> str:
    if not rrule:
        return ""

    time_text = ""
    match = re.search(r"T(\d{2})(\d{2})(\d{2})", rrule)
    if match:
        time_text = f"{match.group(1)}:{match.group(2)}"

    if "FREQ=DAILY" in rrule:
        prefix = text(language, "每天", "Daily")
        return f"{prefix} {time_text}".strip()
    if "FREQ=WEEKLY" in rrule:
        prefix = text(language, "每周", "Weekly")
        return f"{prefix} {time_text}".strip()
    if "FREQ=HOURLY" in rrule:
        return text(language, "每小时", "Hourly")
    return time_text


def localized_task_column_title(kind: TaskColumnKind, language: str) -> str:
    if kind is TaskColumnKind.ACTIVE:
        return text(language, "进行中", "Active")
    if kind is TaskColumnKind.PENDING:
        return text(language, "待处理", "Pending")
    if kind is TaskColumnKind.SCHEDULED:
        return text(language, "定时", "Scheduled")
    return text(language, "完成", "Done")


def localized_day_label(label: str, language: str) -> str:
    if label == "今天":
        return text(language, "今天", "Today")
    return label


def localized_reader_message(message: str, language: str) -> str:
    if language == "zh":
        return message
    if message == "正在读取 codexU 数据":
        return "Reading codexU data"
    replacements = [
        ("未找到 codex", "Codex executable not found"),
        ("app-server 启动失败", "Failed to start app-server"),
        ("app-server 响应超时", "app-server response timed out"),
        ("未找到 Codex state_5.sqlite", "Codex state_5.sqlite not found"),
        ("SQLite 查询失败", "SQLite query failed"),
        ("未找到 Codex session 日志", "Codex session logs not found"),
        ("未找到 Codex token_count 事件", "Codex token_count events not found"),
        ("任务看板未找到 SQLite 数据源", "Task board SQLite data source not found"),
    ]
    for needle, replacement in replacements:
        if needle in message:
            return replacement
    if "app-server" in message:
        return message.replace("未知错误", "Unknown error")
    return message


def task_avatar_text(code: str, detail: str) -> str:
    if code.startswith("AUTO"):
        return "B"
    source = detail.split("·", 1)[0].strip()
    if source:
        return source[0].upper()
    return "C"
