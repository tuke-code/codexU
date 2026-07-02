from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AccountInfo, CreditsInfo, RateWindow


@dataclass(frozen=True)
class AppServerSnapshot:
    account: AccountInfo | None = None
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateWindow | None = None
    secondary: RateWindow | None = None
    credits: CreditsInfo | None = None
    cloud_lifetime_tokens: int | None = None
    messages: tuple[str, ...] = ()


def read_app_server(timeout_seconds: float = 12.0) -> AppServerSnapshot:
    codex_path = _find_codex_executable()
    if codex_path is None:
        return AppServerSnapshot(messages=("未找到 codex 可执行文件",))

    try:
        process = subprocess.Popen(
            [str(codex_path), "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError:
        return AppServerSnapshot(messages=("app-server 启动失败",))

    snapshot = _MutableAppServerSnapshot()
    messages: list[str] = []
    completed: set[int] = set()
    initialized = False
    deadline = time.monotonic() + timeout_seconds

    def write_message(request: dict[str, Any]) -> None:
        if process.stdin is None:
            return
        try:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except OSError:
            messages.append("app-server 写入失败")

    write_message(
        {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "codexu-ubuntu",
                    "title": "codexU Ubuntu",
                    "version": "0.1.0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "optOutNotificationMethods": [],
                },
            },
        }
    )

    while time.monotonic() < deadline and not {2, 3, 4}.issubset(completed):
        if process.poll() is not None:
            if not completed:
                messages.append("app-server 进程已退出")
            break

        if process.stdout is None:
            messages.append("app-server 无输出")
            break

        ready, _writable, _exceptional = select.select([process.stdout], [], [], 0.2)
        if not ready:
            continue

        line = process.stdout.readline()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        response_id = _int_value(payload.get("id"))
        if response_id is None:
            continue

        if response_id == 1 and not initialized:
            initialized = True
            write_message({"method": "initialized"})
            write_message(
                {
                    "id": 2,
                    "method": "account/read",
                    "params": {"refreshToken": False},
                }
            )
            write_message({"id": 3, "method": "account/rateLimits/read"})
            write_message({"id": 4, "method": "account/usage/read"})
            continue

        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "未知错误")
            messages.append(f"app-server {response_id}: {message}")
            completed.add(response_id)
            continue

        result = payload.get("result")
        if not isinstance(result, dict):
            completed.add(response_id)
            continue

        if response_id == 2:
            snapshot.account = _parse_account(result)
        elif response_id == 3:
            _parse_rate_limits(result, snapshot)
        elif response_id == 4:
            snapshot.cloud_lifetime_tokens = _parse_cloud_lifetime_tokens(result)

        if response_id in {2, 3, 4}:
            completed.add(response_id)

    if not {2, 3, 4}.issubset(completed):
        messages.append("app-server 响应超时")

    _terminate_process(process)

    return AppServerSnapshot(
        account=snapshot.account,
        limit_id=snapshot.limit_id,
        limit_name=snapshot.limit_name,
        primary=snapshot.primary,
        secondary=snapshot.secondary,
        credits=snapshot.credits,
        cloud_lifetime_tokens=snapshot.cloud_lifetime_tokens,
        messages=tuple(messages),
    )


class _MutableAppServerSnapshot:
    account: AccountInfo | None = None
    limit_id: str | None = None
    limit_name: str | None = None
    primary: RateWindow | None = None
    secondary: RateWindow | None = None
    credits: CreditsInfo | None = None
    cloud_lifetime_tokens: int | None = None


def _find_codex_executable() -> Path | None:
    from_path = shutil.which("codex")
    candidates = [
        from_path,
        "/usr/bin/codex",
        "/usr/local/bin/codex",
        str(Path.home() / ".local" / "bin" / "codex"),
        str(Path.home() / "bin" / "codex"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def _terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        if process.stdin is not None:
            process.stdin.close()
    except OSError:
        pass

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def _parse_account(result: dict[str, Any]) -> AccountInfo | None:
    account = result.get("account")
    if not isinstance(account, dict):
        return None
    account_type = account.get("type")
    if not isinstance(account_type, str):
        return None
    plan_type = account.get("planType")
    return AccountInfo(
        type=account_type,
        plan_type=plan_type if isinstance(plan_type, str) else None,
        email_present=account.get("email") is not None,
    )


def _parse_rate_limits(result: dict[str, Any], snapshot: _MutableAppServerSnapshot) -> None:
    selected: dict[str, Any] | None = None
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict) and isinstance(by_id.get("codex"), dict):
        selected = by_id["codex"]
    elif isinstance(result.get("rateLimits"), dict):
        selected = result["rateLimits"]

    if selected is None:
        return

    limit_id = selected.get("limitId")
    limit_name = selected.get("limitName")
    snapshot.limit_id = limit_id if isinstance(limit_id, str) else None
    snapshot.limit_name = limit_name if isinstance(limit_name, str) else None
    snapshot.primary = _parse_rate_window(selected.get("primary"))
    snapshot.secondary = _parse_rate_window(selected.get("secondary"))

    reset_credits = None
    reset = result.get("rateLimitResetCredits")
    if isinstance(reset, dict):
        reset_credits = _int_value(reset.get("availableCount"))

    credits = selected.get("credits")
    if isinstance(credits, dict):
        balance = credits.get("balance")
        snapshot.credits = CreditsInfo(
            has_credits=bool(credits.get("hasCredits", False)),
            unlimited=bool(credits.get("unlimited", False)),
            balance=str(balance) if balance is not None else None,
            reset_credits=reset_credits,
        )
    elif reset_credits is not None:
        snapshot.credits = CreditsInfo(
            has_credits=False,
            unlimited=False,
            balance=None,
            reset_credits=reset_credits,
        )


def _parse_rate_window(value: Any) -> RateWindow | None:
    if not isinstance(value, dict):
        return None
    used = _float_value(value.get("usedPercent"))
    if used is None:
        return None

    resets_at = None
    timestamp = _float_value(value.get("resetsAt"))
    if timestamp is not None:
        resets_at = datetime.fromtimestamp(timestamp).astimezone()

    return RateWindow(
        used_percent=used,
        window_duration_mins=_int_value(value.get("windowDurationMins")),
        resets_at=resets_at,
    )


def _parse_cloud_lifetime_tokens(result: dict[str, Any]) -> int | None:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return None
    return _int_value(summary.get("lifetimeTokens"))


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
