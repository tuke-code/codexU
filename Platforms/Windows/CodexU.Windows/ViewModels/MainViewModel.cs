using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Windows.Input;
using System.Windows.Threading;
using CodexU.Windows.Models;
using CodexU.Windows.Services;

namespace CodexU.Windows.ViewModels;

public sealed class MainViewModel : INotifyPropertyChanged
{
    private const double QuotaValueDailyTokenLimit = 200_000_000;
    private const double QuotaValueBillingDays = 30;
    private const double QuotaValueWeightedPricePerMillion = 7.75;
    private static readonly double QuotaValueMonthlyMaxUsd = QuotaValueDailyTokenLimit * QuotaValueBillingDays / 1_000_000d * QuotaValueWeightedPricePerMillion;

    private readonly CodexUsageReader _reader;
    private readonly LocalSettings _settings;
    private readonly DispatcherTimer _fullRefreshTimer = new() { Interval = TimeSpan.FromMinutes(5) };
    private readonly DispatcherTimer _taskBoardTimer = new() { Interval = TimeSpan.FromSeconds(10) };
    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private UsageSnapshot _snapshot = UsageSnapshot.Empty;
    private bool _isRefreshing;
    private bool _isPinnedTopmost;

    public MainViewModel(CodexUsageReader reader, LocalSettings settings)
    {
        _reader = reader;
        _settings = settings;
        _isPinnedTopmost = settings.StartPinnedTopmost;

        RefreshCommand = new RelayCommand(_ => _ = RefreshAsync());
        _fullRefreshTimer.Tick += (_, _) => _ = RefreshAsync();
        _taskBoardTimer.Tick += (_, _) => _ = RefreshTaskBoardAsync();
        RebuildDisplayCollections();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public event EventHandler? ThemeChanged;

    public ICommand RefreshCommand { get; }

    public UsageSnapshot Snapshot
    {
        get => _snapshot;
        private set
        {
            _snapshot = value;
            RebuildDisplayCollections();
            OnPropertyChanged();
            RaiseAllDisplayProperties();
        }
    }

    public bool IsRefreshing
    {
        get => _isRefreshing;
        private set
        {
            if (_isRefreshing == value)
            {
                return;
            }

            _isRefreshing = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(RefreshGlyph));
        }
    }

    public WidgetLanguage Language
    {
        get => _settings.Language;
        set
        {
            if (_settings.Language == value)
            {
                return;
            }

            _settings.Language = value;
            _settings.Save();
            RebuildDisplayCollections();
            OnPropertyChanged();
            RaiseAllDisplayProperties();
        }
    }

