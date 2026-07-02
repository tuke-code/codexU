using System.ComponentModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows;
using CodexU.Windows.ViewModels;
using Forms = System.Windows.Forms;

namespace CodexU.Windows.Services;

public sealed class TrayIconService : IDisposable
{
    private readonly MainWindow _window;
    private readonly MainViewModel _viewModel;
    private readonly Forms.NotifyIcon _notifyIcon;
    private readonly Icon _icon;
    private readonly IntPtr _iconHandle;
    private readonly Forms.ToolStripMenuItem _pinItem;

    public TrayIconService(MainWindow window, MainViewModel viewModel)
    {
        _window = window;
        _viewModel = viewModel;
        (_icon, _iconHandle) = CreateIcon();
        _pinItem = new Forms.ToolStripMenuItem("Pin topmost", null, (_, _) => TogglePinned())
        {
            Checked = viewModel.IsPinnedTopmost
        };

        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("Show / hide", null, (_, _) => ToggleVisibility());
        menu.Items.Add(_pinItem);
        menu.Items.Add("Refresh", null, (_, _) => _viewModel.RefreshCommand.Execute(null));
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("Quit", null, (_, _) => _window.RequestQuit());

        _notifyIcon = new Forms.NotifyIcon
        {
            Icon = _icon,
            Text = "codexU",
            Visible = true,
            ContextMenuStrip = menu
        };
        _notifyIcon.MouseClick += NotifyIconOnMouseClick;
        _viewModel.PropertyChanged += ViewModelOnPropertyChanged;
    }

    public void Dispose()
    {
        _viewModel.PropertyChanged -= ViewModelOnPropertyChanged;
        _notifyIcon.MouseClick -= NotifyIconOnMouseClick;
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
        _icon.Dispose();
        if (_iconHandle != IntPtr.Zero)
        {
            DestroyIcon(_iconHandle);
        }
    }

    private void NotifyIconOnMouseClick(object? sender, Forms.MouseEventArgs e)
    {
        if (e.Button == Forms.MouseButtons.Left)
        {
            ToggleVisibility();
        }
    }

    private void ViewModelOnPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(MainViewModel.IsPinnedTopmost) or "")
        {
            _pinItem.Checked = _viewModel.IsPinnedTopmost;
        }
    }

    private void ToggleVisibility()
    {
        if (_window.IsVisible)
        {
            _window.Hide();
            return;
        }

        _window.ShowWidget(activate: true);
    }

    private void TogglePinned()
    {
        _window.SetPinnedTopmost(!_viewModel.IsPinnedTopmost);
    }

    private static (Icon Icon, IntPtr Handle) CreateIcon()
    {
        using var bitmap = new Bitmap(32, 32);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var background = new LinearGradientBrush(new Rectangle(0, 0, 32, 32), Color.FromArgb(40, 102, 247), Color.FromArgb(218, 163, 250), 45f);
        using var path = RoundedRectangle(new RectangleF(3, 3, 26, 26), 7);
        graphics.FillPath(background, path);
        using var font = new Font("Segoe UI", 16, FontStyle.Bold, GraphicsUnit.Pixel);
        using var textBrush = new SolidBrush(Color.White);
        var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        graphics.DrawString("U", font, textBrush, new RectangleF(0, 0, 32, 30), format);

        var handle = bitmap.GetHicon();
        return (Icon.FromHandle(handle), handle);
    }

    private static GraphicsPath RoundedRectangle(RectangleF bounds, float radius)
    {
        var diameter = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
        path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
        path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyIcon(IntPtr hIcon);
}
