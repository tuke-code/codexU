from __future__ import annotations

import math
import os
import threading
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gdk, Gtk, Pango  # noqa: E402

try:
    import cairo
except ImportError:  # pragma: no cover - runtime dependency of python3-gi on Ubuntu.
    cairo = None  # type: ignore[assignment]

from .formatting import (
    format_compact_usd,
    format_tokens,
    format_usd,
    localized_day_label,
    localized_reader_message,
    localized_task_column_title,
    relative_time,
    reset_date_time,
    task_avatar_text,
    text,
    time_only,
)
from .models import (
    PricedTokenUsage,
    RateWindow,
    TaskColumn,
    TaskColumnKind,
    TaskItem,
    TokenBreakdown,
    UsageSnapshot,
)
from .pricing import QUOTA_VALUE_MONTHLY_MAX_USD, SUBSCRIPTION_MILESTONES
from .reader import CodexUsageReader
from .settings import WidgetSettings


BRAND_PRIMARY = "#2866F7"
BRAND_PRIMARY_LIGHT = "#7BA0FF"
BRAND_SECONDARY = "#8B6DFF"
BRAND_HIGHLIGHT = "#DAA3FA"
STATUS_SUCCESS = "#30D158"
STATUS_INFO = "#0A84FF"
STATUS_WARNING = "#FF9F0A"
STATUS_DANGER = "#FF453A"
STATUS_NEUTRAL = "#98989D"
DATA_INPUT = "#0A84FF"
DATA_CACHED = "#8B6DFF"
DATA_OUTPUT = "#FF9F0A"


