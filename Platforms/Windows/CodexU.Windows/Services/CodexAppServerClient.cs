using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using CodexU.Windows.Models;

namespace CodexU.Windows.Services;

internal sealed record AppServerSnapshot(
    AccountInfo? Account = null,
    string? LimitId = null,
    string? LimitName = null,
    RateWindow? Primary = null,
    RateWindow? Secondary = null,
    CreditsInfo? Credits = null,
    long? CloudLifetimeTokens = null);

internal sealed class CodexAppServerClient
{
    public async Task<AppServerSnapshot> ReadAsync(ICollection<string> messages, CancellationToken cancellationToken)
    {
        var codexPath = FindCodexExecutable();
        if (codexPath is null)
        {
            messages.Add("未找到 codex 可执行文件");
            return new AppServerSnapshot();
        }

        using var process = new Process();
        process.StartInfo = new ProcessStartInfo
        {
            FileName = codexPath,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        process.StartInfo.ArgumentList.Add("app-server");

        try
        {
            process.Start();
        }
        catch
        {
            messages.Add("app-server 启动失败");
            return new AppServerSnapshot();
        }

        var snapshot = new MutableAppServerSnapshot();
        var completed = new HashSet<int>();
        var appServerMessages = new List<string>();
        var sentAccountRequests = false;
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutCts.CancelAfter(TimeSpan.FromSeconds(12));

        try
        {
            await WriteJsonLineAsync(process, new
            {
                id = 1,
                method = "initialize",
                @params = new
                {
                    clientInfo = new
                    {
                        name = "codexu-windows",
                        title = "codexU",
                        version = "0.1.0"
                    },
                    capabilities = new
                    {
                        experimentalApi = true,
                        optOutNotificationMethods = Array.Empty<string>()
                    }
                }
            }, timeoutCts.Token).ConfigureAwait(false);

            while (!timeoutCts.IsCancellationRequested && completed.Count < 3)
            {
                var line = await process.StandardOutput.ReadLineAsync(timeoutCts.Token).ConfigureAwait(false);
                if (line is null)
                {
                    break;
                }

                if (!TryParseResponse(line, out var document, out var id))
                {
                    continue;
                }

                using (document)
                {
                    var root = document.RootElement;
                    if (id == 1)
                    {
                        if (!sentAccountRequests)
                        {
                            sentAccountRequests = true;
                            await WriteJsonLineAsync(process, new { method = "initialized" }, timeoutCts.Token).ConfigureAwait(false);
                            await WriteJsonLineAsync(process, new { id = 2, method = "account/read", @params = new { refreshToken = false } }, timeoutCts.Token).ConfigureAwait(false);
                            await WriteJsonLineAsync(process, new { id = 3, method = "account/rateLimits/read" }, timeoutCts.Token).ConfigureAwait(false);
                            await WriteJsonLineAsync(process, new { id = 4, method = "account/usage/read" }, timeoutCts.Token).ConfigureAwait(false);
                        }

                        continue;
                    }

                    if (root.TryGetProperty("error", out var error))
                    {
                        var message = TryGetString(error, "message") ?? "未知错误";
                        appServerMessages.Add($"app-server {id}: {message}");
                        MarkComplete(completed, id);
                        continue;
                    }

                    if (!root.TryGetProperty("result", out var result))
                    {
                        MarkComplete(completed, id);
                        continue;
                    }

                    switch (id)
                    {
                        case 2:
                            snapshot.Account = ParseAccount(result);
                            break;
                        case 3:
                            ParseRateLimits(result, snapshot);
                            break;
                        case 4:
                            snapshot.CloudLifetimeTokens = ParseCloudLifetimeTokens(result);
                            break;
                    }

                    MarkComplete(completed, id);
                }
            }
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            appServerMessages.Add("app-server 响应超时");
        }
        catch (Exception ex)
        {
            appServerMessages.Add($"app-server: {ex.Message}");
        }
        finally
        {
            messages.AddRange(appServerMessages);
            TryClose(process);
        }

        return snapshot.ToImmutable();
    }

    private static void MarkComplete(ISet<int> completed, int id)
    {
        if (id is 2 or 3 or 4)
        {
            completed.Add(id);
        }
    }

    private static bool TryParseResponse(string line, out JsonDocument document, out int id)
    {
        document = null!;
        id = 0;

        try
        {
            document = JsonDocument.Parse(line);
            if (!document.RootElement.TryGetProperty("id", out var idElement))
            {
                document.Dispose();
                return false;
            }

            id = TryGetInt(idElement) ?? 0;
            return id != 0;
        }
        catch
        {
            document?.Dispose();
            return false;
        }
    }

    private static async Task WriteJsonLineAsync(Process process, object message, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(message);
        cancellationToken.ThrowIfCancellationRequested();
        await process.StandardInput.WriteLineAsync(json).ConfigureAwait(false);
        cancellationToken.ThrowIfCancellationRequested();
        await process.StandardInput.FlushAsync().ConfigureAwait(false);
    }

    private static AccountInfo? ParseAccount(JsonElement result)
    {
        if (!result.TryGetProperty("account", out var account))
        {
            return null;
        }

        var type = TryGetString(account, "type");
        if (string.IsNullOrWhiteSpace(type))
        {
            return null;
        }

        var emailPresent = account.TryGetProperty("email", out var email) && email.ValueKind != JsonValueKind.Null;
        return new AccountInfo(type, TryGetString(account, "planType"), emailPresent);
    }

    private static void ParseRateLimits(JsonElement result, MutableAppServerSnapshot snapshot)
    {
        JsonElement limits;
        if (result.TryGetProperty("rateLimitsByLimitId", out var byId) &&
            byId.TryGetProperty("codex", out var codex))
        {
            limits = codex;
        }
        else if (result.TryGetProperty("rateLimits", out var rateLimits))
        {
            limits = rateLimits;
        }
        else
        {
            return;
        }

        snapshot.LimitId = TryGetString(limits, "limitId");
        snapshot.LimitName = TryGetString(limits, "limitName");
        snapshot.Primary = ParseRateWindow(limits, "primary");
        snapshot.Secondary = ParseRateWindow(limits, "secondary");

        int? resetCredits = null;
        if (result.TryGetProperty("rateLimitResetCredits", out var reset))
        {
            resetCredits = TryGetInt(reset, "availableCount");
        }

        if (limits.TryGetProperty("credits", out var credits))
        {
            snapshot.Credits = new CreditsInfo(
                TryGetBool(credits, "hasCredits") ?? false,
                TryGetBool(credits, "unlimited") ?? false,
                TryGetString(credits, "balance"),
                resetCredits);
        }
        else if (resetCredits is not null)
        {
            snapshot.Credits = new CreditsInfo(false, false, null, resetCredits);
        }
    }

    private static RateWindow? ParseRateWindow(JsonElement parent, string propertyName)
    {
        if (!parent.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        var usedPercent = TryGetDouble(value, "usedPercent");
        if (usedPercent is null)
        {
            return null;
        }

        DateTimeOffset? resetsAt = null;
        var timestamp = TryGetDouble(value, "resetsAt");
        if (timestamp is not null)
        {
            resetsAt = DateFromEpoch(timestamp.Value);
        }

        return new RateWindow(
            usedPercent.Value,
            TryGetInt(value, "windowDurationMins"),
            resetsAt);
    }

    private static long? ParseCloudLifetimeTokens(JsonElement result)
    {
        if (!result.TryGetProperty("summary", out var summary))
        {
            return null;
        }

        return TryGetLong(summary, "lifetimeTokens");
    }

    private static string? FindCodexExecutable()
    {
        var overridePath = Environment.GetEnvironmentVariable("CODEX_EXECUTABLE")?.Trim();
        if (!string.IsNullOrWhiteSpace(overridePath) && File.Exists(overridePath))
        {
            return overridePath;
        }

        var candidates = new List<string>();
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        if (!string.IsNullOrWhiteSpace(localAppData))
        {
            candidates.Add(Path.Combine(localAppData, "Programs", "Codex", "codex.exe"));
            candidates.Add(Path.Combine(localAppData, "Codex", "codex.exe"));
        }

        if (!string.IsNullOrWhiteSpace(programFiles))
        {
            candidates.Add(Path.Combine(programFiles, "Codex", "codex.exe"));
        }

        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (var directory in path.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            candidates.Add(Path.Combine(directory, "codex.exe"));
            candidates.Add(Path.Combine(directory, "codex.cmd"));
            candidates.Add(Path.Combine(directory, "codex.bat"));
            candidates.Add(Path.Combine(directory, "codex"));
        }

        return candidates.FirstOrDefault(File.Exists);
    }

    private static void TryClose(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.StandardInput.Close();
                process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // Best effort process cleanup.
        }
    }

    private static DateTimeOffset DateFromEpoch(double seconds)
    {
        if (seconds > 10_000_000_000)
        {
            seconds /= 1000;
        }

        return DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(seconds)).ToLocalTime();
    }

