namespace CodexU.Windows.Models;

public enum TaskColumnKind
{
    Active,
    Pending,
    Scheduled,
    Done
}

public enum WidgetLanguage
{
    Zh,
    En
}

public enum WidgetThemeMode
{
    System,
    Light,
    Dark
}

public sealed record RateWindow(double UsedPercent, int? WindowDurationMins, DateTimeOffset? ResetsAt)
{
    public double RemainingPercent => Math.Clamp(100.0 - UsedPercent, 0.0, 100.0);
}

public sealed record CreditsInfo(bool HasCredits, bool Unlimited, string? Balance, int? ResetCredits);

public sealed record AccountInfo(string Type, string? PlanType, bool EmailPresent);

public sealed record LocalThread(
    string Id,
    string Title,
    long Tokens,
    DateTimeOffset? UpdatedAt,
    string? Model,
    string Cwd,
    bool Archived);

public sealed record DailyTokenBucket(string Id, string Label, long Tokens);

public readonly record struct TokenBreakdown(
    long InputTokens,
    long CachedInputTokens,
    long OutputTokens,
    long ReasoningOutputTokens,
    long TotalTokens)
{
    public static TokenBreakdown Zero { get; } = new(0, 0, 0, 0, 0);

    public long BillableCachedInputTokens => Math.Min(Math.Max(CachedInputTokens, 0), Math.Max(InputTokens, 0));

    public long UncachedInputTokens => Math.Max(0, InputTokens - BillableCachedInputTokens);

    public long VisibleTotalTokens => Math.Max(TotalTokens, InputTokens + OutputTokens);

    public long SplitTotalTokens => Math.Max(UncachedInputTokens + BillableCachedInputTokens + Math.Max(OutputTokens, 0), 0);

    public bool IsZero =>
        InputTokens == 0 &&
        CachedInputTokens == 0 &&
        OutputTokens == 0 &&
        ReasoningOutputTokens == 0 &&
        TotalTokens == 0;

    public bool HasNegativeValue =>
        InputTokens < 0 ||
        CachedInputTokens < 0 ||
        OutputTokens < 0 ||
        ReasoningOutputTokens < 0 ||
        TotalTokens < 0;

    public TokenBreakdown Add(TokenBreakdown other) =>
        new(
            InputTokens + other.InputTokens,
            CachedInputTokens + other.CachedInputTokens,
            OutputTokens + other.OutputTokens,
            ReasoningOutputTokens + other.ReasoningOutputTokens,
            TotalTokens + other.TotalTokens);

    public TokenBreakdown DeltaFrom(TokenBreakdown previous) =>
        new(
            InputTokens - previous.InputTokens,
            CachedInputTokens - previous.CachedInputTokens,
            OutputTokens - previous.OutputTokens,
            ReasoningOutputTokens - previous.ReasoningOutputTokens,
            TotalTokens - previous.TotalTokens);
}

public readonly record struct PricedTokenUsage(TokenBreakdown Tokens, double EstimatedCostUsd)
{
    public static PricedTokenUsage Zero { get; } = new(TokenBreakdown.Zero, 0);

    public PricedTokenUsage Add(TokenBreakdown addedTokens, double costUsd) =>
        new(Tokens.Add(addedTokens), EstimatedCostUsd + costUsd);
}

public sealed record DetailedUsage(
    PricedTokenUsage Today,
    PricedTokenUsage SevenDay,
    PricedTokenUsage Month,
    PricedTokenUsage Lifetime,
    int ParsedFileCount,
    int TokenEventCount);

public sealed record LocalUsage(
    long LifetimeTokens,
    long TodayTokens,
    long SevenDayTokens,
    int ThreadCount,
    DateTimeOffset? LastUpdatedAt,
    IReadOnlyList<DailyTokenBucket> DailyBuckets,
    IReadOnlyList<LocalThread> RecentThreads,
    DetailedUsage? DetailedUsage);

public sealed record TaskItem(
    string Id,
    string Code,
    string Title,
    string Detail,
    string Chip,
    DateTimeOffset? UpdatedAt,
    long? Tokens,
    TaskColumnKind Kind);

public sealed record TaskColumn(TaskColumnKind Id, string Title, int Count, IReadOnlyList<TaskItem> Items);

public sealed record TaskBoard(DateTimeOffset RefreshedAt, IReadOnlyList<TaskColumn> Columns)
{
    public int TotalCount => Columns.Sum(column => column.Count);
}

public sealed record UsageSnapshot(
    DateTimeOffset RefreshedAt,
    AccountInfo? Account,
    string? LimitId,
    string? LimitName,
    RateWindow? Primary,
    RateWindow? Secondary,
    CreditsInfo? Credits,
    long? CloudLifetimeTokens,
    LocalUsage? Local,
    TaskBoard? TaskBoard,
    IReadOnlyList<string> Messages)
{
    public static UsageSnapshot Empty { get; } = new(
        DateTimeOffset.Now,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        new[] { "正在读取 codexU 数据" });

    public UsageSnapshot WithTaskBoard(TaskBoard? taskBoard) =>
        this with { TaskBoard = taskBoard };
}
