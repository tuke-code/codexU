using System.Collections.Concurrent;
using System.Globalization;
using System.Text.Json;
using CodexU.Windows.Models;
using Microsoft.Data.Sqlite;

namespace CodexU.Windows.Services;

public sealed class CodexUsageReader
{
    private static readonly ConcurrentDictionary<string, SessionUsageCacheEntry> SessionUsageCache = new();
    private readonly CodexAppServerClient _appServerClient = new();
    private readonly CodexDataLocations _locations;

    public CodexUsageReader()
        : this(CodexDataLocations.Current())
    {
    }

    public CodexUsageReader(CodexDataLocations locations)
    {
        _locations = locations;
    }

    public async Task<UsageSnapshot> LoadAsync(CancellationToken cancellationToken = default)
    {
        var messages = new List<string>();
        var appServer = await _appServerClient.ReadAsync(messages, cancellationToken).ConfigureAwait(false);
        var local = ReadLocalUsage(messages);
        var taskBoard = ReadTaskBoard(messages);

        return new UsageSnapshot(
            DateTimeOffset.Now,
            appServer.Account,
            appServer.LimitId,
            appServer.LimitName,
            appServer.Primary,
            appServer.Secondary,
            appServer.Credits,
            appServer.CloudLifetimeTokens,
            local,
            taskBoard,
            messages);
    }

    public Task<TaskBoard?> LoadTaskBoardAsync(CancellationToken cancellationToken = default)
    {
        return Task.Run(() =>
        {
            var messages = new List<string>();
            return ReadTaskBoard(messages);
        }, cancellationToken);
    }

