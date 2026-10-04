#include "pch.h"
#include "MainWindow.xaml.h"
#if __has_include("MainWindow.g.cpp")
#include "MainWindow.g.cpp"
#endif

using namespace winrt::Microsoft::UI::Xaml;
using namespace winrt::Microsoft::UI::Xaml::Controls;
using namespace winrt::Microsoft::UI::Xaml::Media;

namespace winrt::VoxRescueNative::implementation
{
    MainWindow::MainWindow()
    {
        InitializeComponent();
        Title(L"Vox Rescue");
        ConfigureWindow();

        auto weak = get_weak();
        auto dispatcher = DispatcherQueue();
        m_audio = std::make_unique<::VoxRescueNative::AudioWorkerBridge>(
            [weak, dispatcher](std::wstring const& line)
            {
                try
                {
                    dispatcher.TryEnqueue([weak, line]
                    {
                        if (auto target = weak.get())
                        {
                            target->OnWorkerLine(line);
                        }
                    });
                }
                catch (...) {}
            });
        m_audio->Start();
    }

    MainWindow::~MainWindow()
    {
        RemoveTrayIcon();
        if (m_hwnd)
        {
            RemoveWindowSubclass(m_hwnd, WindowSubclassProc, 1);
        }
    }

    void MainWindow::ConfigureWindow()
    {
        HWND hwnd{};
        Window window = *this;
        winrt::check_hresult(window.as<::IWindowNative>()->get_WindowHandle(&hwnd));
        m_hwnd = hwnd;
        const UINT dpi = GetDpiForWindow(hwnd);
        const float scale = static_cast<float>(dpi) / 96.0f;
        const int width = static_cast<int>(360.0f * scale);
        const int height = static_cast<int>(460.0f * scale);

        const LONG_PTR style = GetWindowLongPtrW(hwnd, GWL_STYLE);
        SetWindowLongPtrW(hwnd, GWL_STYLE, style & ~WS_MAXIMIZEBOX & ~WS_THICKFRAME);
        SetWindowPos(hwnd, nullptr, 0, 0, width, height, SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED);

        RECT rect{};
        GetWindowRect(hwnd, &rect);
        MONITORINFO monitor{ sizeof(MONITORINFO) };
        GetMonitorInfoW(MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), &monitor);
        const int x = monitor.rcWork.left + ((monitor.rcWork.right - monitor.rcWork.left) - width) / 2;
        const int y = monitor.rcWork.top + ((monitor.rcWork.bottom - monitor.rcWork.top) - height) / 2;
        const int centeredY = std::max<int>(y, static_cast<int>(monitor.rcWork.top));
        SetWindowPos(hwnd, nullptr, x, centeredY, 0, 0, SWP_NOSIZE | SWP_NOZORDER);

