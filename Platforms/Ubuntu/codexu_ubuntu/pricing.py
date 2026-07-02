from __future__ import annotations

from dataclasses import dataclass

from .models import TokenBreakdown


@dataclass(frozen=True)
class ModelTokenPrice:
    model: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


def model_token_price(model: str | None) -> ModelTokenPrice:
    normalized = (model or "").lower()

    if "gpt-5.5-pro" in normalized:
        return ModelTokenPrice("gpt-5.5-pro", 30, 30, 180)
    if "gpt-5.5" in normalized or normalized == "chat-latest":
        return ModelTokenPrice("gpt-5.5", 5, 0.5, 30)
    if "gpt-5.4-mini" in normalized:
        return ModelTokenPrice("gpt-5.4-mini", 0.75, 0.075, 4.5)
    if "gpt-5.4-nano" in normalized:
        return ModelTokenPrice("gpt-5.4-nano", 0.2, 0.02, 1.25)
    if "gpt-5.4-pro" in normalized:
        return ModelTokenPrice("gpt-5.4-pro", 30, 30, 180)
    if "gpt-5.4" in normalized:
        return ModelTokenPrice("gpt-5.4", 2.5, 0.25, 15)
    if (
        "gpt-5.3-codex" in normalized
        or "gpt-5.2-codex" in normalized
        or "gpt-5.3-chat" in normalized
        or "gpt-5.2" in normalized
    ):
        return ModelTokenPrice("gpt-5.2-codex", 1.75, 0.175, 14)
    if "gpt-5-codex" in normalized or normalized == "gpt-5":
        return ModelTokenPrice("gpt-5", 1.25, 0.125, 10)

    return ModelTokenPrice("gpt-5.5", 5, 0.5, 30)


def estimated_cost_usd(tokens: TokenBreakdown, price: ModelTokenPrice) -> float:
    uncached_input_cost = (
        tokens.uncached_input_tokens / 1_000_000 * price.input_per_million
    )
    cached_input_cost = (
        tokens.billable_cached_input_tokens
        / 1_000_000
        * price.cached_input_per_million
    )
    output_cost = max(tokens.output_tokens, 0) / 1_000_000 * price.output_per_million
    return uncached_input_cost + cached_input_cost + output_cost


QUOTA_VALUE_DAILY_TOKEN_LIMIT = 200_000_000
QUOTA_VALUE_BILLING_DAYS = 30
QUOTA_VALUE_UNCACHED_INPUT_SHARE = 0.30
QUOTA_VALUE_CACHED_INPUT_SHARE = 0.50
QUOTA_VALUE_OUTPUT_SHARE = 0.20
QUOTA_VALUE_REFERENCE_PRICE = model_token_price("chat-latest")
QUOTA_VALUE_WEIGHTED_PRICE_PER_MILLION = (
    QUOTA_VALUE_UNCACHED_INPUT_SHARE * QUOTA_VALUE_REFERENCE_PRICE.input_per_million
    + QUOTA_VALUE_CACHED_INPUT_SHARE
    * QUOTA_VALUE_REFERENCE_PRICE.cached_input_per_million
    + QUOTA_VALUE_OUTPUT_SHARE * QUOTA_VALUE_REFERENCE_PRICE.output_per_million
)
QUOTA_VALUE_MONTHLY_TOKEN_LIMIT = (
    QUOTA_VALUE_DAILY_TOKEN_LIMIT * QUOTA_VALUE_BILLING_DAYS
)
QUOTA_VALUE_MONTHLY_MAX_USD = (
    QUOTA_VALUE_MONTHLY_TOKEN_LIMIT
    / 1_000_000
    * QUOTA_VALUE_WEIGHTED_PRICE_PER_MILLION
)

SUBSCRIPTION_MILESTONES = [
    ("Plus", 20.0, "#0A84FF"),
    ("Pro100", 100.0, "#8B6DFF"),
    ("Pro200", 200.0, "#7BA0FF"),
]
