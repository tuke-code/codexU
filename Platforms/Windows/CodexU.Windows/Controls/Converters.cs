using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using CodexU.Windows.Models;

namespace CodexU.Windows.Controls;

public sealed class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is bool flag && flag ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is Visibility visibility && visibility == Visibility.Visible;
}

public sealed class InverseBoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is bool flag && flag ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        value is Visibility visibility && visibility != Visibility.Visible;
}

public sealed class TaskKindBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var kind = value is TaskColumnKind taskKind ? taskKind : TaskColumnKind.Pending;
        var mode = parameter as string ?? "accent";
        var key = mode == "fill" ? FillKey(kind) : AccentKey(kind);
        return Application.Current.TryFindResource(key) as Brush ?? Brushes.Transparent;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        Binding.DoNothing;

    private static string AccentKey(TaskColumnKind kind) =>
        kind switch
        {
            TaskColumnKind.Active => "StatusWarningBrush",
            TaskColumnKind.Pending => "StatusNeutralBrush",
            TaskColumnKind.Scheduled => "BrandSecondaryBrush",
            TaskColumnKind.Done => "StatusSuccessBrush",
            _ => "StatusNeutralBrush"
        };

    private static string FillKey(TaskColumnKind kind) =>
        kind switch
        {
            TaskColumnKind.Active => "TaskActiveFillBrush",
            TaskColumnKind.Pending => "TaskPendingFillBrush",
            TaskColumnKind.Scheduled => "TaskScheduledFillBrush",
            TaskColumnKind.Done => "TaskDoneFillBrush",
            _ => "TaskPendingFillBrush"
        };
}

public sealed class ResourceKeyBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var key = value as string;
        return key is not null && Application.Current.TryFindResource(key) is Brush brush
            ? brush
            : Brushes.Transparent;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) =>
        Binding.DoNothing;
}