class CodexUApplication(Gtk.Application):
    def __init__(
        self,
        *,
        codex_home: str | None = None,
        enable_app_server: bool = True,
    ) -> None:
        super().__init__(
            application_id="dev.codexu.Ubuntu",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.codex_home = codex_home
        self.enable_app_server = enable_app_server
        self.window: CodexUWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        GLib.set_application_name("codexU")
        _install_css()

        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect("activate", self._on_refresh_action)
        self.add_action(refresh_action)
        self.set_accels_for_action("app.refresh", ["<Control>R"])

    def do_activate(self) -> None:
        if self.window is None:
            self.window = CodexUWindow(
                application=self,
                codex_home=self.codex_home,
                enable_app_server=self.enable_app_server,
            )
        self.window.present()

    def _on_refresh_action(self, _action: Gio.SimpleAction, _param: Any) -> None:
        if self.window is not None:
            self.window.refresh()


class CodexUWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        *,
        application: Gtk.Application,
        codex_home: str | None,
        enable_app_server: bool,
    ) -> None:
        super().__init__(application=application, title="codexU")
        self.reader = CodexUsageReader(
            codex_home,
            enable_app_server=enable_app_server,
        )
        self.settings = WidgetSettings.load()
        self.snapshot: UsageSnapshot | None = None
        self.is_refreshing = False
        self._full_timer_id: int | None = None
        self._task_timer_id: int | None = None

        self.set_default_size(820, 720)
        self.set_size_request(720, 620)
        self.set_resizable(True)
        self.set_decorated(False)
        self._apply_theme()

        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.root.add_css_class("widget-root")
        self.set_child(self.root)

        drag_gesture = Gtk.GestureClick.new()
        drag_gesture.set_button(1)
        drag_gesture.connect("pressed", self._begin_window_move)
        self.root.add_controller(drag_gesture)

        self._build_header()
        self._build_body()
        self._build_footer()
        self.refresh()
        self._full_timer_id = GLib.timeout_add_seconds(300, self._refresh_timer)
        self._task_timer_id = GLib.timeout_add_seconds(10, self._task_timer)

    def do_close_request(self) -> bool:
        if self._full_timer_id is not None:
            GLib.source_remove(self._full_timer_id)
            self._full_timer_id = None
        if self._task_timer_id is not None:
            GLib.source_remove(self._task_timer_id)
            self._task_timer_id = None
        return False

    def refresh(self) -> None:
        if self.is_refreshing:
            return
        self.is_refreshing = True
        self.refresh_button.set_sensitive(False)
        self.refresh_image.set_from_icon_name("process-working-symbolic")

        def worker() -> None:
            snapshot = self.reader.load()
            GLib.idle_add(self._finish_refresh, snapshot)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_timer(self) -> bool:
        self.refresh()
        return True

    def _task_timer(self) -> bool:
        if self.is_refreshing:
            return True

        def worker() -> None:
            board = self.reader.load_task_board()
            GLib.idle_add(self._finish_task_refresh, board)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _finish_refresh(self, snapshot: UsageSnapshot) -> bool:
        self.snapshot = snapshot
        self.is_refreshing = False
        self.refresh_button.set_sensitive(True)
        self.refresh_image.set_from_icon_name("view-refresh-symbolic")
        self._render_snapshot()
        return False

    def _finish_task_refresh(self, board: Any) -> bool:
        if self.snapshot is not None and board is not None:
            self.snapshot = UsageSnapshot(
                refreshed_at=self.snapshot.refreshed_at,
                account=self.snapshot.account,
                limit_id=self.snapshot.limit_id,
                limit_name=self.snapshot.limit_name,
                primary=self.snapshot.primary,
                secondary=self.snapshot.secondary,
                credits=self.snapshot.credits,
                cloud_lifetime_tokens=self.snapshot.cloud_lifetime_tokens,
                local=self.snapshot.local,
                task_board=board,
                messages=self.snapshot.messages,
            )
            self._render_task_board()
            self.task_summary.set_text(self._task_board_summary())
        return False

    def _begin_window_move(
        self,
        gesture: Gtk.GestureClick,
        _press_count: int,
        x: float,
        y: float,
    ) -> None:
        surface = self.get_surface()
        if surface is None or not hasattr(surface, "begin_move"):
            return
        event = gesture.get_current_event()
        device = gesture.get_current_event_device()
        button = gesture.get_current_button()
        if event is not None and hasattr(event, "get_time"):
            timestamp = event.get_time()
        elif hasattr(gesture, "get_current_event_time"):
            timestamp = gesture.get_current_event_time()
        else:
            timestamp = Gdk.CURRENT_TIME
        try:
            surface.begin_move(device, button, x, y, timestamp)
        except TypeError:
            pass

    def _build_header(self) -> None:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.add_css_class("header")
        self.root.append(header)

        logo = Gtk.Image.new_from_icon_name("applications-graphics-symbolic")
        logo.add_css_class("app-logo")
        header.append(logo)

        title = Gtk.Label(label="codexU")
        title.add_css_class("app-title")
        title.set_xalign(0)
        header.append(title)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        self.theme_buttons: dict[str, Gtk.ToggleButton] = {}
        theme_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        theme_switch.add_css_class("segmented")
        for key, label in (("system", "Sys"), ("light", "Light"), ("dark", "Dark")):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segment-button")
            button.set_tooltip_text(
                {
                    "system": "Appearance follows GTK/system setting",
                    "light": "Light appearance",
                    "dark": "Dark appearance",
                }[key]
            )
            button.connect("clicked", self._set_theme, key)
            theme_switch.append(button)
            self.theme_buttons[key] = button
        header.append(theme_switch)

        self.language_buttons: dict[str, Gtk.ToggleButton] = {}
        language_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        language_switch.add_css_class("segmented")
        for key, label in (("zh", "中"), ("en", "EN")):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segment-button")
            button.connect("clicked", self._set_language, key)
            language_switch.append(button)
            self.language_buttons[key] = button
        header.append(language_switch)

        self.plan_pill = Gtk.Label(label="LOCAL")
        self.plan_pill.add_css_class("pill")
        header.append(self.plan_pill)

        self.refresh_button = Gtk.Button()
        self.refresh_button.add_css_class("icon-button")
        self.refresh_button.set_tooltip_text("Refresh")
        self.refresh_button.connect("clicked", lambda _button: self.refresh())
        self.refresh_image = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_child(self.refresh_image)
        header.append(self.refresh_button)

        close_button = Gtk.Button()
        close_button.add_css_class("icon-button")
        close_button.set_tooltip_text("Close")
        close_button.connect("clicked", lambda _button: self.close())
        close_button.set_child(Gtk.Image.new_from_icon_name("window-close-symbolic"))
        header.append(close_button)

        self._sync_header_controls()

    def _build_body(self) -> None:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        self.root.append(scrolled)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.body.set_hexpand(True)
        scrolled.set_child(self.body)

        self.diagnostics_section = self._section_box()
        self.diagnostics_section.set_visible(False)
        self.body.append(self.diagnostics_section)

        self.usage_section = self._section_box()
        self.body.append(self.usage_section)
        usage_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        self.usage_section.append(usage_row)

        quota_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        quota_column.set_size_request(164, -1)
        usage_row.append(quota_column)
        self.quota_ring = QuotaRing()
        quota_column.append(self.quota_ring)
        self.quota_reset_primary = self._quota_reset_label()
        self.quota_reset_secondary = self._quota_reset_label()
        quota_column.append(self.quota_reset_primary)
        quota_column.append(self.quota_reset_secondary)

        metrics_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        metrics_column.set_hexpand(True)
        usage_row.append(metrics_column)

        metric_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        metrics_column.append(metric_row)
        self.metric_today = MetricCard()
        self.metric_seven_day = MetricCard()
        self.metric_lifetime = MetricCard()
        for card in (self.metric_today, self.metric_seven_day, self.metric_lifetime):
            card.set_hexpand(True)
            metric_row.append(card)

        self.value_card = ValueProgressCard()
        metrics_column.append(self.value_card)

        self.task_section = self._section_box()
        self.body.append(self.task_section)
        task_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.task_section.append(task_header)
        self.task_title = Gtk.Label()
        self.task_title.add_css_class("section-title")
        self.task_title.set_xalign(0)
        task_header.append(self.task_title)
        task_header_spacer = Gtk.Box()
        task_header_spacer.set_hexpand(True)
        task_header.append(task_header_spacer)
        self.task_summary = Gtk.Label()
        self.task_summary.add_css_class("section-detail")
        task_header.append(self.task_summary)

        self.task_columns_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.task_section.append(self.task_columns_row)
        self.task_columns: dict[TaskColumnKind, TaskColumnView] = {}
        for kind in (
            TaskColumnKind.ACTIVE,
            TaskColumnKind.PENDING,
            TaskColumnKind.SCHEDULED,
            TaskColumnKind.DONE,
        ):
            column_view = TaskColumnView(kind)
            column_view.set_hexpand(True)
            self.task_columns[kind] = column_view
            self.task_columns_row.append(column_view)

    def _build_footer(self) -> None:
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.add_css_class("footer")
        self.root.append(footer)
        footer_spacer = Gtk.Box()
        footer_spacer.set_hexpand(True)
        footer.append(footer_spacer)
        self.footer_label = Gtk.Label()
        self.footer_label.add_css_class("footer-label")
        footer.append(self.footer_label)
        shortcut = Gtk.Label(label="Ctrl+R")
        shortcut.add_css_class("shortcut")
        footer.append(shortcut)

    def _render_snapshot(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        language = self.settings.language

        self.plan_pill.set_text(
            snapshot.account.plan_type.upper()
            if snapshot.account and snapshot.account.plan_type
            else "LOCAL"
        )

        self._render_diagnostics()
        self.quota_ring.update(snapshot.primary, snapshot.secondary, language)
        self.quota_reset_primary.set_text(
            f"5h  {text(language, '重置', 'resets')}  {reset_date_time(snapshot.primary.resets_at if snapshot.primary else None)}"
        )
        self.quota_reset_secondary.set_text(
            f"7d  {text(language, '重置', 'resets')}  {reset_date_time(snapshot.secondary.resets_at if snapshot.secondary else None)}"
        )

        local = snapshot.local
        detailed = local.detailed_usage if local and local.detailed_usage else None
        self.metric_today.update(
            title=text(language, "今日", "Today"),
            usage=detailed.today if detailed else None,
            fallback_tokens=local.today_tokens if local else None,
            language=language,
        )
        self.metric_seven_day.update(
            title=text(language, "近 7 天", "Last 7 days"),
            usage=detailed.seven_day if detailed else None,
            fallback_tokens=local.seven_day_tokens if local else None,
            language=language,
        )
        self.metric_lifetime.update(
            title=text(language, "累计", "Lifetime"),
            usage=detailed.lifetime if detailed else None,
            fallback_tokens=local.lifetime_tokens if local else None,
            language=language,
        )
        self.value_card.update(
            detailed.month if detailed else None,
            language,
        )

        self._render_task_board()
        self.task_title.set_text(text(language, "今日任务看板", "Today's task board"))
        self.task_summary.set_text(self._task_board_summary())
        self.footer_label.set_text(
            f"{text(language, '刷新', 'Refreshed')} {time_only(snapshot.refreshed_at)}"
        )

    def _render_diagnostics(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        _clear_box(self.diagnostics_section)
        diagnostics = self._diagnostic_items()
        self.diagnostics_section.set_visible(bool(diagnostics))
        if not diagnostics:
            return

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.diagnostics_section.append(header)
        title = Gtk.Label(label=text(self.settings.language, "环境检查", "Environment"))
        title.add_css_class("section-title")
        title.set_xalign(0)
        header.append(title)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)
        detail = Gtk.Label(label=text(self.settings.language, "首次使用", "First run"))
        detail.add_css_class("section-detail")
        header.append(detail)

        for item in diagnostics:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            row.add_css_class("diagnostic-row")
            self.diagnostics_section.append(row)
            icon = Gtk.Image.new_from_icon_name(item["icon"])
            icon.add_css_class(item["class"])
            row.append(icon)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            content.set_hexpand(True)
            row.append(content)
            item_title = Gtk.Label(label=item["title"])
            item_title.add_css_class("diagnostic-title")
            item_title.set_xalign(0)
            content.append(item_title)
            item_detail = Gtk.Label(label=item["detail"])
            item_detail.add_css_class("diagnostic-detail")
            item_detail.set_xalign(0)
            item_detail.set_wrap(True)
            content.append(item_detail)

    def _render_task_board(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        columns = {column.id: column for column in snapshot.task_board.columns} if snapshot.task_board else {}
        for kind, view in self.task_columns.items():
            column = columns.get(kind) or TaskColumn(
                id=kind,
                title=localized_task_column_title(kind, self.settings.language),
                count=0,
                items=[],
            )
            view.update(column, self.settings.language)

    def _diagnostic_items(self) -> list[dict[str, str]]:
        snapshot = self.snapshot
        if snapshot is None:
            return []
        language = self.settings.language
        messages = "\n".join(snapshot.messages)
        items: list[dict[str, str]] = []

        if snapshot.primary is None or snapshot.account is None:
            if "未找到 codex" in messages:
                items.append(
                    {
                        "title": text(language, "未找到 Codex", "Codex not found"),
                        "detail": text(
                            language,
                            "请确认 codex CLI 已安装并在 PATH、/usr/bin、/usr/local/bin 或 ~/.local/bin 中。",
                            "Make sure the codex CLI is installed in PATH, /usr/bin, /usr/local/bin, or ~/.local/bin.",
                        ),
                        "icon": "edit-find-symbolic",
                        "class": "warning-icon",
                    }
                )
            elif "app-server" in messages:
                items.append(
                    {
                        "title": text(
                            language,
                            "Codex 账户接口暂不可用",
                            "Codex account API unavailable",
                        ),
                        "detail": text(
                            language,
                            "确认 Codex 已登录后点击刷新；本机 token 统计仍可继续显示。",
                            "Make sure Codex is signed in, then refresh. Local token stats can still be shown.",
                        ),
                        "icon": "dialog-warning-symbolic",
                        "class": "warning-icon",
                    }
                )

        if snapshot.local is None:
            if "state_5.sqlite" in messages:
                items.append(
                    {
                        "title": text(
                            language,
                            "未找到本机 Codex 统计库",
                            "Local Codex database not found",
                        ),
                        "detail": text(
                            language,
                            "打开 Codex 并至少完成一次会话后，再回到小组件点击刷新。",
                            "Open Codex and complete at least one session, then refresh this widget.",
                        ),
                        "icon": "drive-harddisk-symbolic",
                        "class": "warning-icon",
                    }
                )
            else:
                items.append(
                    {
                        "title": text(
                            language,
                            "本机统计暂不可用",
                            "Local stats unavailable",
                        ),
                        "detail": text(
                            language,
                            "本机 token 和任务看板依赖 CODEX_HOME 或 ~/.codex 下的本地状态文件。",
                            "Local tokens and the task board depend on CODEX_HOME or local state files under ~/.codex.",
                        ),
                        "icon": "view-list-symbolic",
                        "class": "info-icon",
                    }
                )

        if not items and snapshot.messages:
            for message in snapshot.messages[:3]:
                if message == "已跳过 codex app-server":
                    continue
                items.append(
                    {
                        "title": text(language, "运行提示", "Runtime note"),
                        "detail": localized_reader_message(message, language),
                        "icon": "dialog-information-symbolic",
                        "class": "info-icon",
                    }
                )
        return items

    def _task_board_summary(self) -> str:
        snapshot = self.snapshot
        language = self.settings.language
        if snapshot is None or snapshot.task_board is None:
            return text(language, "读取中", "Loading")
        return text(
            language,
            f"{snapshot.task_board.total_count} 事项 · {time_only(snapshot.task_board.refreshed_at)}",
            f"{snapshot.task_board.total_count} items · {time_only(snapshot.task_board.refreshed_at)}",
        )

    def _set_language(self, button: Gtk.ToggleButton, language: str) -> None:
        if not button.get_active() and self.settings.language == language:
            button.set_active(True)
            return
        self.settings.language = language
        self.settings.save()
        self._sync_header_controls()
        self._render_snapshot()

    def _set_theme(self, button: Gtk.ToggleButton, theme: str) -> None:
        if not button.get_active() and self.settings.theme == theme:
            button.set_active(True)
            return
        self.settings.theme = theme
        self.settings.save()
        self._apply_theme()
        self._sync_header_controls()

    def _sync_header_controls(self) -> None:
        for key, button in self.language_buttons.items():
            button.set_active(key == self.settings.language)
        for key, button in self.theme_buttons.items():
            button.set_active(key == self.settings.theme)

    def _apply_theme(self) -> None:
        effective = self._effective_theme()
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property(
                "gtk-application-prefer-dark-theme",
                effective == "dark",
            )
        for css_class in ("theme-light", "theme-dark"):
            self.remove_css_class(css_class)
        self.add_css_class("theme-dark" if effective == "dark" else "theme-light")

    def _effective_theme(self) -> str:
        if self.settings.theme in {"light", "dark"}:
            return self.settings.theme
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return "dark"
        settings = Gtk.Settings.get_default()
        if settings is not None and settings.get_property(
            "gtk-application-prefer-dark-theme"
        ):
            return "dark"
        return "light"

    def _section_box(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class("section")
        box.set_hexpand(True)
        return box

    def _quota_reset_label(self) -> Gtk.Label:
        label = Gtk.Label(label="--")
        label.add_css_class("quota-reset")
        label.set_xalign(0)
        return label


class QuotaRing(Gtk.Overlay):
    def __init__(self) -> None:
        super().__init__()
        self.primary: RateWindow | None = None
        self.secondary: RateWindow | None = None
        self.language = "en"

        self.area = Gtk.DrawingArea()
        self.area.set_content_width(145)
        self.area.set_content_height(145)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        self.add_overlay(center)
        self.primary_label = Gtk.Label(label="5h --")
        self.primary_label.add_css_class("ring-value")
        self.secondary_label = Gtk.Label(label="7d --")
        self.secondary_label.add_css_class("ring-value")
        self.left_label = Gtk.Label(label="left")
        self.left_label.add_css_class("ring-caption")
        center.append(self.primary_label)
        center.append(self.secondary_label)
        center.append(self.left_label)

    def update(
        self,
        primary: RateWindow | None,
        secondary: RateWindow | None,
        language: str,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.language = language
        self.primary_label.set_markup(
            f'<span foreground="{BRAND_PRIMARY}">5h</span> {round(primary.remaining_percent) if primary else "--"}%'
            if primary
            else f'<span foreground="{BRAND_PRIMARY}">5h</span> --'
        )
        self.secondary_label.set_markup(
            f'<span foreground="{BRAND_SECONDARY}">7d</span> {round(secondary.remaining_percent) if secondary else "--"}%'
            if secondary
            else f'<span foreground="{BRAND_SECONDARY}">7d</span> --'
        )
        self.left_label.set_text(text(language, "剩余", "left"))
        self.area.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, ctx: Any, width: int, height: int) -> None:
        cx = width / 2
        cy = height / 2
        _draw_ring(ctx, cx, cy, 64, 16, self.primary, BRAND_PRIMARY_LIGHT, BRAND_PRIMARY)
        _draw_ring(ctx, cx, cy, 45, 16, self.secondary, BRAND_HIGHLIGHT, BRAND_SECONDARY)
        _set_source(ctx, "#000000", 0.08)
        ctx.arc(cx, cy, 36, 0, math.pi * 2)
        ctx.fill()


class MetricCard(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.add_css_class("card")
        self.set_size_request(0, 128)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.append(top)
        self.title = Gtk.Label()
        self.title.add_css_class("metric-title")
        self.title.set_xalign(0)
        top.append(self.title)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top.append(spacer)
        self.cost = Gtk.Label(label="--")
        self.cost.add_css_class("metric-cost")
        top.append(self.cost)

        self.tokens = Gtk.Label(label="--")
        self.tokens.add_css_class("metric-value")
        self.tokens.set_xalign(0)
        self.append(self.tokens)

        self.split_bar = SplitBar()
        self.append(self.split_bar)

        self.input_row = LegendRow(DATA_INPUT)
        self.cached_row = LegendRow(DATA_CACHED)
        self.output_row = LegendRow(DATA_OUTPUT)
        self.append(self.input_row)
        self.append(self.cached_row)
        self.append(self.output_row)

    def update(
        self,
        *,
        title: str,
        usage: PricedTokenUsage | None,
        fallback_tokens: int | None,
        language: str,
    ) -> None:
        display_tokens = (
            usage.tokens.visible_total_tokens if usage is not None else fallback_tokens
        )
        self.title.set_text(title)
        self.cost.set_text(format_usd(usage.estimated_cost_usd if usage else None))
        self.tokens.set_text(format_tokens(display_tokens))
        self.split_bar.update(usage.tokens if usage else None)
        self.input_row.update(text(language, "未缓存", "Input"), usage.tokens.uncached_input_tokens if usage else None)
        self.cached_row.update(text(language, "缓存", "Cached"), usage.tokens.billable_cached_input_tokens if usage else None)
        self.output_row.update(text(language, "输出", "Output"), usage.tokens.output_tokens if usage else None)


class SplitBar(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.tokens: TokenBreakdown | None = None
        self.set_content_height(8)
        self.set_draw_func(self._draw)

    def update(self, tokens: TokenBreakdown | None) -> None:
        self.tokens = tokens
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, ctx: Any, width: int, height: int) -> None:
        _rounded_rect(ctx, 0, 0, width, height, 4)
        _set_source(ctx, "#000000", 0.10)
        ctx.fill()

        if self.tokens is None or self.tokens.split_total_tokens <= 0:
            return

        total = self.tokens.split_total_tokens
        x = 0.0
        for value, color in (
            (self.tokens.uncached_input_tokens, DATA_INPUT),
            (self.tokens.billable_cached_input_tokens, DATA_CACHED),
            (self.tokens.output_tokens, DATA_OUTPUT),
        ):
            if value <= 0:
                continue
            segment_width = max(2.0, width * value / total)
            _set_source(ctx, color, 1)
            ctx.rectangle(x, 0, segment_width, height)
            ctx.fill()
            x += segment_width


class LegendRow(Gtk.Box):
    def __init__(self, color: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        dot = Gtk.DrawingArea()
        dot.set_content_width(6)
        dot.set_content_height(6)
        dot.set_draw_func(lambda _area, ctx, width, height: _draw_dot(ctx, width, height, color))
        self.append(dot)
        self.title = Gtk.Label()
        self.title.add_css_class("legend-title")
        self.title.set_xalign(0)
        self.append(self.title)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)
        self.value = Gtk.Label()
        self.value.add_css_class("legend-value")
        self.append(self.value)

    def update(self, title: str, value: int | None) -> None:
        self.title.set_text(title)
        self.value.set_text(format_tokens(value))


class ValueProgressCard(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("card")
        self.header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(self.header)
        self.title = Gtk.Label()
        self.title.add_css_class("value-title")
        self.title.set_xalign(0)
        self.header.append(self.title)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.header.append(spacer)
        self.amount = Gtk.Label()
        self.amount.add_css_class("value-amount")
        self.header.append(self.amount)
        self.cap = Gtk.Label()
        self.cap.add_css_class("value-cap")
        self.header.append(self.cap)

        self.progress = ValueProgressBar()
        self.append(self.progress)
        self.legend = Gtk.Label()
        self.legend.add_css_class("value-legend")
        self.legend.set_xalign(0)
        self.append(self.legend)

    def update(self, usage: PricedTokenUsage | None, language: str) -> None:
        cost = usage.estimated_cost_usd if usage is not None else 0.0
        self.title.set_text(text(language, "羊毛进度", "Value progress"))
        self.amount.set_text(format_usd(cost))
        self.cap.set_text(f"/ {format_compact_usd(QUOTA_VALUE_MONTHLY_MAX_USD)}")
        self.progress.update(cost)
        milestone_labels = "   ".join(label for label, _amount, _color in SUBSCRIPTION_MILESTONES)
        self.legend.set_text(
            f"{milestone_labels}        {text(language, '满额', 'Cap')} {format_compact_usd(QUOTA_VALUE_MONTHLY_MAX_USD)}"
        )


class ValueProgressBar(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self.current_value = 0.0
        self.set_content_height(18)
        self.set_draw_func(self._draw)

    def update(self, current_value: float) -> None:
        self.current_value = max(0.0, current_value)
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, ctx: Any, width: int, height: int) -> None:
        y = height / 2 - 5
        _rounded_rect(ctx, 0, y, width, 10, 5)
        _set_source(ctx, "#000000", 0.10)
        ctx.fill()

        progress_width = _value_offset(self.current_value, width)
        if self.current_value > 0:
            _rounded_rect(ctx, 0, y, max(5, progress_width), 10, 5)
            _set_source(ctx, _value_accent(self.current_value), 1)
            ctx.fill()

        for _label, amount, color in SUBSCRIPTION_MILESTONES:
            x = _value_offset(amount, width)
            _set_source(ctx, color, 1)
            ctx.arc(x, height / 2, 3.5, 0, math.pi * 2)
            ctx.fill()


class TaskColumnView(Gtk.Box):
    def __init__(self, kind: TaskColumnKind) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.kind = kind
        self.add_css_class("task-column")
        self.add_css_class(f"task-{kind.value}")
        self.set_size_request(0, 274)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.append(header)
        self.icon = Gtk.Label(label=_task_icon(kind))
        self.icon.add_css_class(f"task-icon-{kind.value}")
        header.append(self.icon)
        self.title = Gtk.Label()
        self.title.add_css_class("task-column-title")
        self.title.set_xalign(0)
        header.append(self.title)
        self.count = Gtk.Label()
        self.count.add_css_class("task-count")
        header.append(self.count)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)
        more = Gtk.Label(label="...")
        more.add_css_class("task-more")
        header.append(more)

        self.items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.append(self.items_box)

    def update(self, column: TaskColumn, language: str) -> None:
        self.title.set_text(localized_task_column_title(column.id, language))
        self.count.set_text(str(column.count))
        _clear_box(self.items_box)
        if not column.items:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            empty.add_css_class("task-empty")
            icon = Gtk.Label(label="○")
            icon.add_css_class("task-empty-icon")
            empty.append(icon)
            label = Gtk.Label(label=text(language, "暂无", "No items"))
            label.add_css_class("task-empty-label")
            empty.append(label)
            self.items_box.append(empty)
            return

        for item in column.items:
            self.items_box.append(TaskIssueCard(item, language))
        if column.count > len(column.items):
            more = Gtk.Label(
                label=text(
                    language,
                    f"+ {column.count - len(column.items)} 项",
                    f"+ {column.count - len(column.items)} more",
                )
            )
            more.add_css_class("task-more-label")
            more.set_xalign(0)
            self.items_box.append(more)


class TaskIssueCard(Gtk.Box):
    def __init__(self, item: TaskItem, language: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("task-card")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.append(top)
        code = Gtk.Label(label=item.code)
        code.add_css_class("task-code")
        top.append(code)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        top.append(spacer)
        when = Gtk.Label(label=relative_time(item.updated_at, language))
        when.add_css_class("task-time")
        top.append(when)

        title = Gtk.Label(label=item.title)
        title.add_css_class("task-title")
        title.set_xalign(0)
        title.set_wrap(True)
        title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title.set_lines(2)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(title)

        if item.detail:
            detail = Gtk.Label(label=item.detail)
            detail.add_css_class("task-detail")
            detail.set_xalign(0)
            detail.set_ellipsize(Pango.EllipsizeMode.END)
            self.append(detail)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.append(bottom)
        chip = Gtk.Label(label=item.chip)
        chip.add_css_class("task-chip")
        chip.add_css_class(f"chip-{_chip_kind(item)}")
        bottom.append(chip)
        bottom_spacer = Gtk.Box()
        bottom_spacer.set_hexpand(True)
        bottom.append(bottom_spacer)
        avatar = Gtk.Label(label=task_avatar_text(item.code, item.detail))
        avatar.add_css_class("task-avatar")
        avatar.add_css_class(f"avatar-{item.kind.value}")
        bottom.append(avatar)


def _install_css() -> None:
    provider = Gtk.CssProvider()
    try:
        provider.load_from_data(CSS)
    except TypeError:
        provider.load_from_data(CSS.encode("utf-8"))
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def _clear_box(box: Gtk.Box) -> None:
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


def _draw_ring(
    ctx: Any,
    cx: float,
    cy: float,
    radius: float,
    width: float,
    window: RateWindow | None,
    start_color: str,
    end_color: str,
) -> None:
    if cairo is not None:
        line_cap = getattr(getattr(cairo, "LineCap", None), "ROUND", None)
        if line_cap is None:
            line_cap = getattr(cairo, "LINE_CAP_ROUND", None)
        if line_cap is not None:
            ctx.set_line_cap(line_cap)
    ctx.set_line_width(width)
    _set_source(ctx, "#000000", 0.10)
    ctx.arc(cx, cy, radius, -math.pi / 2, math.pi * 1.5)
    ctx.stroke()

    if window is None:
        return
    progress = max(0.0, min(1.0, window.remaining_percent / 100.0))
    if progress <= 0:
        return

    gradient = cairo.LinearGradient(0, 0, cx * 2, cy * 2) if cairo is not None else None
    if gradient is not None:
        gradient.add_color_stop_rgba(0, *_rgba_tuple(start_color, 1))
        gradient.add_color_stop_rgba(1, *_rgba_tuple(end_color, 1))
        ctx.set_source(gradient)
    else:
        _set_source(ctx, end_color, 1)
    ctx.arc(cx, cy, radius, -math.pi / 2, -math.pi / 2 + math.pi * 2 * progress)
    ctx.stroke()


def _draw_dot(ctx: Any, width: int, height: int, color: str) -> None:
    _set_source(ctx, color, 1)
    ctx.arc(width / 2, height / 2, min(width, height) / 2, 0, math.pi * 2)
    ctx.fill()


def _set_source(ctx: Any, color: str, alpha: float) -> None:
    r, g, b, a = _rgba_tuple(color, alpha)
    ctx.set_source_rgba(r, g, b, a)


def _rgba_tuple(color: str, alpha: float) -> tuple[float, float, float, float]:
    color = color.lstrip("#")
    return (
        int(color[0:2], 16) / 255,
        int(color[2:4], 16) / 255,
        int(color[4:6], 16) / 255,
        alpha,
    )


def _rounded_rect(
    ctx: Any,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
) -> None:
    radius = min(radius, width / 2, height / 2)
    ctx.new_sub_path()
    ctx.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    ctx.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    ctx.arc(x + radius, y + radius, radius, math.pi, math.pi * 1.5)
    ctx.close_path()


def _value_offset(amount: float, width: float) -> float:
    max_value = max(QUOTA_VALUE_MONTHLY_MAX_USD, 200)
    subscription_ceiling = 200.0
    subscription_band = 0.28
    clamped = max(0.0, min(amount, max_value))
    if clamped <= subscription_ceiling:
        fraction = subscription_band * (clamped / subscription_ceiling)
    else:
        remaining = max(max_value - subscription_ceiling, 1)
        fraction = subscription_band + (1 - subscription_band) * (
            (clamped - subscription_ceiling) / remaining
        )
    return max(0.0, min(width, width * fraction))


def _value_accent(cost: float) -> str:
    if cost >= 200:
        return BRAND_PRIMARY_LIGHT
    if cost >= 100:
        return BRAND_SECONDARY
    if cost >= 20:
        return STATUS_INFO
    return STATUS_WARNING


def _task_icon(kind: TaskColumnKind) -> str:
    if kind is TaskColumnKind.ACTIVE:
        return "●"
    if kind is TaskColumnKind.PENDING:
        return "○"
    if kind is TaskColumnKind.SCHEDULED:
        return "◷"
    return "✓"


def _chip_kind(item: TaskItem) -> str:
    value = item.chip.lower()
    if value in {"high", "urgent"}:
        return "danger"
    if value in {"medium", "active"}:
        return "warning"
    if value in {"cron", "wake"}:
        return "scheduled"
    if value == "done":
        return "done"
    return item.kind.value


CSS = """
window {
  background: transparent;
}

window.theme-light .widget-root {
  background: rgba(246, 247, 251, 0.96);
  color: #1d1d1f;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18);
}

window.theme-dark .widget-root {
  background: rgba(29, 31, 36, 0.95);
  color: #f5f5f7;
  border: 1px solid rgba(255, 255, 255, 0.10);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.34);
}

.widget-root {
  border-radius: 24px;
  padding: 16px;
}

.header {
  min-height: 34px;
}

.app-logo {
  color: #2866F7;
  min-width: 34px;
  min-height: 34px;
}

.app-title {
  font-size: 22px;
  font-weight: 700;
}

.segmented {
  border-radius: 8px;
  padding: 1px;
  background: rgba(120, 120, 128, 0.12);
  border: 1px solid rgba(120, 120, 128, 0.14);
}

.segment-button {
  min-height: 24px;
  min-width: 34px;
  padding: 0 8px;
  border-radius: 7px;
  border: 0;
  background: transparent;
  font-size: 10px;
  font-weight: 700;
}

.segment-button:checked {
  background: rgba(40, 102, 247, 0.16);
  color: #2866F7;
}

.pill {
  border-radius: 999px;
  padding: 5px 9px;
  background: rgba(120, 120, 128, 0.12);
  border: 1px solid rgba(120, 120, 128, 0.14);
  color: rgba(29, 29, 31, 0.72);
  font-size: 11px;
  font-weight: 700;
}

window.theme-dark .pill {
  color: rgba(245, 245, 247, 0.72);
}

.icon-button {
  min-width: 26px;
  min-height: 26px;
  padding: 0;
  border-radius: 8px;
  background: rgba(120, 120, 128, 0.12);
  border: 1px solid rgba(120, 120, 128, 0.14);
}

.section {
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.36);
  border: 1px solid rgba(120, 120, 128, 0.12);
}

window.theme-dark .section {
  background: rgba(255, 255, 255, 0.07);
  border-color: rgba(255, 255, 255, 0.08);
}

.card,
.task-card {
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(0, 0, 0, 0.06);
}

window.theme-dark .card,
window.theme-dark .task-card {
  background: rgba(255, 255, 255, 0.10);
  border-color: rgba(255, 255, 255, 0.08);
}

.section-title {
  font-size: 12px;
  font-weight: 700;
}

.section-detail,
.footer-label,
.metric-title,
.metric-cost,
.legend-title,
.legend-value,
.quota-reset,
.task-count,
.task-time,
.task-detail,
.task-more,
.task-more-label,
.value-cap,
.value-legend {
  color: rgba(29, 29, 31, 0.66);
}

window.theme-dark .section-detail,
window.theme-dark .footer-label,
window.theme-dark .metric-title,
window.theme-dark .metric-cost,
window.theme-dark .legend-title,
window.theme-dark .legend-value,
window.theme-dark .quota-reset,
window.theme-dark .task-count,
window.theme-dark .task-time,
window.theme-dark .task-detail,
window.theme-dark .task-more,
window.theme-dark .task-more-label,
window.theme-dark .value-cap,
window.theme-dark .value-legend {
  color: rgba(245, 245, 247, 0.66);
}

.quota-reset {
  font-size: 9px;
  font-weight: 700;
}

.ring-value {
  font-size: 15px;
  font-weight: 800;
}

.ring-caption {
  font-size: 10px;
  font-weight: 700;
  color: rgba(29, 29, 31, 0.64);
}

window.theme-dark .ring-caption {
  color: rgba(245, 245, 247, 0.64);
}

.metric-title {
  font-size: 11px;
  font-weight: 700;
}

.metric-cost {
  font-size: 10px;
  font-weight: 800;
}

.metric-value {
  font-size: 21px;
  font-weight: 800;
}

.legend-title,
.legend-value {
  font-size: 9px;
  font-weight: 700;
}

.value-title {
  font-size: 12px;
  font-weight: 700;
}

.value-amount {
  font-size: 16px;
  font-weight: 800;
}

.value-cap,
.value-legend {
  font-size: 9px;
  font-weight: 700;
}

.diagnostic-row {
  padding: 2px 0;
}

.diagnostic-title {
  font-size: 11px;
  font-weight: 700;
}

.diagnostic-detail {
  font-size: 10px;
  font-weight: 600;
  color: rgba(29, 29, 31, 0.66);
}

window.theme-dark .diagnostic-detail {
  color: rgba(245, 245, 247, 0.66);
}

.warning-icon {
  color: #FF9F0A;
}

.info-icon {
  color: #0A84FF;
}

.task-column {
  border-radius: 10px;
  padding: 8px;
  border: 1px solid rgba(120, 120, 128, 0.10);
}

.task-active {
  background: rgba(255, 159, 10, 0.07);
}

.task-pending {
  background: rgba(152, 152, 157, 0.07);
}

.task-scheduled {
  background: rgba(139, 109, 255, 0.07);
}

.task-done {
  background: rgba(48, 209, 88, 0.07);
}

.task-icon-active,
.chip-warning {
  color: #FF9F0A;
}

.task-icon-pending {
  color: #98989D;
}

.task-icon-scheduled,
.chip-scheduled {
  color: #8B6DFF;
}

.task-icon-done,
.chip-done {
  color: #30D158;
}

.chip-danger {
  color: #FF453A;
}

.task-column-title {
  font-size: 11px;
  font-weight: 800;
}

.task-card {
  padding: 8px;
  border-radius: 8px;
}

.task-code {
  font-size: 9px;
  font-weight: 800;
  color: rgba(29, 29, 31, 0.66);
}

window.theme-dark .task-code {
  color: rgba(245, 245, 247, 0.66);
}

.task-title {
  font-size: 11px;
  font-weight: 800;
}

.task-detail {
  font-size: 9px;
  font-weight: 650;
}

.task-time {
  font-size: 8px;
  font-weight: 650;
}

.task-chip {
  border-radius: 999px;
  padding: 3px 7px;
  background: rgba(120, 120, 128, 0.12);
  font-size: 9px;
  font-weight: 800;
}

.task-avatar {
  border-radius: 999px;
  min-width: 18px;
  min-height: 18px;
  font-size: 9px;
  font-weight: 800;
  background: rgba(120, 120, 128, 0.12);
}

.avatar-active {
  color: #FF9F0A;
}

.avatar-pending {
  color: #98989D;
}

.avatar-scheduled {
  color: #8B6DFF;
}

.avatar-done {
  color: #30D158;
}

.task-empty {
  min-height: 66px;
  color: rgba(29, 29, 31, 0.40);
}

window.theme-dark .task-empty {
  color: rgba(245, 245, 247, 0.40);
}

.task-empty-icon {
  font-size: 13px;
  font-weight: 700;
}

.task-empty-label {
  font-size: 10px;
  font-weight: 650;
}

.footer {
  min-height: 18px;
}

.shortcut {
  color: rgba(29, 29, 31, 0.46);
  font-size: 10px;
  font-weight: 800;
}

window.theme-dark .shortcut {
  color: rgba(245, 245, 247, 0.46);
}
"""
