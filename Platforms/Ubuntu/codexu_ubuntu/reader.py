from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Ubuntu 24.04 includes tomllib.
    tomllib = None  # type: ignore[assignment]

from .app_server import read_app_server
from .formatting import (
    normalized_title,
    schedule_summary,
    short_workspace_name,
)
from .locations import CodexDataLocations
from .models import (
    DailyTokenBucket,
    DetailedUsage,
    LocalThread,
    LocalUsage,
    PricedTokenUsage,
    TaskBoard,
    TaskColumn,
    TaskColumnKind,
    TaskItem,
    TokenBreakdown,
    UsageSnapshot,
)
from .pricing import estimated_cost_usd, model_token_price


@dataclass(frozen=True)
class SessionUsageSource:
    path: Path
    model: str | None = None


@dataclass(frozen=True)
class SessionUsageDelta:
    date: datetime
    tokens: TokenBreakdown


@dataclass(frozen=True)
class SessionUsageParseResult:
    has_token_events: bool
    token_event_count: int
    deltas: list[SessionUsageDelta]


@dataclass
class DetailedUsageAccumulator:
    today: PricedTokenUsage = field(default_factory=PricedTokenUsage)
    seven_day: PricedTokenUsage = field(default_factory=PricedTokenUsage)
    month: PricedTokenUsage = field(default_factory=PricedTokenUsage)
    lifetime: PricedTokenUsage = field(default_factory=PricedTokenUsage)
    parsed_file_count: int = 0
    token_event_count: int = 0

    def add(
        self,
        tokens: TokenBreakdown,
        at: datetime,
        model: str | None,
        day_start: datetime,
        seven_day_start: datetime,
        month_start: datetime,
    ) -> None:
        price = model_token_price(model)
        cost = estimated_cost_usd(tokens, price)
        self.lifetime.add(tokens, cost)
        if at >= month_start:
            self.month.add(tokens, cost)
        if at >= seven_day_start:
            self.seven_day.add(tokens, cost)
        if at >= day_start:
            self.today.add(tokens, cost)

    def make_usage(self) -> DetailedUsage:
        return DetailedUsage(
            today=self.today,
            seven_day=self.seven_day,
            month=self.month,
            lifetime=self.lifetime,
            parsed_file_count=self.parsed_file_count,
            token_event_count=self.token_event_count,
        )


