using System.Threading;
using System.Windows;
using CodexU.Windows.Services;
using CodexU.Windows.ViewModels;

namespace CodexU.Windows;

public partial class App : Application
{
    private Mutex? _singleInstanceMutex;
    private TrayIconService? _trayIconService;

    protected override void OnStartup(StartupEventArgs e)
    {
        _singleInstanceMutex = new Mutex(true, "CodexU.Windows.SingleInstance", out var isFirstInstance);
        if (!isFirstInstance)
        {
            Shutdown();
            return;
        }

        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        var settings = LocalSettings.Load();
        ThemeResourceService.Apply(settings.ThemeMode);

        var viewModel = new MainViewModel(new CodexUsageReader(), settings);
        var window = new MainWindow(viewModel);
        MainWindow = window;
        _trayIconService = new TrayIconService(window, viewModel);

        window.Show();
        viewModel.Start();
        base.OnStartup(e);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _trayIconService?.Dispose();
        _singleInstanceMutex?.Dispose();
        base.OnExit(e);
    }
}