        const BOOL darkCaption = FALSE;
        DwmSetWindowAttribute(hwnd, 20, &darkCaption, sizeof(darkCaption));
        const COLORREF caption = RGB(246, 248, 248);
        const COLORREF captionText = RGB(33, 38, 38);
        DwmSetWindowAttribute(hwnd, 35, &caption, sizeof(caption));
        DwmSetWindowAttribute(hwnd, 36, &captionText, sizeof(captionText));
        ConfigureTrayIcon(hwnd);
    }

    void MainWindow::ConfigureTrayIcon(HWND hwnd)
    {
        SetWindowSubclass(hwnd, WindowSubclassProc, 1, reinterpret_cast<DWORD_PTR>(this));
        m_trayIcon = {};
        m_trayIcon.cbSize = sizeof(m_trayIcon);
        m_trayIcon.hWnd = hwnd;
        m_trayIcon.uID = 1;
        m_trayIcon.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        m_trayIcon.uCallbackMessage = WM_APP + 42;
        m_trayIcon.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
        wcscpy_s(m_trayIcon.szTip, L"Vox Rescue - voice protection");
        Shell_NotifyIconW(NIM_ADD, &m_trayIcon);
    }

    void MainWindow::RemoveTrayIcon() noexcept
    {
        if (m_trayIcon.cbSize)
        {
            Shell_NotifyIconW(NIM_DELETE, &m_trayIcon);
            m_trayIcon.cbSize = 0;
        }
    }

    void MainWindow::ShowFromTray() noexcept
    {
        if (!m_hwnd) return;
        ShowWindow(m_hwnd, SW_SHOW);
        ShowWindow(m_hwnd, SW_RESTORE);
        SetForegroundWindow(m_hwnd);
    }

    LRESULT CALLBACK MainWindow::WindowSubclassProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam,
                                                     UINT_PTR subclassId, DWORD_PTR referenceData)
    {
        auto* self = reinterpret_cast<MainWindow*>(referenceData);
        if (!self)
        {
            return DefSubclassProc(hwnd, message, wParam, lParam);
        }

        if (message == WM_CLOSE && !self->m_exitRequested)
        {
            ShowWindow(hwnd, SW_HIDE);
            return 0;
        }
        if (message == WM_APP + 42)
        {
            if (lParam == WM_LBUTTONUP || lParam == WM_LBUTTONDBLCLK)
            {
                self->ShowFromTray();
                return 0;
            }
            if (lParam == WM_RBUTTONUP)
            {
                POINT point{};
                GetCursorPos(&point);
                HMENU menu = CreatePopupMenu();
                AppendMenuW(menu, MF_STRING, 1, L"Open Vox Rescue");
                AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
                AppendMenuW(menu, MF_STRING, 2, L"Exit");
                SetForegroundWindow(hwnd);
                const UINT command = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_NONOTIFY,
                                                    point.x, point.y, 0, hwnd, nullptr);
                DestroyMenu(menu);
                if (command == 1)
                {
                    self->ShowFromTray();
                }
                else if (command == 2)
                {
                    self->m_exitRequested = true;
                    self->RemoveTrayIcon();
                    PostMessageW(hwnd, WM_CLOSE, 0, 0);
                }
                return 0;
            }
        }
        if (message == WM_NCDESTROY)
        {
            self->RemoveTrayIcon();
            RemoveWindowSubclass(hwnd, WindowSubclassProc, subclassId);
            self->m_hwnd = nullptr;
        }
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    void MainWindow::OnMainSwitchToggled(IInspectable const&, RoutedEventArgs const&)
    {
        const auto mainSwitch = MainSwitch();
        const auto status = ProtectionStatus();
        const auto latency = LatencyText();
        const auto meter = InputMeter();
        const auto engineState = EngineStateText();
        if (!mainSwitch || !status || !latency || !meter || !engineState)
        {
            return;
        }

        const bool enabled = mainSwitch.IsOn();
        m_controller.Enabled(enabled);
        if (m_audio)
        {
            if (!m_audio->Running()) m_audio->Start();
            m_audio->Send(enabled ? L"ENABLE 1" : L"ENABLE 0");
        }
        status.Text(enabled ? L"Active" : L"Off");
        latency.Text(enabled ? L"48 kHz  |  20 ms" : L"48 kHz  |  BYPASS");
        engineState.Text(enabled ? L"ACTIVE" : L"READY");

    }

    void MainWindow::OnReturnToggled(IInspectable const&, RoutedEventArgs const&)
    {
        if (m_audio) m_audio->Send(ReturnSwitch().IsOn() ? L"MONITOR 1" : L"MONITOR 0");
    }

    void MainWindow::OnRefreshClicked(IInspectable const&, RoutedEventArgs const&)
    {
        if (m_audio) m_audio->Send(L"REFRESH");
    }

    void MainWindow::OnWorkerLine(std::wstring const& line)
    {
        const auto tab = line.find(L'\t');
        const auto kind = line.substr(0, tab);
        const auto value = tab == std::wstring::npos ? std::wstring{} : line.substr(tab + 1);

        if (kind == L"WORKER" || kind == L"LOADING")
        {
            EngineStateText().Text(L"LOADING");
            ProtectionStatus().Text(L"Preparing model");
        }
        else if (kind == L"READY")
        {
            MainSwitch().IsEnabled(true);
            EngineStateText().Text(MainSwitch().IsOn() ? L"ACTIVE" : L"READY");
            ProtectionStatus().Text(MainSwitch().IsOn() ? L"Active" : L"Off");
        }
        else if (kind == L"METER")
        {
            try { InputMeter().Value(std::stod(value) * 100.0); } catch (...) {}
        }
        else if (kind == L"DEVICES") { DeviceText().Text(value); }
        else if (kind == L"ROUTE") { RouteText().Text(value); }
        else if (kind == L"STATUS") { ProtectionStatus().Text(value); }
        else if (kind == L"ERROR")
        {
            MainSwitch().IsEnabled(false);
            EngineStateText().Text(L"ERROR");
            ProtectionStatus().Text(value);
        }
    }
}