class CodexUsageReader:
    def __init__(
        self,
        codex_home: str | Path | None = None,
        *,
        enable_app_server: bool = True,
    ) -> None:
        self.locations = CodexDataLocations.current(codex_home)
        self.enable_app_server = enable_app_server

    def load(self) -> UsageSnapshot:
        messages: list[str] = []

        app_server = None
        if self.enable_app_server:
            app_server = read_app_server()
            messages.extend(app_server.messages)
        else:
            messages.append("已跳过 codex app-server")

        local = self.read_local_usage(messages)
        task_board = self.read_task_board(messages)

        return UsageSnapshot(
            refreshed_at=datetime.now().astimezone(),
            account=app_server.account if app_server else None,
            limit_id=app_server.limit_id if app_server else None,
            limit_name=app_server.limit_name if app_server else None,
            primary=app_server.primary if app_server else None,
            secondary=app_server.secondary if app_server else None,
            credits=app_server.credits if app_server else None,
            cloud_lifetime_tokens=(
                app_server.cloud_lifetime_tokens if app_server else None
            ),
            local=local,
            task_board=task_board,
            messages=messages,
        )

    def load_task_board(self) -> TaskBoard | None:
        messages: list[str] = []
        return self.read_task_board(messages)

    def read_local_usage(self, messages: list[str]) -> LocalUsage | None:
        db_path = self.locations.first_existing_database()
        if db_path is None:
            messages.append("未找到 Codex state_5.sqlite")
            return None

        now = datetime.now().astimezone()
        day_start = _start_of_day(now)
        seven_day_start = day_start - timedelta(days=6)

        try:
            with _connect_readonly(db_path) as connection:
                columns = _table_columns(connection, "threads")
                if not columns:
                    messages.append("SQLite 查询失败：未找到 threads 表")
                    return None

                totals = self._read_thread_totals(
                    connection,
                    columns,
                    day_start,
                    seven_day_start,
                )
                recent_threads = self._read_recent_threads(connection, columns)
                daily_buckets = self._read_daily_buckets(
                    connection,
                    columns,
                    day_start,
                    seven_day_start,
                )
                detailed_usage = self._read_detailed_usage(
                    connection,
                    columns,
                    day_start,
                    seven_day_start,
                    messages,
                )
        except sqlite3.Error as error:
            messages.append(f"SQLite 查询失败：{error}")
            return None

        return LocalUsage(
            lifetime_tokens=_int_value(totals.get("lifetimeTokens")) or 0,
            today_tokens=_int_value(totals.get("todayTokens")) or 0,
            seven_day_tokens=_int_value(totals.get("sevenDayTokens")) or 0,
            thread_count=_int_value(totals.get("threadCount")) or 0,
            last_updated_at=_date_from_epoch(totals.get("lastUpdatedAt")),
            daily_buckets=daily_buckets,
            recent_threads=recent_threads,
            detailed_usage=detailed_usage,
        )

    def _read_thread_totals(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
        day_start: datetime,
        seven_day_start: datetime,
    ) -> dict[str, Any]:
        tokens = _numeric_column(columns, "tokens_used", "0")
        updated = _numeric_column(columns, "updated_at", "0")
        query = f"""
        SELECT
          COALESCE(SUM({tokens}), 0) AS lifetimeTokens,
          COALESCE(SUM(CASE WHEN {updated} >= ? THEN {tokens} ELSE 0 END), 0)
            AS todayTokens,
          COALESCE(SUM(CASE WHEN {updated} >= ? THEN {tokens} ELSE 0 END), 0)
            AS sevenDayTokens,
          COUNT(*) AS threadCount,
          COALESCE(MAX({updated}), 0) AS lastUpdatedAt
        FROM threads;
        """
        row = connection.execute(
            query,
            (int(day_start.timestamp()), int(seven_day_start.timestamp())),
        ).fetchone()
        return dict(row or {})

    def _read_recent_threads(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
    ) -> list[LocalThread]:
        id_column = _text_column(columns, "id", "''")
        title_column = _text_column(columns, "title", "''")
        tokens = _numeric_column(columns, "tokens_used", "0")
        updated = _numeric_column(columns, "updated_at", "0")
        model_column = _text_column(columns, "model", "NULL")
        cwd_column = _text_column(columns, "cwd", "''")
        archived = _numeric_column(columns, "archived", "0")

        query = f"""
        SELECT
          {id_column} AS id,
          {title_column} AS title,
          {tokens} AS tokens,
          {updated} AS updatedAt,
          {model_column} AS model,
          {cwd_column} AS cwd,
          {archived} AS archived
        FROM threads
        ORDER BY {updated} DESC
        LIMIT 5;
        """

        rows = connection.execute(query).fetchall()
        return [
            LocalThread(
                id=str(row["id"] or ""),
                title=normalized_title(str(row["title"] or "Untitled")),
                tokens=_int_value(row["tokens"]) or 0,
                updated_at=_date_from_epoch(row["updatedAt"]),
                model=str(row["model"]) if row["model"] is not None else None,
                cwd=str(row["cwd"] or ""),
                archived=(_int_value(row["archived"]) or 0) != 0,
            )
            for row in rows
        ]

    def _read_daily_buckets(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
        day_start: datetime,
        seven_day_start: datetime,
    ) -> list[DailyTokenBucket]:
        tokens = _numeric_column(columns, "tokens_used", "0")
        updated = _numeric_column(columns, "updated_at", "0")
        query = f"""
        SELECT
          date({updated}, 'unixepoch', 'localtime') AS day,
          COALESCE(SUM({tokens}), 0) AS tokens
        FROM threads
        WHERE {updated} >= ?
        GROUP BY day
        ORDER BY day ASC;
        """
        rows = connection.execute(query, (int(seven_day_start.timestamp()),)).fetchall()
        tokens_by_day = {
            str(row["day"]): _int_value(row["tokens"]) or 0
            for row in rows
            if row["day"] is not None
        }

        buckets: list[DailyTokenBucket] = []
        for index in range(7):
            date = day_start + timedelta(days=index - 6)
            key = date.strftime("%Y-%m-%d")
            label = "今天" if index == 6 else f"{date.month}/{date.day}"
            buckets.append(
                DailyTokenBucket(
                    id=key,
                    label=label,
                    tokens=tokens_by_day.get(key, 0),
                )
            )
        return buckets

    def _read_detailed_usage(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
        day_start: datetime,
        seven_day_start: datetime,
        messages: list[str],
    ) -> DetailedUsage | None:
        sources = self._session_sources_from_database(connection, columns)
        sources.extend(self._session_sources_from_filesystem(sources))

        if not sources:
            messages.append("未找到 Codex session 日志")
            return None

        now = datetime.now().astimezone()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        accumulator = DetailedUsageAccumulator()

        for source in sources:
            parsed = parse_session_usage(source.path)
            if parsed is None:
                continue
            if parsed.has_token_events:
                accumulator.parsed_file_count += 1
                accumulator.token_event_count += parsed.token_event_count
            for delta in parsed.deltas:
                accumulator.add(
                    delta.tokens,
                    at=delta.date,
                    model=source.model,
                    day_start=day_start,
                    seven_day_start=seven_day_start,
                    month_start=month_start,
                )

        if accumulator.parsed_file_count == 0 or accumulator.token_event_count == 0:
            messages.append("未找到 Codex token_count 事件")
            return None

        return accumulator.make_usage()

    def _session_sources_from_database(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
    ) -> list[SessionUsageSource]:
        if "rollout_path" not in columns:
            return []

        tokens = _numeric_column(columns, "tokens_used", "0")
        model = _text_column(columns, "model", "NULL")
        query = f"""
        SELECT rollout_path AS rolloutPath, {model} AS model
        FROM threads
        WHERE rollout_path IS NOT NULL
          AND rollout_path <> ''
          AND {tokens} > 0
        ORDER BY {_numeric_column(columns, "updated_at", "0")} ASC;
        """
        rows = connection.execute(query).fetchall()

        sources: list[SessionUsageSource] = []
        seen: set[Path] = set()
        for row in rows:
            raw_path = row["rolloutPath"]
            if not raw_path:
                continue
            path = _normalize_session_path(self.locations.codex_home, str(raw_path))
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            sources.append(
                SessionUsageSource(
                    path=path,
                    model=str(row["model"]) if row["model"] is not None else None,
                )
            )
        return sources

    def _session_sources_from_filesystem(
        self,
        existing_sources: list[SessionUsageSource],
    ) -> list[SessionUsageSource]:
        seen = {source.path for source in existing_sources}
        sources: list[SessionUsageSource] = []
        for path in self.locations.discover_session_logs():
            if path in seen:
                continue
            seen.add(path)
            sources.append(SessionUsageSource(path=path, model=None))
        return sources

    def read_task_board(self, messages: list[str]) -> TaskBoard | None:
        now = datetime.now().astimezone()
        day_start = _start_of_day(now)
        active_cutoff = now - timedelta(hours=2)

        active_items: list[TaskItem] = []
        pending_items: list[TaskItem] = []
        done_items: list[TaskItem] = []

        db_path = self.locations.first_existing_database()
        if db_path is None:
            messages.append("任务看板未找到 SQLite 数据源")
        else:
            try:
                with _connect_readonly(db_path) as connection:
                    columns = _table_columns(connection, "threads")
                    if columns:
                        active_items, pending_items = self._read_open_task_items(
                            connection,
                            columns,
                            day_start,
                            active_cutoff,
                        )
                        done_items = self._read_done_task_items(
                            connection,
                            columns,
                            day_start,
                        )
                    else:
                        messages.append("任务看板未找到 SQLite 数据源")
            except sqlite3.Error as error:
                messages.append(f"任务看板 SQLite 查询失败：{error}")

        scheduled_items = self.read_automation_tasks()

        return TaskBoard(
            refreshed_at=datetime.now().astimezone(),
            columns=[
                TaskColumn(
                    id=TaskColumnKind.ACTIVE,
                    title="进行中",
                    count=len(active_items),
                    items=active_items[:3],
                ),
                TaskColumn(
                    id=TaskColumnKind.PENDING,
                    title="待处理",
                    count=len(pending_items),
                    items=pending_items[:3],
                ),
                TaskColumn(
                    id=TaskColumnKind.SCHEDULED,
                    title="定时",
                    count=len(scheduled_items),
                    items=scheduled_items[:3],
                ),
                TaskColumn(
                    id=TaskColumnKind.DONE,
                    title="完成",
                    count=len(done_items),
                    items=done_items[:3],
                ),
            ],
        )

    def _read_open_task_items(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
        day_start: datetime,
        active_cutoff: datetime,
    ) -> tuple[list[TaskItem], list[TaskItem]]:
        id_column = _text_column(columns, "id", "''")
        title_column = _text_column(columns, "title", "''")
        preview_column = _text_column(columns, "preview", "''")
        cwd_column = _text_column(columns, "cwd", "''")
        tokens = _numeric_column(columns, "tokens_used", "0")
        updated = _numeric_column(columns, "updated_at", "0")
        recency = _numeric_column(columns, "recency_at", updated)
        created = _numeric_column(columns, "created_at", updated)
        model = _text_column(columns, "model", "NULL")
        archived = _numeric_column(columns, "archived", "0")

        query = f"""
        SELECT
          {id_column} AS id,
          {title_column} AS title,
          {preview_column} AS preview,
          {cwd_column} AS cwd,
          {tokens} AS tokens,
          {updated} AS updatedAt,
          {recency} AS recencyAt,
          {model} AS model
        FROM threads
        WHERE {archived} = 0
          AND COALESCE(NULLIF({preview_column}, ''), NULLIF({title_column}, ''), '') <> ''
          AND (
            {updated} >= ?
            OR {recency} >= ?
            OR {created} >= ?
          )
        ORDER BY {recency} DESC, {updated} DESC
        LIMIT 24;
        """
        rows = connection.execute(
            query,
            (
                int(day_start.timestamp()),
                int(day_start.timestamp()),
                int(day_start.timestamp()),
            ),
        ).fetchall()

        active: list[TaskItem] = []
        pending: list[TaskItem] = []
        for row in rows:
            updated_at = _date_from_epoch(row["recencyAt"]) or _date_from_epoch(
                row["updatedAt"]
            )
            kind = (
                TaskColumnKind.ACTIVE
                if updated_at is not None and updated_at >= active_cutoff
                else TaskColumnKind.PENDING
            )
            item = _make_thread_task_item(row, updated_at, kind)
            if kind is TaskColumnKind.ACTIVE:
                active.append(item)
            else:
                pending.append(item)
        return active, pending

    def _read_done_task_items(
        self,
        connection: sqlite3.Connection,
        columns: set[str],
        day_start: datetime,
    ) -> list[TaskItem]:
        id_column = _text_column(columns, "id", "''")
        title_column = _text_column(columns, "title", "''")
        preview_column = _text_column(columns, "preview", "''")
        cwd_column = _text_column(columns, "cwd", "''")
        tokens = _numeric_column(columns, "tokens_used", "0")
        updated = _numeric_column(columns, "updated_at", "0")
        archived_at = _numeric_column(columns, "archived_at", updated)
        model = _text_column(columns, "model", "NULL")
        archived = _numeric_column(columns, "archived", "0")

        query = f"""
        SELECT
          {id_column} AS id,
          {title_column} AS title,
          {preview_column} AS preview,
          {cwd_column} AS cwd,
          {tokens} AS tokens,
          COALESCE({archived_at}, {updated}) AS updatedAt,
          {model} AS model
        FROM threads
        WHERE {archived} = 1
          AND COALESCE({archived_at}, {updated}) >= ?
        ORDER BY COALESCE({archived_at}, {updated}) DESC
        LIMIT 12;
        """
        rows = connection.execute(query, (int(day_start.timestamp()),)).fetchall()
        return [
            _make_thread_task_item(row, _date_from_epoch(row["updatedAt"]), TaskColumnKind.DONE)
            for row in rows
        ]

    def read_automation_tasks(self) -> list[TaskItem]:
        root = self.locations.automations_directory
        if not root.is_dir():
            return []

        items: list[TaskItem] = []
        for path in root.rglob("automation.toml"):
            fields = _parse_toml_fields(path)
            if str(fields.get("status", "")).upper() != "ACTIVE":
                continue

            automation_id = str(fields.get("id") or path.parent.name)
            name = str(fields.get("name") or automation_id)
            kind = str(fields.get("kind") or "cron")
            schedule = schedule_summary(str(fields.get("rrule") or ""), "zh")
            detail = " · ".join(
                value for value in (kind.upper(), schedule) if value
            )
            chip = "Wake" if kind == "heartbeat" else "Cron"
            updated_at = _date_from_value(fields.get("updated_at"))

            items.append(
                TaskItem(
                    id=f"automation-{automation_id}",
                    code=f"AUTO-{automation_id[:4].upper()}",
                    title=name,
                    detail=detail,
                    chip=chip,
                    updated_at=updated_at,
                    tokens=None,
                    kind=TaskColumnKind.SCHEDULED,
                )
            )

        return sorted(items, key=lambda item: item.title)


