using System.ComponentModel;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using CodexU.Windows.Services;
using CodexU.Windows.ViewModels;
using Microsoft.Win32;

namespace CodexU.Windows;

public partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;
    private GlobalHotKeyService? _hotKeyService;
    private bool _allowClose;

    public MainWindow(MainViewModel viewModel)
    {
        _viewModel = viewModel;
        DataContext = viewModel;
        InitializeComponent();

        _viewModel.ThemeChanged += (_, _) => ApplyTheme();
        SystemEvents.UserPreferenceChanged += SystemEventsOnUserPreferenceChanged;
    }

    public void ShowWidget(bool activate)
    {
        if (!IsVisible)
        {
            Show();
        }

        if (WindowState == WindowState.Minimized)
        {
            WindowState = WindowState.Normal;
        }

        if (activate)
        {
            Activate();
        }
    }

    public void SetPinnedTopmost(bool pinned)
    {
        _viewModel.IsPinnedTopmost = pinned;
        Topmost = pinned;
        if (pinned)
        {
            ShowWidget(activate: true);
        }
    }

    public void RequestQuit()
    {
        _allowClose = true;
        Close();
        Application.Current.Shutdown();
    }

    private void Window_Loaded(object sender, RoutedEventArgs e)
    {
        PlaceTopRight();
        SetPinnedTopmost(_viewModel.IsPinnedTopmost);
    }

    private void Window_SourceInitialized(object? sender, EventArgs e)
    {
        NativeWindowStyles.HideFromAltTab(this);
        _hotKeyService = new GlobalHotKeyService(this, ModifierKeys.Control | ModifierKeys.Alt, Key.U, ToggleFromHotKey);
        RenderOptions.SetClearTypeHint(this, ClearTypeHint.Enabled);
    }

    private void Window_Closing(object? sender, CancelEventArgs e)
    {
        if (_allowClose)
        {
            return;
        }

        e.Cancel = true;
        Hide();
    }

    private void Window_Closed(object? sender, EventArgs e)
    {
        _viewModel.Stop();
        _hotKeyService?.Dispose();
        SystemEvents.UserPreferenceChanged -= SystemEventsOnUserPreferenceChanged;
    }

    private void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed)
        {
            try
            {
                DragMove();
            }
            catch
            {
                // DragMove can throw if the mouse button is released during activation.
            }
        }
    }

    private void PinButton_Click(object sender, RoutedEventArgs e)
    {
        SetPinnedTopmost(!_viewModel.IsPinnedTopmost);
    }

    private void CloseToTray_Click(object sender, RoutedEventArgs e)
    {
        Hide();
    }

    private void ToggleFromHotKey()
    {
        Dispatcher.Invoke(() =>
        {
            if (!IsVisible)
            {
                ShowWidget(activate: true);
                return;
            }

            SetPinnedTopmost(!_viewModel.IsPinnedTopmost);
        });
    }

    private void ApplyTheme()
    {
        ThemeResourceService.Apply(_viewModel.ThemeMode);
        InvalidateVisualTree(this);
    }

    private void SystemEventsOnUserPreferenceChanged(object sender, UserPreferenceChangedEventArgs e)
    {
        if (_viewModel.ThemeMode == Models.WidgetThemeMode.System)
        {
            ApplyTheme();
        }
    }

    private void PlaceTopRight()
    {
        var area = SystemParameters.WorkArea;
        Left = Math.Max(area.Left + 16, area.Right - Width - 28);
        Top = Math.Max(area.Top + 16, area.Top + 36);
    }

    private static void InvalidateVisualTree(DependencyObject root)
    {
        if (root is UIElement element)
        {
            element.InvalidateVisual();
        }

        var count = VisualTreeHelper.GetChildrenCount(root);
        for (var i = 0; i < count; i++)
        {
            InvalidateVisualTree(VisualTreeHelper.GetChild(root, i));
        }
    }
}
