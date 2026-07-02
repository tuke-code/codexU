using System.Globalization;
using System.Text.Json;
using CodexU.Windows.Models;

namespace CodexU.Windows.Services;

public sealed class LocalSettings
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public WidgetLanguage Language { get; set; } = AutomaticLanguage();

    public WidgetThemeMode ThemeMode { get; set; } = WidgetThemeMode.System;

    public bool StartPinnedTopmost { get; set; }

    public static LocalSettings Load()
    {
        try
        {
            var path = SettingsPath;
            if (File.Exists(path))
            {
                var settings = JsonSerializer.Deserialize<LocalSettings>(File.ReadAllText(path), JsonOptions);
                if (settings is not null)
                {
                    return settings;
                }
            }
        }
        catch
        {
            // Settings are a convenience. Corrupt or locked settings must not block the widget.
        }

        return new LocalSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
            File.WriteAllText(SettingsPath, JsonSerializer.Serialize(this, JsonOptions));
        }
        catch
        {
            // Ignore persistence failures; the UI remains usable for this session.
        }
    }

    private static string SettingsPath
    {
        get
        {
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            return Path.Combine(appData, "codexU", "windows-settings.json");
        }
    }

    private static WidgetLanguage AutomaticLanguage()
    {
        var culture = CultureInfo.CurrentUICulture;
        return culture.TwoLetterISOLanguageName.Equals("zh", StringComparison.OrdinalIgnoreCase)
            ? WidgetLanguage.Zh
            : WidgetLanguage.En;
    }
}
