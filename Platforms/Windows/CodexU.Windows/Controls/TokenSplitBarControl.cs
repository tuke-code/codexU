using System.Windows;
using System.Windows.Media;

namespace CodexU.Windows.Controls;

public sealed class TokenSplitBarControl : FrameworkElement
{
    public static readonly DependencyProperty UncachedInputProperty =
        DependencyProperty.Register(nameof(UncachedInput), typeof(long), typeof(TokenSplitBarControl), new FrameworkPropertyMetadata(0L, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty CachedInputProperty =
        DependencyProperty.Register(nameof(CachedInput), typeof(long), typeof(TokenSplitBarControl), new FrameworkPropertyMetadata(0L, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty OutputProperty =
        DependencyProperty.Register(nameof(Output), typeof(long), typeof(TokenSplitBarControl), new FrameworkPropertyMetadata(0L, FrameworkPropertyMetadataOptions.AffectsRender));

    public long UncachedInput
    {
        get => (long)GetValue(UncachedInputProperty);
        set => SetValue(UncachedInputProperty, value);
    }

    public long CachedInput
    {
        get => (long)GetValue(CachedInputProperty);
        set => SetValue(CachedInputProperty, value);
    }

    public long Output
    {
        get => (long)GetValue(OutputProperty);
        set => SetValue(OutputProperty, value);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        var width = double.IsInfinity(availableSize.Width) ? 120 : availableSize.Width;
        var height = double.IsInfinity(availableSize.Height) ? 8 : availableSize.Height;
        return new Size(width, height);
    }

    protected override void OnRender(DrawingContext drawingContext)
    {
        base.OnRender(drawingContext);
        var rect = new Rect(0, 0, ActualWidth, ActualHeight);
        if (rect.Width <= 0 || rect.Height <= 0)
        {
            return;
        }

        drawingContext.DrawRoundedRectangle(Brush("SurfaceTrackBrush"), null, rect, rect.Height / 2, rect.Height / 2);
        var total = Math.Max(UncachedInput, 0) + Math.Max(CachedInput, 0) + Math.Max(Output, 0);
        if (total <= 0)
        {
            return;
        }

        drawingContext.PushClip(new RectangleGeometry(rect, rect.Height / 2, rect.Height / 2));
        var x = 0d;
        DrawSegment(drawingContext, ref x, UncachedInput, total, Brush("StatusInfoBrush"));
        DrawSegment(drawingContext, ref x, CachedInput, total, Brush("BrandSecondaryBrush"));
        DrawSegment(drawingContext, ref x, Output, total, Brush("StatusWarningBrush"));
        drawingContext.Pop();
    }

    private void DrawSegment(DrawingContext context, ref double x, long value, long total, Brush brush)
    {
        if (value <= 0)
        {
            return;
        }

        var width = Math.Max(2, ActualWidth * value / total);
        context.DrawRectangle(brush, null, new Rect(x, 0, Math.Min(width, Math.Max(0, ActualWidth - x)), ActualHeight));
        x += width;
    }

    private Brush Brush(string key) =>
        TryFindResource(key) as Brush ?? Brushes.Transparent;
}
