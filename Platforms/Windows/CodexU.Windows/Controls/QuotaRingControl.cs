using System.Windows;
using System.Windows.Media;

namespace CodexU.Windows.Controls;

public sealed class QuotaRingControl : FrameworkElement
{
    public static readonly DependencyProperty PrimaryPercentProperty =
        DependencyProperty.Register(nameof(PrimaryPercent), typeof(double), typeof(QuotaRingControl), new FrameworkPropertyMetadata(0d, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty SecondaryPercentProperty =
        DependencyProperty.Register(nameof(SecondaryPercent), typeof(double), typeof(QuotaRingControl), new FrameworkPropertyMetadata(0d, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty HasPrimaryProperty =
        DependencyProperty.Register(nameof(HasPrimary), typeof(bool), typeof(QuotaRingControl), new FrameworkPropertyMetadata(false, FrameworkPropertyMetadataOptions.AffectsRender));

    public static readonly DependencyProperty HasSecondaryProperty =
        DependencyProperty.Register(nameof(HasSecondary), typeof(bool), typeof(QuotaRingControl), new FrameworkPropertyMetadata(false, FrameworkPropertyMetadataOptions.AffectsRender));

    public double PrimaryPercent
    {
        get => (double)GetValue(PrimaryPercentProperty);
        set => SetValue(PrimaryPercentProperty, value);
    }

    public double SecondaryPercent
    {
        get => (double)GetValue(SecondaryPercentProperty);
        set => SetValue(SecondaryPercentProperty, value);
    }

    public bool HasPrimary
    {
        get => (bool)GetValue(HasPrimaryProperty);
        set => SetValue(HasPrimaryProperty, value);
    }

    public bool HasSecondary
    {
        get => (bool)GetValue(HasSecondaryProperty);
        set => SetValue(HasSecondaryProperty, value);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        var width = double.IsInfinity(availableSize.Width) ? 146 : availableSize.Width;
        var height = double.IsInfinity(availableSize.Height) ? 146 : availableSize.Height;
        return new Size(width, height);
    }

    protected override void OnRender(DrawingContext drawingContext)
    {
        base.OnRender(drawingContext);

        var size = Math.Min(ActualWidth, ActualHeight);
        if (size <= 0)
        {
            return;
        }

        var center = new Point(ActualWidth / 2, ActualHeight / 2);
        DrawRing(drawingContext, center, size / 2 - 9, 16, HasPrimary ? PrimaryPercent : 0, Brush("BrandLightBrush"), Brush("BrandPrimaryBrush"));
        DrawRing(drawingContext, center, size / 2 - 29, 16, HasSecondary ? SecondaryPercent : 0, Brush("BrandHighlightBrush"), Brush("BrandSecondaryBrush"));

        drawingContext.DrawEllipse(Brush("SurfaceTrackBrush"), null, center, 34, 34);
    }

    private void DrawRing(DrawingContext context, Point center, double radius, double thickness, double percent, Brush startBrush, Brush endBrush)
    {
        var trackPen = new Pen(Brush("SurfaceTrackBrush"), thickness)
        {
            StartLineCap = PenLineCap.Round,
            EndLineCap = PenLineCap.Round
        };
        context.DrawEllipse(null, trackPen, center, radius, radius);

        var progress = Math.Clamp(percent / 100d, 0d, 1d);
        if (progress <= 0)
        {
            return;
        }

        var segments = Math.Max(18, (int)Math.Ceiling(progress * 144));
        var startColor = ((SolidColorBrush)startBrush).Color;
        var endColor = ((SolidColorBrush)endBrush).Color;

        for (var index = 0; index < segments; index++)
        {
            var from = (double)index / segments * progress;
            var to = (double)(index + 1) / segments * progress;
            var color = Mix(startColor, endColor, (double)(index + 1) / segments);
            var pen = new Pen(new SolidColorBrush(color), thickness)
            {
                StartLineCap = index == 0 ? PenLineCap.Round : PenLineCap.Flat,
                EndLineCap = index == segments - 1 ? PenLineCap.Round : PenLineCap.Flat
            };
            pen.Freeze();
            context.DrawGeometry(null, pen, ArcGeometry(center, radius, from, to));
        }
    }

    private static StreamGeometry ArcGeometry(Point center, double radius, double from, double to)
    {
        var geometry = new StreamGeometry();
        using (var context = geometry.Open())
        {
            var start = PointOnCircle(center, radius, from);
            var end = PointOnCircle(center, radius, to);
            context.BeginFigure(start, false, false);
            context.ArcTo(end, new Size(radius, radius), 0, (to - from) > 0.5, SweepDirection.Clockwise, true, false);
        }

        geometry.Freeze();
        return geometry;
    }

    private static Point PointOnCircle(Point center, double radius, double progress)
    {
        var radians = (-90 + progress * 360) * Math.PI / 180;
        return new Point(center.X + Math.Cos(radians) * radius, center.Y + Math.Sin(radians) * radius);
    }

    private static Color Mix(Color start, Color end, double fraction)
    {
        fraction = Math.Clamp(fraction, 0, 1);
        return Color.FromArgb(
            255,
            (byte)(start.R + (end.R - start.R) * fraction),
            (byte)(start.G + (end.G - start.G) * fraction),
            (byte)(start.B + (end.B - start.B) * fraction));
    }

    private Brush Brush(string key) =>
        TryFindResource(key) as Brush ?? Brushes.Transparent;
}