    private LocalUsage? ReadLocalUsage(ICollection<string> messages)
    {
        var dbPath = FirstExistingFile(_locations.StateDatabaseCandidates);
        var now = DateTimeOffset.Now;
        var dayStart = new DateTimeOffset(now.LocalDateTime.Date, now.Offset);
        var sevenDayStart = dayStart.AddDays(-6);

        var recent = new List<LocalThread>();
        var threadSources = new List<SessionUsageSource>();
        IReadOnlyList<DailyTokenBucket>? dailyBuckets = null;
        long? lifetimeTokens = null;
        long? todayTokens = null;
        long? sevenDayTokens = null;
        int threadCount = 0;
        DateTimeOffset? lastUpdatedAt = null;

        if (dbPath is null)
        {
            messages.Add("未找到 Codex state_5.sqlite");
        }
        else
        {
            try
            {
                using var connection = OpenReadOnlyConnection(dbPath);
                var totals = QueryRows(connection, $"""
                    SELECT
                      COALESCE(SUM(tokens_used), 0) AS lifetimeTokens,
                      COALESCE(SUM(CASE WHEN updated_at >= {dayStart.ToUnixTimeSeconds()} THEN tokens_used ELSE 0 END), 0) AS todayTokens,
                      COALESCE(SUM(CASE WHEN updated_at >= {sevenDayStart.ToUnixTimeSeconds()} THEN tokens_used ELSE 0 END), 0) AS sevenDayTokens,
                      COUNT(*) AS threadCount,
                      COALESCE(MAX(updated_at), 0) AS lastUpdatedAt
                    FROM threads;
                    """).FirstOrDefault();

                if (totals is not null)
                {
                    lifetimeTokens = LongValue(totals.GetValueOrDefault("lifetimeTokens")) ?? 0;
                    todayTokens = LongValue(totals.GetValueOrDefault("todayTokens")) ?? 0;
                    sevenDayTokens = LongValue(totals.GetValueOrDefault("sevenDayTokens")) ?? 0;
                    threadCount = IntValue(totals.GetValueOrDefault("threadCount")) ?? 0;
                    lastUpdatedAt = DateFromEpoch(totals.GetValueOrDefault("lastUpdatedAt"));
                }

                recent = QueryRows(connection, """
                    SELECT id, title, tokens_used AS tokens, updated_at AS updatedAt, model, cwd, archived
                    FROM threads
                    ORDER BY updated_at DESC
                    LIMIT 5;
                    """)
                    .Select(row => new LocalThread(
                        StringValue(row.GetValueOrDefault("id")) ?? Guid.NewGuid().ToString("N"),
                        StringValue(row.GetValueOrDefault("title")) ?? "Untitled",
                        LongValue(row.GetValueOrDefault("tokens")) ?? 0,
                        DateFromEpoch(row.GetValueOrDefault("updatedAt")),
                        StringValue(row.GetValueOrDefault("model")),
                        StringValue(row.GetValueOrDefault("cwd")) ?? "",
                        (IntValue(row.GetValueOrDefault("archived")) ?? 0) != 0))
                    .ToList();

                var tokensByDay = QueryRows(connection, $"""
                    SELECT date(updated_at, 'unixepoch', 'localtime') AS day, COALESCE(SUM(tokens_used), 0) AS tokens
                    FROM threads
                    WHERE updated_at >= {sevenDayStart.ToUnixTimeSeconds()}
                    GROUP BY day
                    ORDER BY day ASC;
                    """)
                    .Select(row => new
                    {
                        Day = StringValue(row.GetValueOrDefault("day")),
                        Tokens = LongValue(row.GetValueOrDefault("tokens")) ?? 0
                    })
                    .Where(row => !string.IsNullOrWhiteSpace(row.Day))
                    .ToDictionary(row => row.Day!, row => row.Tokens);

                dailyBuckets = MakeDailyBuckets(dayStart, tokensByDay);

                threadSources = QueryRows(connection, """
                    SELECT rollout_path AS rolloutPath, model
                    FROM threads
                    WHERE rollout_path IS NOT NULL
                      AND rollout_path <> ''
                      AND tokens_used > 0
                    ORDER BY updated_at ASC;
                    """)
                    .Select(row => new SessionUsageSource(
                        StringValue(row.GetValueOrDefault("rolloutPath")) ?? "",
                        StringValue(row.GetValueOrDefault("model"))))
                    .Where(source => !string.IsNullOrWhiteSpace(source.RolloutPath))
                    .ToList();
            }
            catch (Exception ex) when (ex is SqliteException or InvalidOperationException)
            {
                messages.Add($"SQLite 查询失败: {ex.Message}");
            }
        }

        var detailedResult = ReadDetailedUsage(threadSources, dayStart, sevenDayStart, messages);
        var detailedUsage = detailedResult?.Usage;
        dailyBuckets ??= MakeDailyBuckets(dayStart, detailedResult?.DailyTokenTotals ?? new Dictionary<string, long>());

        if (dbPath is null && detailedUsage is null)
        {
            return null;
        }

        return new LocalUsage(
            lifetimeTokens ?? detailedUsage?.Lifetime.Tokens.VisibleTotalTokens ?? 0,
            todayTokens ?? detailedUsage?.Today.Tokens.VisibleTotalTokens ?? 0,
            sevenDayTokens ?? detailedUsage?.SevenDay.Tokens.VisibleTotalTokens ?? 0,
            threadCount,
            lastUpdatedAt,
            dailyBuckets,
            recent,
            detailedUsage);
    }

    private DetailedUsageResult? ReadDetailedUsage(
        IEnumerable<SessionUsageSource> dbSources,
        DateTimeOffset dayStart,
        DateTimeOffset sevenDayStart,
        ICollection<string> messages)
    {
        var sources = new List<SessionUsageSource>();
        var seenPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var source in dbSources)
        {
            var normalized = NormalizePath(source.RolloutPath);
            if (!string.IsNullOrWhiteSpace(normalized) && seenPaths.Add(normalized))
            {
                sources.Add(source with { RolloutPath = normalized });
            }
        }

        foreach (var file in EnumerateSessionFiles())
        {
            var normalized = NormalizePath(file);
            if (!string.IsNullOrWhiteSpace(normalized) && seenPaths.Add(normalized))
            {
                sources.Add(new SessionUsageSource(normalized, null));
            }
        }

        if (sources.Count == 0)
        {
            messages.Add("未找到 Codex session 日志");
            return null;
        }

        var monthStart = new DateTimeOffset(new DateTime(dayStart.Year, dayStart.Month, 1), dayStart.Offset);
        var accumulator = new DetailedUsageAccumulator();
        var dailyTotals = new Dictionary<string, long>();