    public WidgetThemeMode ThemeMode
    {
        get => _settings.ThemeMode;
        set
        {
            if (_settings.ThemeMode == value)
            {
                return;
            }

            _settings.ThemeMode = value;
            _settings.Save();
            OnPropertyChanged();
            OnPropertyChanged(nameof(ThemeOptions));
            ThemeChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    public bool IsPinnedTopmost
    {
        get => _isPinnedTopmost;
        set
        {
            if (_isPinnedTopmost == value)
            {
                return;
            }

            _isPinnedTopmost = value;
            _settings.StartPinnedTopmost = value;
            _settings.Save();
            OnPropertyChanged();
            OnPropertyChanged(nameof(PinGlyph));
            OnPropertyChanged(nameof(PinTooltip));
        }
    }

    public IReadOnlyList<OptionItem<WidgetLanguage>> LanguageOptions => new[]
    {
        new OptionItem<WidgetLanguage>("中", WidgetLanguage.Zh),
        new OptionItem<WidgetLanguage>("EN", WidgetLanguage.En)
    };

    public IReadOnlyList<OptionItem<WidgetThemeMode>> ThemeOptions => new[]
    {
        new OptionItem<WidgetThemeMode>(T("系统", "System"), WidgetThemeMode.System),
        new OptionItem<WidgetThemeMode>(T("浅色", "Light"), WidgetThemeMode.Light),
        new OptionItem<WidgetThemeMode>(T("深色", "Dark"), WidgetThemeMode.Dark)
    };

    public ObservableCollection<TaskColumnDisplay> TaskColumns { get; } = new();

    public ObservableCollection<DiagnosticDisplay> Diagnostics { get; } = new();

    public bool ShowDiagnostics => Diagnostics.Count > 0;

    public string PlanLabel => Snapshot.Account?.PlanType?.ToUpperInvariant() ?? "LOCAL";

    public string RefreshGlyph => IsRefreshing ? "\uE823" : "\uE72C";

    public string PinGlyph => IsPinnedTopmost ? "\uE840" : "\uE718";

    public string PinTooltip => IsPinnedTopmost ? T("切回普通桌面层", "Return to desktop mode") : T("置顶显示", "Pin topmost");

    public string EnvironmentTitle => T("环境检查", "Environment");

    public string EnvironmentDetail => T("首次使用 / 诊断", "First run / diagnostics");

    public string UsageTitle => T("用量概览", "Usage overview");

    public string UsageDetail => T("本机统计 + 账户额度", "Local stats + quota");

    public string TaskBoardTitle => T("今日任务看板", "Today's task board");

    public string TaskBoardSummary =>
        Snapshot.TaskBoard is null
            ? T("读取中", "Loading")
            : T($"{Snapshot.TaskBoard.TotalCount} 事项 · {TimeOnly(Snapshot.TaskBoard.RefreshedAt)}", $"{Snapshot.TaskBoard.TotalCount} items · {TimeOnly(Snapshot.TaskBoard.RefreshedAt)}");

    public string FooterText => $"{T("刷新", "Refreshed")} {TimeOnly(Snapshot.RefreshedAt)}";

    public double PrimaryRemainingPercent => Snapshot.Primary?.RemainingPercent ?? 0;

    public double SecondaryRemainingPercent => Snapshot.Secondary?.RemainingPercent ?? 0;

    public bool HasPrimaryQuota => Snapshot.Primary is not null;

    public bool HasSecondaryQuota => Snapshot.Secondary is not null;

    public string PrimaryQuotaText => Snapshot.Primary is null ? "--" : $"{Math.Round(Snapshot.Primary.RemainingPercent):0}%";

    public string SecondaryQuotaText => Snapshot.Secondary is null ? "--" : $"{Math.Round(Snapshot.Secondary.RemainingPercent):0}%";

    public string QuotaLeftLabel => T("剩余", "left");

    public string PrimaryResetText => ResetText(Snapshot.Primary);

    public string SecondaryResetText => ResetText(Snapshot.Secondary);

    public string TodayTitle => T("今日", "Today");

    public string SevenDayTitle => T("近 7 天", "Last 7 days");

    public string LifetimeTitle => T("累计", "Lifetime");

    public string TokensLabel => "Tokens";

    public string InputLabel => T("未缓存", "Input");

    public string CachedLabel => T("缓存", "Cached");

    public string OutputLabel => T("输出", "Output");

    public string TodayTokensText => FormatTokens(TodayUsage?.Tokens.VisibleTotalTokens ?? Snapshot.Local?.TodayTokens);

    public string SevenDayTokensText => FormatTokens(SevenDayUsage?.Tokens.VisibleTotalTokens ?? Snapshot.Local?.SevenDayTokens);

    public string LifetimeTokensText => FormatTokens(LifetimeUsage?.Tokens.VisibleTotalTokens ?? Snapshot.Local?.LifetimeTokens);

    public string TodayCostText => FormatUsd(TodayUsage?.EstimatedCostUsd);

    public string SevenDayCostText => FormatUsd(SevenDayUsage?.EstimatedCostUsd);

    public string LifetimeCostText => FormatUsd(LifetimeUsage?.EstimatedCostUsd);

    public long TodayUncached => TodayUsage?.Tokens.UncachedInputTokens ?? 0;

    public long TodayCached => TodayUsage?.Tokens.BillableCachedInputTokens ?? 0;

    public long TodayOutput => TodayUsage?.Tokens.OutputTokens ?? 0;

    public long SevenDayUncached => SevenDayUsage?.Tokens.UncachedInputTokens ?? 0;

    public long SevenDayCached => SevenDayUsage?.Tokens.BillableCachedInputTokens ?? 0;

    public long SevenDayOutput => SevenDayUsage?.Tokens.OutputTokens ?? 0;

    public long LifetimeUncached => LifetimeUsage?.Tokens.UncachedInputTokens ?? 0;

    public long LifetimeCached => LifetimeUsage?.Tokens.BillableCachedInputTokens ?? 0;

    public long LifetimeOutput => LifetimeUsage?.Tokens.OutputTokens ?? 0;

    public string TodayInputText => FormatTokens(TodayUncached);

    public string TodayCachedText => FormatTokens(TodayCached);

    public string TodayOutputText => FormatTokens(TodayOutput);

    public string SevenDayInputText => FormatTokens(SevenDayUncached);

    public string SevenDayCachedText => FormatTokens(SevenDayCached);

    public string SevenDayOutputText => FormatTokens(SevenDayOutput);

    public string LifetimeInputText => FormatTokens(LifetimeUncached);

    public string LifetimeCachedText => FormatTokens(LifetimeCached);

    public string LifetimeOutputText => FormatTokens(LifetimeOutput);

    public string ValueProgressTitle => T("羊毛进度", "Value progress");

    public double MonthCostValue => Snapshot.Local?.DetailedUsage?.Month.EstimatedCostUsd ?? 0;

    public double MonthMaxValue => QuotaValueMonthlyMaxUsd;

    public string MonthCostText => FormatUsd(MonthCostValue);

    public string MonthCapText => $"/ {FormatCompactUsd(MonthMaxValue)}";

    public string FullQuotaText => $"{T("满额", "Cap")} {FormatCompactUsd(MonthMaxValue)}";

    private PricedTokenUsage? TodayUsage => Snapshot.Local?.DetailedUsage?.Today;

    private PricedTokenUsage? SevenDayUsage => Snapshot.Local?.DetailedUsage?.SevenDay;

    private PricedTokenUsage? LifetimeUsage => Snapshot.Local?.DetailedUsage?.Lifetime;

    public void Start()
    {
        _fullRefreshTimer.Start();
        _taskBoardTimer.Start();
        _ = RefreshAsync();
    }

    public void Stop()
    {
        _fullRefreshTimer.Stop();
        _taskBoardTimer.Stop();
    }

    public async Task RefreshAsync()
    {
        if (!await _refreshLock.WaitAsync(0).ConfigureAwait(false))
        {
            return;
        }

        try
        {
            IsRefreshing = true;
            var snapshot = await Task.Run(async () => await _reader.LoadAsync().ConfigureAwait(false)).ConfigureAwait(true);
            Snapshot = snapshot;
        }
        finally
        {
            IsRefreshing = false;
            _refreshLock.Release();
        }
    }

    private async Task RefreshTaskBoardAsync()
    {
        if (IsRefreshing)
        {
            return;
        }

        try
        {
            var taskBoard = await _reader.LoadTaskBoardAsync().ConfigureAwait(true);
            Snapshot = Snapshot.WithTaskBoard(taskBoard);
        }
        catch
        {
            // Task board refresh is opportunistic; full refresh diagnostics will surface reader issues.
        }
    }

    private void RebuildDisplayCollections()
    {
        TaskColumns.Clear();
        var sourceColumns = Snapshot.TaskBoard?.Columns ?? new[]
        {
            new TaskColumn(TaskColumnKind.Active, "进行中", 0, Array.Empty<TaskItem>()),
            new TaskColumn(TaskColumnKind.Pending, "待处理", 0, Array.Empty<TaskItem>()),
            new TaskColumn(TaskColumnKind.Scheduled, "定时", 0, Array.Empty<TaskItem>()),
            new TaskColumn(TaskColumnKind.Done, "完成", 0, Array.Empty<TaskItem>())
        };

        foreach (var column in sourceColumns)
        {
            TaskColumns.Add(TaskColumnDisplay.From(column, Language));
        }

        Diagnostics.Clear();
        foreach (var item in BuildDiagnostics())
        {
            Diagnostics.Add(item);
        }

        OnPropertyChanged(nameof(ShowDiagnostics));
    }

    private IEnumerable<DiagnosticDisplay> BuildDiagnostics()
    {
        if (Snapshot.Messages.Contains("正在读取 codexU 数据"))
        {
            yield break;
        }

        var messages = string.Join('\n', Snapshot.Messages);
        if (Snapshot.Primary is null || Snapshot.Account is null)
        {
            if (messages.Contains("未找到 codex", StringComparison.OrdinalIgnoreCase))
            {
                yield return new DiagnosticDisplay("codex-missing", T("未找到 Codex", "Codex not found"), T("请先安装 Codex Windows 桌面应用，或确认 codex.exe 位于 PATH。", "Install Codex for Windows, or make sure codex.exe is on PATH."), "\uE721", "StatusWarningBrush");
            }
            else if (messages.Contains("app-server", StringComparison.OrdinalIgnoreCase))
            {
                yield return new DiagnosticDisplay("app-server", T("Codex 账户接口暂不可用", "Codex account API unavailable"), T("确认 Codex 已登录后点击刷新；本机 token 统计仍会继续显示。", "Make sure Codex is signed in, then refresh. Local token stats can still be shown."), "\uE7BA", "StatusWarningBrush");
            }
            else
            {
                yield return new DiagnosticDisplay("quota-loading", T("账户额度读取中", "Reading account quota"), T("如果长时间无数据，请确认 Codex 已安装并完成登录。", "If data does not appear, make sure Codex is installed and signed in."), "\uE77B", "StatusInfoBrush");
            }
        }

        if (Snapshot.Local is null)
        {
            if (messages.Contains("state_5.sqlite", StringComparison.OrdinalIgnoreCase))
            {
                yield return new DiagnosticDisplay("sqlite-db", T("未找到本机 Codex 统计库", "Local Codex database not found"), T("打开 Codex 并至少完成一次会话后，再回到小组件点击刷新。", "Open Codex and complete at least one session, then refresh this widget."), "\uEDA2", "StatusWarningBrush");
            }
            else
            {
                yield return new DiagnosticDisplay("local-usage", T("本机统计暂不可用", "Local stats unavailable"), T("本机 token 和任务看板依赖 .codex 下的本地状态文件。", "Local tokens and the task board depend on Codex state files under .codex."), "\uE9D9", "StatusInfoBrush");
            }
        }

        if (Snapshot.Messages.Count > 0 && Snapshot.Local is not null)
        {
            foreach (var message in Snapshot.Messages.Take(2))
            {
                yield return new DiagnosticDisplay("message-" + message.GetHashCode().ToString("X", CultureInfo.InvariantCulture), T("运行提示", "Runtime note"), LocalizedReaderMessage(message), "\uE946", "StatusInfoBrush");
            }
        }
    }

    private string ResetText(RateWindow? window)
    {
        if (window?.ResetsAt is null)
        {
            return "--";
        }

        return window.ResetsAt.Value.LocalDateTime.Date == DateTime.Now.Date
            ? TimeOnly(window.ResetsAt.Value)
            : window.ResetsAt.Value.LocalDateTime.ToString("M/d HH:mm", CultureInfo.InvariantCulture);
    }

    private string TimeOnly(DateTimeOffset date) =>
        date.LocalDateTime.ToString("HH:mm", CultureInfo.InvariantCulture);

    private string LocalizedReaderMessage(string message)
    {
        if (Language == WidgetLanguage.Zh)
        {
            return message;
        }

        if (message == "正在读取 codexU 数据") return "Reading codexU data";
        if (message.Contains("未找到 codex", StringComparison.OrdinalIgnoreCase)) return "Codex executable not found";
        if (message.Contains("app-server 启动失败", StringComparison.OrdinalIgnoreCase)) return "Failed to start app-server";
        if (message.Contains("app-server 响应超时", StringComparison.OrdinalIgnoreCase)) return "app-server response timed out";
        if (message.Contains("state_5.sqlite", StringComparison.OrdinalIgnoreCase)) return "Codex state_5.sqlite not found";
        if (message.Contains("SQLite 查询失败", StringComparison.OrdinalIgnoreCase)) return "SQLite query failed";
        if (message.Contains("session 日志", StringComparison.OrdinalIgnoreCase)) return "Codex session logs not found";
        if (message.Contains("token_count", StringComparison.OrdinalIgnoreCase)) return "Codex token_count events not found";
        if (message.Contains("任务看板", StringComparison.OrdinalIgnoreCase)) return "Task board data source unavailable";
        return message.Replace("未知错误", "Unknown error", StringComparison.Ordinal);
    }

    private string T(string zh, string en) => Language == WidgetLanguage.Zh ? zh : en;

    private static string FormatTokens(long? value)
    {
        if (value is null)
        {
            return "--";
        }

        var abs = Math.Abs((double)value.Value);
        if (abs >= 1_000_000)
        {
            return (value.Value / 1_000_000d).ToString("0.0M", CultureInfo.InvariantCulture);
        }

        if (abs >= 1_000)
        {
            return (value.Value / 1_000d).ToString("0.0K", CultureInfo.InvariantCulture);
        }

        return value.Value.ToString(CultureInfo.InvariantCulture);
    }

    private static string FormatUsd(double? value)
    {
        if (value is null)
        {
            return "--";
        }

        return Math.Abs(value.Value) >= 1_000
            ? value.Value.ToString("$0", CultureInfo.InvariantCulture)
            : value.Value.ToString("$0.00", CultureInfo.InvariantCulture);
    }

    private static string FormatCompactUsd(double value)
    {
        var abs = Math.Abs(value);
        if (abs >= 1_000_000)
        {
            return (value / 1_000_000d).ToString("$0.0M", CultureInfo.InvariantCulture);
        }

        if (abs >= 10_000)
        {
            return (value / 1_000d).ToString("$0.0K", CultureInfo.InvariantCulture);
        }

        return value.ToString("$0", CultureInfo.InvariantCulture);
    }

    private void RaiseAllDisplayProperties() => OnPropertyChanged(string.Empty);

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}

public sealed record OptionItem<T>(string Label, T Value);

public sealed record DiagnosticDisplay(string Id, string Title, string Detail, string Glyph, string BrushKey);

public sealed class TaskColumnDisplay
{
    private TaskColumnDisplay(TaskColumnKind kind, string title, int count, IReadOnlyList<TaskItemDisplay> items, string iconGlyph)
    {
        Kind = kind;
        Title = title;
        Count = count;
        Items = items;
        IconGlyph = iconGlyph;
    }

    public TaskColumnKind Kind { get; }
    public string Title { get; }
    public int Count { get; }
    public IReadOnlyList<TaskItemDisplay> Items { get; }
    public string IconGlyph { get; }
    public bool HasItems => Items.Count > 0;
    public bool HasOverflow => Count > Items.Count;
    public string OverflowText { get; private init; } = "";
    public string EmptyText { get; private init; } = "";

    public static TaskColumnDisplay From(TaskColumn column, WidgetLanguage language)
    {
        var items = column.Items.Select(item => TaskItemDisplay.From(item, language)).ToList();
        return new TaskColumnDisplay(
            column.Id,
            LocalizedColumnTitle(column.Id, language),
            column.Count,
            items,
            ColumnGlyph(column.Id))
        {
            OverflowText = language == WidgetLanguage.Zh ? $"+ {Math.Max(0, column.Count - items.Count)} 项" : $"+ {Math.Max(0, column.Count - items.Count)} more",
            EmptyText = language == WidgetLanguage.Zh ? "暂无" : "No items"
        };
    }

    private static string LocalizedColumnTitle(TaskColumnKind kind, WidgetLanguage language) =>
        (kind, language) switch
        {
            (TaskColumnKind.Active, WidgetLanguage.Zh) => "进行中",
            (TaskColumnKind.Pending, WidgetLanguage.Zh) => "待处理",
            (TaskColumnKind.Scheduled, WidgetLanguage.Zh) => "定时",
            (TaskColumnKind.Done, WidgetLanguage.Zh) => "完成",
            (TaskColumnKind.Active, _) => "Active",
            (TaskColumnKind.Pending, _) => "Pending",
            (TaskColumnKind.Scheduled, _) => "Scheduled",
            (TaskColumnKind.Done, _) => "Done",
            _ => ""
        };

    private static string ColumnGlyph(TaskColumnKind kind) =>
        kind switch
        {
            TaskColumnKind.Active => "\u25C9",
            TaskColumnKind.Pending => "\u25CB",
            TaskColumnKind.Scheduled => "\u25F7",
            TaskColumnKind.Done => "\u2713",
            _ => "\u25CB"
        };
}

public sealed class TaskItemDisplay
{
    private TaskItemDisplay(TaskItem item, WidgetLanguage language)
    {
        Kind = item.Kind;
        Code = item.Code;
        Title = item.Title;
        Detail = language == WidgetLanguage.En
            ? item.Detail
                .Replace("每天", "Daily", StringComparison.Ordinal)
                .Replace("每周", "Weekly", StringComparison.Ordinal)
                .Replace("每小时", "Hourly", StringComparison.Ordinal)
            : item.Detail;
        Chip = item.Chip;
        RelativeTime = item.UpdatedAt is null ? "" : RelativeTimeText(item.UpdatedAt.Value, language);
        Avatar = AvatarText(item);
    }

    public TaskColumnKind Kind { get; }
    public string Code { get; }
    public string Title { get; }
    public string Detail { get; }
    public string Chip { get; }
    public string RelativeTime { get; }
    public string Avatar { get; }

    public static TaskItemDisplay From(TaskItem item, WidgetLanguage language) => new(item, language);

    private static string RelativeTimeText(DateTimeOffset date, WidgetLanguage language)
    {
        var seconds = Math.Max(0, (int)(DateTimeOffset.Now - date).TotalSeconds);
        if (seconds < 60)
        {
            return language == WidgetLanguage.Zh ? "刚刚" : "just now";
        }

        var minutes = seconds / 60;
        if (minutes < 60)
        {
            return language == WidgetLanguage.Zh ? $"{minutes} 分钟前" : $"{minutes}m ago";
        }

        var hours = minutes / 60;
        if (hours < 24)
        {
            return language == WidgetLanguage.Zh ? $"{hours} 小时前" : $"{hours}h ago";
        }

        return language == WidgetLanguage.Zh ? $"{hours / 24} 天前" : $"{hours / 24}d ago";
    }

    private static string AvatarText(TaskItem item)
    {
        if (item.Code.StartsWith("AUTO", StringComparison.OrdinalIgnoreCase))
        {
            return "B";
        }

        var source = item.Detail.Split('·').FirstOrDefault()?.Trim();
        return !string.IsNullOrWhiteSpace(source) ? source[0].ToString().ToUpperInvariant() : "C";
    }
}