    private static string? TryGetString(JsonElement element, string propertyName) =>
        element.TryGetProperty(propertyName, out var value) ? TryGetString(value) : null;

    private static string? TryGetString(JsonElement value) =>
        value.ValueKind switch
        {
            JsonValueKind.String => value.GetString(),
            JsonValueKind.Number => value.GetRawText(),
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            _ => null
        };

    private static int? TryGetInt(JsonElement element, string propertyName) =>
        element.TryGetProperty(propertyName, out var value) ? TryGetInt(value) : null;

    private static int? TryGetInt(JsonElement value) =>
        value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number)
            ? number
            : int.TryParse(TryGetString(value), out var parsed)
                ? parsed
                : null;

    private static long? TryGetLong(JsonElement element, string propertyName) =>
        element.TryGetProperty(propertyName, out var value) ? TryGetLong(value) : null;

    private static long? TryGetLong(JsonElement value) =>
        value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number)
            ? number
            : long.TryParse(TryGetString(value), out var parsed)
                ? parsed
                : null;

    private static double? TryGetDouble(JsonElement element, string propertyName) =>
        element.TryGetProperty(propertyName, out var value) ? TryGetDouble(value) : null;

    private static double? TryGetDouble(JsonElement value) =>
        value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number)
            ? number
            : double.TryParse(TryGetString(value), NumberStyles.Any, CultureInfo.InvariantCulture, out var parsed)
                ? parsed
                : null;

    private static bool? TryGetBool(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.String when bool.TryParse(value.GetString(), out var parsed) => parsed,
            _ => null
        };
    }

    private sealed class MutableAppServerSnapshot
    {
        public AccountInfo? Account { get; set; }
        public string? LimitId { get; set; }
        public string? LimitName { get; set; }
        public RateWindow? Primary { get; set; }
        public RateWindow? Secondary { get; set; }
        public CreditsInfo? Credits { get; set; }
        public long? CloudLifetimeTokens { get; set; }

        public AppServerSnapshot ToImmutable() =>
            new(Account, LimitId, LimitName, Primary, Secondary, Credits, CloudLifetimeTokens);
    }
}