def parse_session_usage(path: Path) -> SessionUsageParseResult | None:
    if not path.is_file():
        return None

    previous = TokenBreakdown()
    saw_token_event = False
    token_event_count = 0
    deltas: list[SessionUsageDelta] = []

    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "token_count" not in line:
                    continue
                parsed = _process_usage_line(line, previous)
                if parsed is None:
                    continue
                saw_token_event = True
                token_event_count += 1
                previous = parsed[0]
                delta = parsed[1]
                date = parsed[2]
                if not delta.is_zero:
                    deltas.append(SessionUsageDelta(date=date, tokens=delta))
    except OSError:
        return None

    return SessionUsageParseResult(
        has_token_events=saw_token_event,
        token_event_count=token_event_count,
        deltas=deltas,
    )


def _process_usage_line(
    line: str,
    previous: TokenBreakdown,
) -> tuple[TokenBreakdown, TokenBreakdown, datetime] | None:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None

    timestamp = obj.get("timestamp")
    payload = obj.get("payload")
    if not isinstance(timestamp, str) or not isinstance(payload, dict):
        return None
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    total_usage = info.get("total_token_usage")
    if not isinstance(total_usage, dict):
        return None

    date = _date_from_iso(timestamp)
    if date is None:
        return None

    current = TokenBreakdown(
        input_tokens=_int_value(total_usage.get("input_tokens")) or 0,
        cached_input_tokens=_int_value(total_usage.get("cached_input_tokens")) or 0,
        output_tokens=_int_value(total_usage.get("output_tokens")) or 0,
        reasoning_output_tokens=_int_value(
            total_usage.get("reasoning_output_tokens")
        )
        or 0,
        total_tokens=_int_value(total_usage.get("total_tokens")) or 0,
    )
    delta = current.delta_from(previous)
    if delta.has_negative_value:
        delta = current

    return current, delta, date


