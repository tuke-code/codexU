using System.Windows;
using System.Windows.Media;

namespace CodexU.Windows.Controls;

public sealed class ValueProgressBarControl : FrameworkElement
{
    private static readonly Milestone[] Milestones =
    {
        new("Plus", 20, "StatusInfoBrush"),
        new("Pro100", 100, "BrandSecondaryBrush"),
        new("Pro200", 200, "BrandLightBrush")
    };

    public static readonly DependencyProperty CurrentValueProperty =
        DependencyProperty.Register(nameof(CurrentValue), typeof(double), typeof(ValueProgressBarControl), new FrameworkPropertyMetadata(0d, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty MaxValueProperty =
        DependencyProperty.Register(nameof(MaxValue), typeof(double), typeof(ValueProgressBarControl), new FrameworkPropertyMetadata(46500d, FrameworkPropertyMetadataOptions.AffectsRender));

    public double CurrentValue
    {
        get => (double)GetValue(CurrentValueProperty);
        set => SetValue(CurrentValueProperty, value);
    }

    public double MaxValue
    {
        get => (double)GetValue(MaxValueProperty);
        set => SetValue(MaxValueProperty, value);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        var width = double.IsInfinity(availableSize.Width) ? 320 : availableSize.Width;
        var height = double.IsInfinity(availableSize.Height) ? 18 : availableSize.Height;
        return new Size(width, height);
    }

    protected override void OnRender(DrawingContext drawingContext)
    {
        base.OnRender(drawingContext);
        var barHeight = Math.Min(10, ActualHeight);
        var y = (ActualHeight - barHeight) / 2;
        var track = new Rect(0, y, ActualWidth, barHeight);
        drawingContext.DrawRoundedRectangle(Brush("SurfaceTrackBrush"), null, track, 5, 5);

        var progressWidth = ValueOffset(CurrentValue, ActualWidth);
        if (CurrentValue > 0 && progressWidth > 0)
        {
            var accent = CurrentValue >= 200 ? Brush("BrandLightBrush") :
                CurrentValue >= 100 ? Brush("BrandSecondaryBrush") :
                CurrentValue >= 20 ? Brush("StatusInfoBrush") :
                Brush("StatusWarningBrush");
            drawingContext.DrawRoundedRectangle(accent, null, new Rect(0, y, Math.Max(5, progressWidth), barHeight), 5, 5);
        }

        foreach (var milestone in Milestones)
        {
            var x = ValueOffset(milestone.AmountUsd, ActualWidth);
            drawingContext.DrawEllipse(Brush(milestone.BrushKey), new Pen(Brush("WindowBrush"), 1), new Point(x, ActualHeight / 2), 4, 4);
        }
    }

    private double ValueOffset(double amount, double width)
    {
        var maxValue = Math.Max(MaxValue, 200);
        var clamped = Math.Clamp(amount, 0, maxValue);
        const double subscriptionCeiling = 200;
        const double subscriptionBand = 0.28;

        var fraction = clamped <= subscriptionCeiling
            ? subscriptionBand * (clamped / subscriptionCeiling)
            : subscriptionBand + (1 - subscriptionBand) * ((clamped - subscriptionCeiling) / Math.Max(maxValue - subscriptionCeiling, 1));

        return Math.Clamp(width * fraction, 0, width);
    }

    private Brush Brush(string key) =>
        TryFindResource(key) as Brush ?? Brushes.Transparent;

    private sealed record Milestone(string Title, double AmountUsd, string BrushKey);
}
