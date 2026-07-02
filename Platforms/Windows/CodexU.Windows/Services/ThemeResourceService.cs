using System.Windows;
using System.Windows.Media;
using CodexU.Windows.Models;
using Microsoft.Win32;

namespace CodexU.Windows.Services;

public static class ThemeResourceService
{
    public static bool IsDarkTheme(WidgetThemeMode mode)
    {
        return mode switch
        {
            WidgetThemeMode.Dark => true,
            WidgetThemeMode.Light => false,
            _ => IsSystemDarkTheme()
        };
    }

    public static void Apply(WidgetThemeMode mode)
    {
        if (Application.Current is null)
        {
            return;
        }

        var isDark = IsDarkTheme(mode);
        var resources = Application.Current.Resources;

        SetBrush(resources, "WindowBrush", isDark ? Color.FromArgb(245, 31, 33, 40) : Color.FromArgb(242, 247, 248, 250));
        SetBrush(resources, "WindowStrokeBrush", isDark ? Color.FromArgb(36, 255, 255, 255) : Color.FromArgb(38, 0, 0, 0));
        SetBrush(resources, "SectionBrush", isDark ? Color.FromArgb(28, 255, 255, 255) : Color.FromArgb(124, 255, 255, 255));
        SetBrush(resources, "SectionStrokeBrush", isDark ? Color.FromArgb(24, 255, 255, 255) : Color.FromArgb(16, 0, 0, 0));
        SetBrush(resources, "CardBrush", isDark ? Color.FromArgb(28, 255, 255, 255) : Color.FromArgb(174, 255, 255, 255));
        SetBrush(resources, "CardElevatedBrush", isDark ? Color.FromArgb(38, 255, 255, 255) : Color.FromArgb(232, 255, 255, 255));
        SetBrush(resources, "CardStrokeBrush", isDark ? Color.FromArgb(28, 255, 255, 255) : Color.FromArgb(18, 0, 0, 0));
        SetBrush(resources, "ControlBrush", isDark ? Color.FromArgb(30, 255, 255, 255) : Color.FromArgb(130, 255, 255, 255));
        SetBrush(resources, "ControlStrokeBrush", isDark ? Color.FromArgb(24, 255, 255, 255) : Color.FromArgb(18, 0, 0, 0));
        SetBrush(resources, "SurfaceTrackBrush", isDark ? Color.FromArgb(28, 255, 255, 255) : Color.FromArgb(24, 0, 0, 0));
        SetBrush(resources, "TextPrimaryBrush", isDark ? Color.FromArgb(235, 255, 255, 255) : Color.FromArgb(232, 0, 0, 0));
        SetBrush(resources, "TextSecondaryBrush", isDark ? Color.FromArgb(166, 255, 255, 255) : Color.FromArgb(153, 0, 0, 0));
        SetBrush(resources, "TextTertiaryBrush", isDark ? Color.FromArgb(112, 255, 255, 255) : Color.FromArgb(102, 0, 0, 0));
        SetBrush(resources, "BrandPrimaryBrush", isDark ? Color.FromRgb(94, 140, 255) : Color.FromRgb(40, 102, 247));
        SetBrush(resources, "BrandStrongBrush", isDark ? Color.FromRgb(123, 160, 255) : Color.FromRgb(31, 89, 237));
        SetBrush(resources, "BrandLightBrush", Color.FromRgb(123, 160, 255));
        SetBrush(resources, "BrandSecondaryBrush", isDark ? Color.FromRgb(161, 149, 244) : Color.FromRgb(139, 109, 255));
        SetBrush(resources, "BrandHighlightBrush", isDark ? Color.FromRgb(231, 184, 255) : Color.FromRgb(218, 163, 250));
        SetBrush(resources, "StatusSuccessBrush", isDark ? Color.FromRgb(48, 209, 88) : Color.FromRgb(52, 199, 89));
        SetBrush(resources, "StatusInfoBrush", isDark ? Color.FromRgb(10, 132, 255) : Color.FromRgb(0, 122, 255));
        SetBrush(resources, "StatusWarningBrush", Color.FromRgb(255, 159, 10));
        SetBrush(resources, "StatusDangerBrush", isDark ? Color.FromRgb(255, 69, 58) : Color.FromRgb(255, 59, 48));
        SetBrush(resources, "StatusNeutralBrush", isDark ? Color.FromRgb(152, 152, 157) : Color.FromRgb(142, 142, 147));
        SetBrush(resources, "DataZeroBrush", isDark ? Color.FromArgb(90, 152, 152, 157) : Color.FromArgb(90, 142, 142, 147));
        SetBrush(resources, "TaskActiveFillBrush", Color.FromArgb(18, 255, 159, 10));
        SetBrush(resources, "TaskPendingFillBrush", isDark ? Color.FromArgb(16, 152, 152, 157) : Color.FromArgb(14, 142, 142, 147));
        SetBrush(resources, "TaskScheduledFillBrush", isDark ? Color.FromArgb(20, 161, 149, 244) : Color.FromArgb(18, 139, 109, 255));
        SetBrush(resources, "TaskDoneFillBrush", Color.FromArgb(18, 48, 209, 88));
    }

    private static bool IsSystemDarkTheme()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            var appsUseLightTheme = key?.GetValue("AppsUseLightTheme");
            return appsUseLightTheme is int value && value == 0;
        }
        catch
        {
            return false;
        }
    }

    private static void SetBrush(ResourceDictionary resources, string key, Color color)
    {
        var brush = new SolidColorBrush(color);
        brush.Freeze();
        resources[key] = brush;
    }
}
