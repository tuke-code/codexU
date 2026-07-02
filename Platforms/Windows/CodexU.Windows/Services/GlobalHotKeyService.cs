using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

namespace CodexU.Windows.Services;

public sealed class GlobalHotKeyService : IDisposable
{
    private const int WmHotKey = 0x0312;
    private const uint ModAlt = 0x0001;
    private const uint ModControl = 0x0002;
    private const uint ModShift = 0x0004;
    private const uint ModWin = 0x0008;
    private readonly int _id = Environment.TickCount & 0x7FFF;
    private readonly Action _callback;
    private readonly HwndSource _source;
    private readonly IntPtr _handle;
    private bool _registered;

    public GlobalHotKeyService(Window window, ModifierKeys modifiers, Key key, Action callback)
    {
        _callback = callback;
        _handle = new WindowInteropHelper(window).Handle;
        _source = HwndSource.FromHwnd(_handle) ?? throw new InvalidOperationException("Window handle is not initialized.");
        _source.AddHook(WndProc);

        var modifierFlags = ToModifierFlags(modifiers);
        var virtualKey = (uint)KeyInterop.VirtualKeyFromKey(key);
        _registered = RegisterHotKey(_handle, _id, modifierFlags, virtualKey);
    }

    public bool IsRegistered => _registered;

    public void Dispose()
    {
        _source.RemoveHook(WndProc);
        if (_registered)
        {
            UnregisterHotKey(_handle, _id);
            _registered = false;
        }
    }

    private IntPtr WndProc(IntPtr hwnd, int message, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        if (message == WmHotKey && wParam.ToInt32() == _id)
        {
            handled = true;
            _callback();
        }

        return IntPtr.Zero;
    }

    private static uint ToModifierFlags(ModifierKeys modifiers)
    {
        uint flags = 0;
        if (modifiers.HasFlag(ModifierKeys.Alt)) flags |= ModAlt;
        if (modifiers.HasFlag(ModifierKeys.Control)) flags |= ModControl;
        if (modifiers.HasFlag(ModifierKeys.Shift)) flags |= ModShift;
        if (modifiers.HasFlag(ModifierKeys.Windows)) flags |= ModWin;
        return flags;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr hWnd, int id);
}
