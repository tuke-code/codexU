from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskColumnKind(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SCHEDULED = "scheduled"
    DONE = "done"


@dataclass(frozen=True)
class RateWindow:
    used_percent: float
    window_duration_mins: int | None = None
    resets_at: datetime | None = None

    @property
    def remaining_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


@dataclass(frozen=True)
class CreditsInfo:
    has_credits: bool
    unlimited: bool
    balance: str | None = None
    reset_credits: int | None = None


@dataclass(frozen=True)
class AccountInfo:
    type: str
    plan_type: str | None = None
    email_present: bool = False


@dataclass(frozen=True)
class LocalThread:
    id: str
    title: str
    tokens: int
    updated_at: datetime | None
    model: str | None
    cwd: str
    archived: bool


@dataclass(frozen=True)
class DailyTokenBucket:
    id: str
    label: str
    tokens: int


@dataclass
class TokenBreakdown:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @property
    def billable_cached_input_tokens(self) -> int:
        return min(max(self.cached_input_tokens, 0), max(self.input_tokens, 0))

    @property
    def uncached_input_tokens(self) -> int:
        return max(0, self.input_tokens - self.billable_cached_input_tokens)

    @property
    def visible_total_tokens(self) -> int:
        return max(self.total_tokens, self.input_tokens + self.output_tokens)

    @property
    def split_total_tokens(self) -> int:
        return max(
            self.uncached_input_tokens
            + self.billable_cached_input_tokens
            + max(self.output_tokens, 0),
            0,
        )

    @property
    def is_zero(self) -> bool:
        return (
            self.input_tokens == 0
            and self.cached_input_tokens == 0
            and self.output_tokens == 0
            and self.reasoning_output_tokens == 0
            and self.total_tokens == 0
        )

    @property
    def has_negative_value(self) -> bool:
        return (
            self.input_tokens < 0
            or self.cached_input_tokens < 0
            or self.output_tokens < 0
            or self.reasoning_output_tokens < 0
            or self.total_tokens < 0
        )

    def add(self, other: "TokenBreakdown") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.total_tokens += other.total_tokens

    def delta_from(self, previous: "TokenBreakdown") -> "TokenBreakdown":
        return TokenBreakdown(
            input_tokens=self.input_tokens - previous.input_tokens,
            cached_input_tokens=self.cached_input_tokens - previous.cached_input_tokens,
            output_tokens=self.output_tokens - previous.output_tokens,
            reasoning_output_tokens=(
                self.reasoning_output_tokens - previous.reasoning_output_tokens
            ),
            total_tokens=self.total_tokens - previous.total_tokens,
        )


@dataclass
class PricedTokenUsage:
    tokens: TokenBreakdown = field(default_factory=TokenBreakdown)
    estimated_cost_usd: float = 0.0

    def add(self, tokens: TokenBreakdown, cost_usd: float) -> None:
        self.tokens.add(tokens)
        self.estimated_cost_usd += cost_usd


@dataclass(frozen=True)
class DetailedUsage:
    today: PricedTokenUsage
    seven_day: PricedTokenUsage
    month: PricedTokenUsage
    lifetime: PricedTokenUsage
    parsed_file_count: int
    token_event_count: int


@dataclass(frozen=True)
class LocalUsage:
    lifetime_tokens: int
    today_tokens: int
    seven_day_tokens: int
    thread_count: int
    last_updated_at: datetime | None
    daily_buckets: list[DailyTokenBucket]
    recent_threads: list[LocalThread]
    detailed_usage: DetailedUsage | None


@dataclass(frozen=True)
class TaskItem:
    id: str
    code: str
    title: str
    detail: str
    chip: str
    updated_at: datetime | None
    tokens: int | None
    kind: TaskColumnKind


@dataclass(frozen=True)
class TaskColumn:
    id: TaskColumnKind
    title: str
    count: int
    items: list[TaskItem]


@dataclass(frozen=True)
class TaskBoard:
    refreshed_at: datetime
    columns: list[TaskColumn]

    @property
    def total_count(self) -> int:
        return sum(column.count for column in self.columns)


@dataclass(frozen=True)
class UsageSnapshot:
    refreshed_at: datetime
    account: AccountInfo | None = None
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateWindow | None = None
    secondary: RateWindow | None = None
    credits: CreditsInfo | None = None
    cloud_lifetime_tokens: int | None = None
    local: LocalUsage | None = None
    task_board: TaskBoard | None = None
    messages: list[str] = field(default_factory=list)


def iso_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone().isoformat(timespec="seconds")


def json_value(value: Any) -> Any:
    return value if value is not None else None


def priced_usage_to_dict(usage: PricedTokenUsage) -> dict[str, Any]:
    tokens = usage.tokens
    return {
        "estimatedCostUSD": usage.estimated_cost_usd,
        "tokens": {
            "inputTokens": tokens.input_tokens,
            "cachedInputTokens": tokens.billable_cached_input_tokens,
            "uncachedInputTokens": tokens.uncached_input_tokens,
            "outputTokens": tokens.output_tokens,
            "reasoningOutputTokens": tokens.reasoning_output_tokens,
            "totalTokens": tokens.visible_total_tokens,
        },
    }


def snapshot_to_dict(snapshot: UsageSnapshot) -> dict[str, Any]:
    result: dict[str, Any] = {
        "refreshedAt": iso_string(snapshot.refreshed_at),
        "messages": snapshot.messages,
    }

    if snapshot.account is not None:
        result["account"] = {
            "type": snapshot.account.type,
            "planType": json_value(snapshot.account.plan_type),
            "emailPresent": snapshot.account.email_present,
        }

    if snapshot.primary is not None:
        result["primary"] = {
            "usedPercent": snapshot.primary.used_percent,
            "remainingPercent": snapshot.primary.remaining_percent,
            "windowDurationMins": json_value(snapshot.primary.window_duration_mins),
            "resetsAt": json_value(iso_string(snapshot.primary.resets_at)),
        }

    if snapshot.secondary is not None:
        result["secondary"] = {
            "usedPercent": snapshot.secondary.used_percent,
            "remainingPercent": snapshot.secondary.remaining_percent,
            "windowDurationMins": json_value(snapshot.secondary.window_duration_mins),
            "resetsAt": json_value(iso_string(snapshot.secondary.resets_at)),
        }

    if snapshot.credits is not None:
        result["credits"] = {
            "hasCredits": snapshot.credits.has_credits,
            "unlimited": snapshot.credits.unlimited,
            "balance": json_value(snapshot.credits.balance),
            "resetCredits": json_value(snapshot.credits.reset_credits),
        }

    if snapshot.cloud_lifetime_tokens is not None:
        result["cloudLifetimeTokens"] = snapshot.cloud_lifetime_tokens

    if snapshot.local is not None:
        local: dict[str, Any] = {
            "todayTokens": snapshot.local.today_tokens,
            "sevenDayTokens": snapshot.local.seven_day_tokens,
            "lifetimeTokens": snapshot.local.lifetime_tokens,
            "threadCount": snapshot.local.thread_count,
            "lastUpdatedAt": json_value(iso_string(snapshot.local.last_updated_at)),
            "dailyBuckets": [
                {"day": bucket.id, "label": bucket.label, "tokens": bucket.tokens}
                for bucket in snapshot.local.daily_buckets
            ],
            "recentThreads": [
                {
                    "id": thread.id,
                    "title": thread.title,
                    "tokens": thread.tokens,
                    "updatedAt": json_value(iso_string(thread.updated_at)),
                    "model": json_value(thread.model),
                    "cwd": thread.cwd,
                    "archived": thread.archived,
                }
                for thread in snapshot.local.recent_threads
            ],
        }
        if snapshot.local.detailed_usage is not None:
            detailed = snapshot.local.detailed_usage
            local["detailedUsage"] = {
                "today": priced_usage_to_dict(detailed.today),
                "sevenDay": priced_usage_to_dict(detailed.seven_day),
                "month": priced_usage_to_dict(detailed.month),
                "lifetime": priced_usage_to_dict(detailed.lifetime),
                "parsedFileCount": detailed.parsed_file_count,
                "tokenEventCount": detailed.token_event_count,
            }
        result["local"] = local

    if snapshot.task_board is not None:
        result["taskBoard"] = {
            "refreshedAt": iso_string(snapshot.task_board.refreshed_at),
            "totalCount": snapshot.task_board.total_count,
            "columns": [
                {
                    "id": column.id.value,
                    "title": column.title,
                    "count": column.count,
                    "items": [
                        {
                            "id": item.id,
                            "code": item.code,
                            "title": item.title,
                            "detail": item.detail,
                            "chip": item.chip,
                            "updatedAt": json_value(iso_string(item.updated_at)),
                            "tokens": json_value(item.tokens),
                        }
                        for item in column.items
                    ],
                }
                for column in snapshot.task_board.columns
            ],
        }

    return result
