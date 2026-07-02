namespace CodexU.Windows.Services;

public sealed class CodexDataLocations
{
    public CodexDataLocations(string codexHomePath)
    {
        CodexHomePath = codexHomePath;
    }

    public string CodexHomePath { get; }

    public IReadOnlyList<string> StateDatabaseCandidates => new[]
    {
        Path.Combine(CodexHomePath, "state_5.sqlite"),
        Path.Combine(CodexHomePath, "sqlite", "state_5.sqlite")
    };

    public string SessionsDirectory => Path.Combine(CodexHomePath, "sessions");

    public string ArchivedSessionsDirectory => Path.Combine(CodexHomePath, "archived_sessions");

    public string AutomationsDirectory => Path.Combine(CodexHomePath, "automations");

    public static CodexDataLocations Current()
    {
        var overrideHome = Environment.GetEnvironmentVariable("CODEX_HOME")?.Trim();
        if (!string.IsNullOrWhiteSpace(overrideHome))
        {
            return new CodexDataLocations(Environment.ExpandEnvironmentVariables(overrideHome));
        }

        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (string.IsNullOrWhiteSpace(profile))
        {
            profile = Environment.GetEnvironmentVariable("USERPROFILE") ?? "";
        }

        return new CodexDataLocations(Path.Combine(profile, ".codex"));
    }
}