def _make_thread_task_item(
    row: sqlite3.Row,
    updated_at: datetime | None,
    kind: TaskColumnKind,
) -> TaskItem:
    raw_id = str(row["id"] or "")
    title = normalized_title(str(row["title"] or ""), str(row["preview"] or ""))
    cwd = str(row["cwd"] or "")
    tokens = _int_value(row["tokens"]) or 0
    compact_id = raw_id.replace("-", "")
    suffix = (compact_id[-4:] or "0000").upper()
    code = f"COD-{suffix}"

    if kind is TaskColumnKind.ACTIVE:
        chip = "High" if tokens >= 5_000_000 else "Active"
    elif kind is TaskColumnKind.PENDING:
        chip = "Medium" if tokens >= 2_000_000 else "Idle"
    elif kind is TaskColumnKind.SCHEDULED:
        chip = "Cron"
    else:
        chip = "Done"

    detail_parts = [
        short_workspace_name(cwd),
        _format_tokens_for_detail(tokens) if tokens > 0 else "",
    ]
    detail = " · ".join(part for part in detail_parts if part)

    return TaskItem(
        id=f"{raw_id}{kind.value}",
        code=code,
        title=title,
        detail=detail,
        chip=chip,
        updated_at=updated_at,
        tokens=tokens,
        kind=kind,
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON;")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = connection.execute(f"PRAGMA table_info({table});").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row["name"]) for row in rows}


def _numeric_column(columns: set[str], name: str, fallback: str) -> str:
    return name if name in columns else fallback


def _text_column(columns: set[str], name: str, fallback: str) -> str:
    return name if name in columns else fallback


def _start_of_day(value: datetime) -> datetime:
    local = value.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _date_from_epoch(value: Any) -> datetime | None:
    seconds = _float_value(value)
    if seconds is None or seconds <= 0:
        return None
    if seconds > 10_000_000_000:
        seconds /= 1000
    return datetime.fromtimestamp(seconds).astimezone()


def _date_from_iso(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone()


def _date_from_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone()
    if isinstance(value, (int, float)):
        return _date_from_epoch(value)
    if isinstance(value, str):
        if re.fullmatch(r"\d+(\.\d+)?", value):
            return _date_from_epoch(value)
        return _date_from_iso(value)
    return None


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_session_path(codex_home: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = codex_home / path
    return path


def _parse_toml_fields(path: Path) -> dict[str, Any]:
    if tomllib is not None:
        try:
            with path.open("rb") as handle:
                parsed = tomllib.load(handle)
            return _flatten_toml(parsed)
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return _parse_simple_toml(path)


def _flatten_toml(value: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            flattened.update(_flatten_toml(item))
        else:
            flattened[key] = item
    return flattened


def _parse_simple_toml(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    fields: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        fields[key] = value.replace("\\n", "\n").replace('\\"', '"')
    return fields


def _format_tokens_for_detail(value: int) -> str:
    abs_value = abs(float(value))
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)