        foreach (var source in sources)
        {
            var entry = CachedSessionUsage(source);
            if (entry is null)
            {
                continue;
            }

            if (entry.HasTokenEvents)
            {
                accumulator.ParsedFileCount++;
                accumulator.TokenEventCount += entry.TokenEventCount;
            }

            var price = ModelTokenPrice.For(source.Model);
            foreach (var delta in entry.Deltas)
            {
                accumulator.Add(delta.Tokens, delta.Date, price, dayStart, sevenDayStart, monthStart);
                if (delta.Date >= sevenDayStart)
                {
                    var key = delta.Date.LocalDateTime.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
                    dailyTotals[key] = dailyTotals.GetValueOrDefault(key) + delta.Tokens.VisibleTotalTokens;
                }
            }
        }

        if (accumulator.ParsedFileCount == 0 || accumulator.TokenEventCount == 0)
        {
            messages.Add("未找到 Codex token_count 事件");
            return null;
        }

        return new DetailedUsageResult(accumulator.MakeUsage(), dailyTotals);
    }

    private SessionUsageCacheEntry? CachedSessionUsage(SessionUsageSource source)
    {
        if (!File.Exists(source.RolloutPath))
        {
            return null;
        }

        var info = new FileInfo(source.RolloutPath);
        if (SessionUsageCache.TryGetValue(source.RolloutPath, out var cached) &&
            cached.FileSize == info.Length &&
            cached.LastWriteUtc == info.LastWriteTimeUtc)
        {
            return cached;
        }

        var parsed = ParseSessionUsageFile(source.RolloutPath);
        var entry = new SessionUsageCacheEntry(
            info.Length,
            info.LastWriteTimeUtc,
            parsed.HasTokenEvents,
            parsed.TokenEventCount,
            parsed.Deltas);
        SessionUsageCache[source.RolloutPath] = entry;
        return entry;
    }

    private static (bool HasTokenEvents, int TokenEventCount, IReadOnlyList<SessionUsageDelta> Deltas) ParseSessionUsageFile(string path)
    {
        var previous = TokenBreakdown.Zero;
        var sawTokenEvent = false;
        var tokenEventCount = 0;
        var deltas = new List<SessionUsageDelta>();

        try
        {
            using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream);
            while (reader.ReadLine() is { } line)
            {
                if (!line.Contains("\"type\":\"token_count\"", StringComparison.Ordinal))
                {
                    continue;
                }

                ProcessUsageLine(line, ref previous, ref sawTokenEvent, ref tokenEventCount, deltas);
            }
        }
        catch
        {
            return (false, 0, Array.Empty<SessionUsageDelta>());
        }

        return (sawTokenEvent, tokenEventCount, deltas);
    }

    private static void ProcessUsageLine(
        string line,
        ref TokenBreakdown previous,
        ref bool sawTokenEvent,
        ref int tokenEventCount,
        ICollection<SessionUsageDelta> deltas)
    {
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            if (!root.TryGetProperty("timestamp", out var timestampElement) ||
                timestampElement.GetString() is not { } timestamp ||
                !root.TryGetProperty("payload", out var payload) ||
                StringValue(payload, "type") != "token_count" ||
                !payload.TryGetProperty("info", out var info) ||
                !info.TryGetProperty("total_token_usage", out var totalUsage) ||
                !DateTimeOffset.TryParse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var date))
            {
                return;
            }

            sawTokenEvent = true;
            tokenEventCount++;

            var current = new TokenBreakdown(
                LongValue(totalUsage, "input_tokens") ?? 0,
                LongValue(totalUsage, "cached_input_tokens") ?? 0,
                LongValue(totalUsage, "output_tokens") ?? 0,
                LongValue(totalUsage, "reasoning_output_tokens") ?? 0,
                LongValue(totalUsage, "total_tokens") ?? 0);

            var delta = current.DeltaFrom(previous);
            if (delta.HasNegativeValue)
            {
                delta = current;
            }

            previous = current;
            if (!delta.IsZero)
            {
                deltas.Add(new SessionUsageDelta(date.ToLocalTime(), delta));
            }
        }
        catch
        {
            // Ignore malformed JSONL lines. Codex may append partial lines while writing.
        }
    }

    private TaskBoard ReadTaskBoard(ICollection<string> messages)
    {
        var now = DateTimeOffset.Now;
        var dayStart = new DateTimeOffset(now.LocalDateTime.Date, now.Offset);
        var activeCutoff = now.AddHours(-2);
        var activeItems = new List<TaskItem>();
        var pendingItems = new List<TaskItem>();
        var doneItems = new List<TaskItem>();

        var dbPath = FirstExistingFile(_locations.StateDatabaseCandidates);
        if (dbPath is null)
        {
            messages.Add("任务看板未找到 SQLite 数据源");
        }
        else
        {
            try
            {
                using var connection = OpenReadOnlyConnection(dbPath);
                var todayThreads = QueryRows(connection, $"""
                    SELECT id, title, preview, cwd, tokens_used AS tokens, updated_at AS updatedAt, recency_at AS recencyAt, model
                    FROM threads
                    WHERE archived = 0
                      AND preview <> ''
                      AND (
                        updated_at >= {dayStart.ToUnixTimeSeconds()}
                        OR recency_at >= {dayStart.ToUnixTimeSeconds()}
                        OR created_at >= {dayStart.ToUnixTimeSeconds()}
                      )
                    ORDER BY recency_at DESC, updated_at DESC
                    LIMIT 24;
                    """);

                foreach (var row in todayThreads)
                {
                    var updatedAt = DateFromEpoch(row.GetValueOrDefault("recencyAt")) ?? DateFromEpoch(row.GetValueOrDefault("updatedAt"));
                    var kind = (updatedAt ?? DateTimeOffset.MinValue) >= activeCutoff ? TaskColumnKind.Active : TaskColumnKind.Pending;
                    var item = MakeThreadTaskItem(row, updatedAt, kind);
                    if (kind == TaskColumnKind.Active)
                    {
                        activeItems.Add(item);
                    }
                    else
                    {
                        pendingItems.Add(item);
                    }
                }

                doneItems = QueryRows(connection, $"""
                    SELECT id, title, preview, cwd, tokens_used AS tokens, COALESCE(archived_at, updated_at) AS updatedAt, model
                    FROM threads
                    WHERE archived = 1
                      AND COALESCE(archived_at, updated_at) >= {dayStart.ToUnixTimeSeconds()}
                    ORDER BY COALESCE(archived_at, updated_at) DESC
                    LIMIT 12;
                    """)
                    .Select(row => MakeThreadTaskItem(row, DateFromEpoch(row.GetValueOrDefault("updatedAt")), TaskColumnKind.Done))
                    .ToList();
            }
            catch (Exception ex) when (ex is SqliteException or InvalidOperationException)
            {
                messages.Add($"任务看板 SQLite 查询失败: {ex.Message}");
            }
        }

        var scheduledItems = ReadAutomationTasks();
        return new TaskBoard(DateTimeOffset.Now, new[]
        {
            new TaskColumn(TaskColumnKind.Active, "进行中", activeItems.Count, activeItems.Take(3).ToList()),
            new TaskColumn(TaskColumnKind.Pending, "待处理", pendingItems.Count, pendingItems.Take(3).ToList()),
            new TaskColumn(TaskColumnKind.Scheduled, "定时", scheduledItems.Count, scheduledItems.Take(3).ToList()),
            new TaskColumn(TaskColumnKind.Done, "完成", doneItems.Count, doneItems.Take(3).ToList())
        });
    }

    private TaskItem MakeThreadTaskItem(IReadOnlyDictionary<string, object?> row, DateTimeOffset? updatedAt, TaskColumnKind kind)
    {
        var rawId = StringValue(row.GetValueOrDefault("id")) ?? Guid.NewGuid().ToString("N");
        var title = NormalizedTitle(
            StringValue(row.GetValueOrDefault("title")),
            StringValue(row.GetValueOrDefault("preview")));
        var cwd = StringValue(row.GetValueOrDefault("cwd")) ?? "";
        var tokens = LongValue(row.GetValueOrDefault("tokens")) ?? 0;
        var compactId = rawId.Replace("-", "", StringComparison.Ordinal);
        var suffix = compactId.Length <= 4 ? compactId : compactId[^4..];
        var code = "COD-" + suffix.ToUpperInvariant();
        var chip = kind switch
        {
            TaskColumnKind.Active => tokens >= 5_000_000 ? "High" : "Active",
            TaskColumnKind.Pending => tokens >= 2_000_000 ? "Medium" : "Idle",
            TaskColumnKind.Scheduled => "Cron",
            TaskColumnKind.Done => "Done",
            _ => "Task"
        };

        var detailParts = new[]
        {
            ShortWorkspaceName(cwd),
            tokens > 0 ? FormatTokens(tokens) : null
        }.Where(part => !string.IsNullOrWhiteSpace(part));

        return new TaskItem(
            rawId + kind,
            code,
            title,
            string.Join(" · ", detailParts),
            chip,
            updatedAt,
            tokens,
            kind);
    }

    private IReadOnlyList<TaskItem> ReadAutomationTasks()
    {
        if (!Directory.Exists(_locations.AutomationsDirectory))
        {
            return Array.Empty<TaskItem>();
        }

        var items = new List<TaskItem>();
        foreach (var file in SafeEnumerateFiles(_locations.AutomationsDirectory, "automation.toml", SearchOption.AllDirectories))
        {
            string text;
            try
            {
                text = File.ReadAllText(file);
            }
            catch
            {
                continue;
            }

            var fields = ParseSimpleToml(text);
            if (!fields.TryGetValue("status", out var status) || !status.Equals("ACTIVE", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var id = fields.GetValueOrDefault("id") ?? Path.GetFileName(Path.GetDirectoryName(file)) ?? Guid.NewGuid().ToString("N");
            var name = fields.GetValueOrDefault("name") ?? id;
            var kind = fields.GetValueOrDefault("kind") ?? "cron";
            var schedule = ScheduleSummary(fields.GetValueOrDefault("rrule"));
            var detail = string.Join(" · ", new[] { kind.ToUpperInvariant(), schedule }.Where(part => !string.IsNullOrWhiteSpace(part)));

            items.Add(new TaskItem(
                "automation-" + id,
                "AUTO-" + id[..Math.Min(4, id.Length)].ToUpperInvariant(),
                name,
                detail,
                kind.Equals("heartbeat", StringComparison.OrdinalIgnoreCase) ? "Wake" : "Cron",
                DateFromEpoch(fields.GetValueOrDefault("updated_at")),
                null,
                TaskColumnKind.Scheduled));
        }

        return items.OrderBy(item => item.Title, StringComparer.CurrentCultureIgnoreCase).ToList();
    }

    private IEnumerable<string> EnumerateSessionFiles()
    {
        foreach (var file in SafeEnumerateFiles(_locations.SessionsDirectory, "rollout-*.jsonl", SearchOption.AllDirectories))
        {
            yield return file;
        }

        foreach (var file in SafeEnumerateFiles(_locations.ArchivedSessionsDirectory, "*.jsonl", SearchOption.AllDirectories))
        {
            yield return file;
        }
    }

    private static IEnumerable<string> SafeEnumerateFiles(string directory, string searchPattern, SearchOption searchOption)
    {
        if (!Directory.Exists(directory))
        {
            return Array.Empty<string>();
        }

        try
        {
            return Directory.EnumerateFiles(directory, searchPattern, searchOption).ToArray();
        }
        catch
        {
            return Array.Empty<string>();
        }
    }

    private static SqliteConnection OpenReadOnlyConnection(string dbPath)
    {
        var builder = new SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = SqliteOpenMode.ReadOnly,
            Cache = SqliteCacheMode.Shared
        };
        var connection = new SqliteConnection(builder.ToString());
        connection.Open();
        return connection;
    }

    private static List<Dictionary<string, object?>> QueryRows(SqliteConnection connection, string query)
    {
        using var command = connection.CreateCommand();
        command.CommandText = query;
        using var reader = command.ExecuteReader();
        var rows = new List<Dictionary<string, object?>>();
        while (reader.Read())
        {
            var row = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
            for (var i = 0; i < reader.FieldCount; i++)
            {
                row[reader.GetName(i)] = reader.IsDBNull(i) ? null : reader.GetValue(i);
            }

            rows.Add(row);
        }

        return rows;
    }

    private static IReadOnlyList<DailyTokenBucket> MakeDailyBuckets(DateTimeOffset dayStart, IReadOnlyDictionary<string, long> tokensByDay)
    {
        var buckets = new List<DailyTokenBucket>();
        for (var index = 0; index < 7; index++)
        {
            var date = dayStart.AddDays(index - 6);
            var key = date.LocalDateTime.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            var label = index == 6 ? "今天" : date.LocalDateTime.ToString("M/d", CultureInfo.GetCultureInfo("zh-CN"));
            buckets.Add(new DailyTokenBucket(key, label, tokensByDay.GetValueOrDefault(key)));
        }

        return buckets;
    }

    private static string? FirstExistingFile(IEnumerable<string> paths) =>
        paths.FirstOrDefault(File.Exists);

    private static string NormalizePath(string path)
    {
        try
        {
            return Path.GetFullPath(Environment.ExpandEnvironmentVariables(path));
        }
        catch
        {
            return path;
        }
    }

    private static Dictionary<string, string> ParseSimpleToml(string text)
    {
        var fields = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var rawLine in text.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith('#') || !line.Contains('='))
            {
                continue;
            }

            var separator = line.IndexOf('=');
            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim();
            if (value.Length >= 2 && value.StartsWith('"') && value.EndsWith('"'))
            {
                value = value[1..^1]
                    .Replace("\\n", "\n", StringComparison.Ordinal)
                    .Replace("\\\"", "\"", StringComparison.Ordinal);
            }

            fields[key] = value;
        }

        return fields;
    }

    private static string NormalizedTitle(string? title, string? fallback)
    {
        var raw = new[] { title, fallback }
            .Select(value => value?.Trim())
            .FirstOrDefault(value => !string.IsNullOrWhiteSpace(value)) ?? "Untitled";

        var singleLine = string.Join(" ", raw.Split(new[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries));
        return singleLine.Length <= 48 ? singleLine : singleLine[..45] + "...";
    }

    private static string ShortWorkspaceName(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return "";
        }

        var name = Path.GetFileName(path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        return string.IsNullOrWhiteSpace(name) ? path : name;
    }

    private static string ScheduleSummary(string? rrule)
    {
        if (string.IsNullOrWhiteSpace(rrule))
        {
            return "";
        }

        var timeText = "";
        var marker = rrule.IndexOf('T');
        if (marker >= 0 && marker + 5 < rrule.Length)
        {
            var digits = new string(rrule[(marker + 1)..].TakeWhile(char.IsDigit).ToArray());
            if (digits.Length >= 4)
            {
                timeText = digits[..2] + ":" + digits[2..4];
            }
        }

        if (rrule.Contains("FREQ=DAILY", StringComparison.OrdinalIgnoreCase))
        {
            return string.IsNullOrWhiteSpace(timeText) ? "每天" : $"每天 {timeText}";
        }

        if (rrule.Contains("FREQ=WEEKLY", StringComparison.OrdinalIgnoreCase))
        {
            return string.IsNullOrWhiteSpace(timeText) ? "每周" : $"每周 {timeText}";
        }

        if (rrule.Contains("FREQ=HOURLY", StringComparison.OrdinalIgnoreCase))
        {
            return "每小时";
        }

        return timeText;
    }

    private static string FormatTokens(long value)
    {
        var abs = Math.Abs((double)value);
        if (abs >= 1_000_000)
        {
            return (value / 1_000_000d).ToString("0.0M", CultureInfo.InvariantCulture);
        }

        if (abs >= 1_000)
        {
            return (value / 1_000d).ToString("0.0K", CultureInfo.InvariantCulture);
        }

        return value.ToString(CultureInfo.InvariantCulture);
    }

    private static DateTimeOffset? DateFromEpoch(object? value)
    {
        var seconds = DoubleValue(value);
        if (seconds is null || seconds <= 0)
        {
            return null;
        }

        return DateFromEpoch(seconds.Value);
    }

    private static DateTimeOffset? DateFromEpoch(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out var seconds))
        {
            return DateFromEpoch(seconds);
        }

        return DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.AssumeLocal, out var parsed)
            ? parsed
            : null;
    }

    private static DateTimeOffset DateFromEpoch(double seconds)
    {
        if (seconds > 10_000_000_000)
        {
            seconds /= 1000;
        }

        return DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(seconds)).ToLocalTime();
    }

    private static int? IntValue(object? value)
    {
        if (value is int intValue)
        {
            return intValue;
        }

        if (value is long longValue)
        {
            return Convert.ToInt32(longValue);
        }

        return int.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : null;
    }

    private static long? LongValue(object? value)
    {
        if (value is long longValue)
        {
            return longValue;
        }

        if (value is int intValue)
        {
            return intValue;
        }

        return long.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : null;
    }

    private static double? DoubleValue(object? value)
    {
        if (value is double doubleValue)
        {
            return doubleValue;
        }

        if (value is long longValue)
        {
            return longValue;
        }

        return double.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : null;
    }

    private static string? StringValue(object? value) =>
        Convert.ToString(value, CultureInfo.InvariantCulture);

    private static string? StringValue(JsonElement element, string propertyName) =>
        element.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static long? LongValue(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number))
        {
            return number;
        }

        return value.ValueKind == JsonValueKind.String &&
               long.TryParse(value.GetString(), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : null;
    }

    private sealed record SessionUsageSource(string RolloutPath, string? Model);

    private sealed record SessionUsageDelta(DateTimeOffset Date, TokenBreakdown Tokens);

    private sealed record SessionUsageCacheEntry(
        long FileSize,
        DateTime LastWriteUtc,
        bool HasTokenEvents,
        int TokenEventCount,
        IReadOnlyList<SessionUsageDelta> Deltas);

    private sealed record DetailedUsageResult(DetailedUsage Usage, IReadOnlyDictionary<string, long> DailyTokenTotals);

    private sealed record ModelTokenPrice(string Model, double InputPerMillion, double CachedInputPerMillion, double OutputPerMillion)
    {
        public static ModelTokenPrice For(string? model)
        {
            var normalized = (model ?? "").ToLowerInvariant();

            if (normalized.Contains("gpt-5.5-pro", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.5-pro", 30, 30, 180);
            }

            if (normalized.Contains("gpt-5.5", StringComparison.Ordinal) || normalized == "chat-latest")
            {
                return new ModelTokenPrice("gpt-5.5", 5, 0.5, 30);
            }

            if (normalized.Contains("gpt-5.4-mini", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.4-mini", 0.75, 0.075, 4.5);
            }

            if (normalized.Contains("gpt-5.4-nano", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.4-nano", 0.2, 0.02, 1.25);
            }

            if (normalized.Contains("gpt-5.4-pro", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.4-pro", 30, 30, 180);
            }

            if (normalized.Contains("gpt-5.4", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.4", 2.5, 0.25, 15);
            }

            if (normalized.Contains("gpt-5.3-codex", StringComparison.Ordinal) ||
                normalized.Contains("gpt-5.2-codex", StringComparison.Ordinal) ||
                normalized.Contains("gpt-5.3-chat", StringComparison.Ordinal) ||
                normalized.Contains("gpt-5.2", StringComparison.Ordinal))
            {
                return new ModelTokenPrice("gpt-5.2-codex", 1.75, 0.175, 14);
            }

            if (normalized.Contains("gpt-5-codex", StringComparison.Ordinal) || normalized == "gpt-5")
            {
                return new ModelTokenPrice("gpt-5", 1.25, 0.125, 10);
            }

            return new ModelTokenPrice("gpt-5.5", 5, 0.5, 30);
        }
    }

    private sealed class DetailedUsageAccumulator
    {
        public PricedTokenUsage Today { get; private set; } = PricedTokenUsage.Zero;
        public PricedTokenUsage SevenDay { get; private set; } = PricedTokenUsage.Zero;
        public PricedTokenUsage Month { get; private set; } = PricedTokenUsage.Zero;
        public PricedTokenUsage Lifetime { get; private set; } = PricedTokenUsage.Zero;
        public int ParsedFileCount { get; set; }
        public int TokenEventCount { get; set; }

        public void Add(
            TokenBreakdown tokens,
            DateTimeOffset date,
            ModelTokenPrice price,
            DateTimeOffset dayStart,
            DateTimeOffset sevenDayStart,
            DateTimeOffset monthStart)
        {
            var cost = EstimatedCostUsd(tokens, price);
            Lifetime = Lifetime.Add(tokens, cost);
            if (date >= monthStart)
            {
                Month = Month.Add(tokens, cost);
            }

            if (date >= sevenDayStart)
            {
                SevenDay = SevenDay.Add(tokens, cost);
            }

            if (date >= dayStart)
            {
                Today = Today.Add(tokens, cost);
            }
        }

        public DetailedUsage MakeUsage() =>
            new(Today, SevenDay, Month, Lifetime, ParsedFileCount, TokenEventCount);

        private static double EstimatedCostUsd(TokenBreakdown tokens, ModelTokenPrice price)
        {
            var uncachedInput = tokens.UncachedInputTokens / 1_000_000d * price.InputPerMillion;
            var cachedInput = tokens.BillableCachedInputTokens / 1_000_000d * price.CachedInputPerMillion;
            var output = Math.Max(tokens.OutputTokens, 0) / 1_000_000d * price.OutputPerMillion;
            return uncachedInput + cachedInput + output;
        }
    }
}
